"""
Background Cron Tasks and Scheduler Module.
Configures APScheduler for periodic SaveSage data synchronization.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from app.core.config import settings
from app.core.database import AsyncSessionLocal
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


def start_scheduler():
    """Initializes and starts the APScheduler if enabled in configuration."""
    if not settings.CRON_SYNC_ENABLED:
        logger.info("Background cron sync is disabled via CRON_SYNC_ENABLED=False.")
        return

    try:
        # Parse cron expression (5 fields: min hour day month day_of_week)
        parts = settings.CRON_SYNC_SCHEDULE.split()
        if len(parts) == 5:
            trigger = CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone="UTC",
            )
            scheduler.add_job(
                scheduled_catalog_sync_job,
                trigger=trigger,
                id="savesage_catalog_sync",
                name="Synchronize SaveSage Credit Cards Catalog",
                replace_existing=True,
            )
            scheduler.start()
            logger.info(
                f"Background scheduler started with cron expression: '{settings.CRON_SYNC_SCHEDULE}' UTC."
            )
        else:
            logger.warning(
                f"Invalid cron format '{settings.CRON_SYNC_SCHEDULE}'. Expected 5 space-separated parts. Scheduler not started."
            )
    except Exception as e:
        logger.error(f"Failed to start APScheduler: {e}")


def shutdown_scheduler():
    """Gracefully shuts down the APScheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler shut down.")
