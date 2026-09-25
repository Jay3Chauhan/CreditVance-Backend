"""
Admin Ingestion & Sync API Router.
Protected by X-Admin-API-Key or Admin User credentials.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, verify_admin_key
from app.core.database import AsyncSessionLocal
from app.models.bank import Bank
from app.models.card import CreditCard
from app.models.sync_audit import SyncAuditLog
from app.schemas.common import ApiResponse
from app.schemas.sync import (
    SyncAuditResponse,
    SyncStatusResponse,
    SyncTriggerRequest,
)
from app.services.sync_service import SYNC_LOCK_KEY, sync_service
from app.core.redis_client import redis_service

router = APIRouter(prefix="/admin/sync", tags=["Admin & Data Ingestion"])


async def _run_background_sync(sync_tabs: bool, limit_cards: int | None):
    async with AsyncSessionLocal() as session:
        await sync_service.execute_sync(
            db=session,
            sync_type="manual",
            sync_tabs=sync_tabs,
            limit_cards=limit_cards,
        )


@router.post("/trigger", response_model=ApiResponse[Dict[str, Any]])
async def trigger_sync(
    req: SyncTriggerRequest,
    background_tasks: BackgroundTasks,
    authorized: bool = Depends(verify_admin_key),
):
    """
    Triggers an asynchronous background synchronization run from SaveSage Club APIs.
    Protected by X-Admin-API-Key or Admin JWT.
    """
    background_tasks.add_task(
        _run_background_sync, sync_tabs=req.sync_tabs, limit_cards=req.limit_cards
    )
    return ApiResponse(
        message="Data synchronization task queued in background.",
        data={
            "sync_tabs": req.sync_tabs,
            "limit_cards": req.limit_cards,
            "status": "queued",
        },
    )


@router.get("/status", response_model=ApiResponse[SyncStatusResponse])
async def get_sync_status(
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Checks current sync lock status and database entity counts."""
    # Check if lock exists
    is_syncing = False
    lock_val = await redis_service.get_json(SYNC_LOCK_KEY)
    if lock_val:
        is_syncing = True

    # Count cards and banks
    cards_count = (await db.execute(select(func.count(CreditCard.id)))).scalar() or 0
    banks_count = (await db.execute(select(func.count(Bank.id)))).scalar() or 0

    # Get last audit log
    last_audit_stmt = select(SyncAuditLog).order_by(desc(SyncAuditLog.started_at)).limit(1)
    last_audit = (await db.execute(last_audit_stmt)).scalar_one_or_none()

    status_data = SyncStatusResponse(
        is_syncing=is_syncing,
        last_sync_status=last_audit.status if last_audit else "none",
        last_sync_time=last_audit.completed_at if last_audit else None,
        total_cards_in_db=cards_count,
        total_banks_in_db=banks_count,
    )
    return ApiResponse(data=status_data)


@router.get("/history", response_model=ApiResponse[List[SyncAuditResponse]])
async def get_sync_history(
    limit: int = 10,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves recent sync audit logs."""
    stmt = select(SyncAuditLog).order_by(desc(SyncAuditLog.started_at)).limit(limit)
    audits = (await db.execute(stmt)).scalars().all()
    return ApiResponse(
        data=[SyncAuditResponse.model_validate(a) for a in audits]
    )
