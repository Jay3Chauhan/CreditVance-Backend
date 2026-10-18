"""
Background Cron Tasks and Scheduler Module.
Configures APScheduler for periodic SaveSage data synchronization.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.redis_client import redis_service
from app.services.sync_service import sync_service

scheduler = AsyncIOScheduler()


async def scheduled_catalog_sync_job():
    """Weekly scheduled cron job to synchronize credit cards and perk tabs."""
    logger.info("Cron trigger: Starting scheduled SaveSage catalog synchronization...")
    async with AsyncSessionLocal() as session:
        try:
            result = await sync_service.execute_sync(
                db=session,
                sync_type="scheduled",
                sync_tabs=True,
                limit_cards=None,
            )
            logger.info(f"Scheduled sync completed: {result}")
        except Exception as e:
            logger.exception(f"Exception during scheduled sync cron job: {e}")


async def scheduled_push_job():
    """Daily payment and statement pushes. A lock stops the second worker from doubling them."""
    from app.services.notification_service import notification_service

    acquired = await redis_service.acquire_lock("lock:push:reminders", ttl_seconds=3600)
    if not acquired:
        logger.info("Push reminder job skipped because another worker holds the lock.")
        return
    try:
        async with AsyncSessionLocal() as session:
            result = await notification_service.dispatch_scheduled_pushes(session)
            logger.info(f"Scheduled push reminders finished: {result}")
    except Exception as exc:
        logger.exception(f"Scheduled push reminder job failed: {exc}")
    finally:
        await redis_service.release_lock("lock:push:reminders")


def _cron_trigger(expression: str) -> CronTrigger | None:
    parts = expression.split()
    if len(parts) != 5:
        logger.warning(
            f"Invalid cron format '{expression}'. Expected 5 space-separated parts."
        )
        return None
    return CronTrigger(
        minute=parts[0],
        hour=parts[1],
        day=parts[2],
        month=parts[3],
        day_of_week=parts[4],
        timezone="UTC",
    )


def start_scheduler():
    """Starts catalog sync and/or the daily push job, whichever flags are on."""
    jobs = 0
    if settings.CRON_SYNC_ENABLED:
        trigger = _cron_trigger(settings.CRON_SYNC_SCHEDULE)
        if trigger:
            scheduler.add_job(
                scheduled_catalog_sync_job,
                trigger=trigger,
                id="savesage_catalog_sync",
                name="Synchronize SaveSage Credit Cards Catalog",
                replace_existing=True,
            )
            jobs += 1
            logger.info(f"Catalog sync scheduled at '{settings.CRON_SYNC_SCHEDULE}' UTC.")
    else:
        logger.info("Background catalog sync is disabled via CRON_SYNC_ENABLED=false.")

    if settings.CRON_PUSH_ENABLED:
        trigger = _cron_trigger(settings.CRON_PUSH_SCHEDULE)
        if trigger:
            scheduler.add_job(
                scheduled_push_job,
                trigger=trigger,
                id="firebase_payment_reminders",
                name="Send Firebase payment and statement reminders",
                replace_existing=True,
            )
            jobs += 1
            logger.info(f"Push reminders scheduled at '{settings.CRON_PUSH_SCHEDULE}' UTC.")
    else:
        logger.info("Push reminder cron is disabled via CRON_PUSH_ENABLED=false.")

    if not jobs:
        return
    try:
        if not scheduler.running:
            scheduler.start()
            logger.info("Background scheduler started.")
    except Exception as exc:
        logger.error(f"Failed to start APScheduler: {exc}")


def shutdown_scheduler():
    """Gracefully shuts down the APScheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler shut down.")
