"""
SMS Expense Tracking Router (Mounted at /expenses).
Exposes endpoints for:
- Batch ingestion of card transactions & bills with idempotency
- Transaction restore & paginated browsing
- Soft delete (tombstone) & DPDP right-to-erasure
- Append-only consent ledger
- Card milestone rules and progress
- Spend analytics summary (category, card, merchant, monthly)
- Bank sender DLT header registry
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.expense import (
    BatchIngestRequest,
    BatchIngestResponse,
    CardMilestoneResponse,
    SenderRegistryResponse,
    SmsConsentRequest,
    SmsConsentResponse,
    SpendAnalyticsSummaryResponse,
    TransactionListResponse,
)
from app.services.expense_service import expense_service

router = APIRouter(prefix="/expenses", tags=["SMS Expense Tracking"])


@router.post(
    "/transactions/batch",
    response_model=ApiResponse[BatchIngestResponse],
    status_code=status.HTTP_200_OK,
)
async def ingest_transactions_batch(
    req: BatchIngestRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingests up to 100 card transactions and 100 bills per batch.
    Deduplicates by SHA-256 hash and updates user-overridden categories.
    Idempotent: Replaying the same Idempotency-Key returns the cached response.
    """
    result = await expense_service.ingest_batch(
        db=db,
        user_id=user.id,
        idempotency_key=idempotency_key,
        req=req,
    )
    return ApiResponse(
        message="Batch ingestion processed successfully.",
        data=result,
    )


@router.get(
    "/transactions",
    response_model=ApiResponse[TransactionListResponse],
)
async def list_transactions(
    since: Optional[datetime] = Query(None, description="Filter transactions occurred on or after this timestamp"),
    cursor: Optional[int] = Query(None, description="Pagination cursor (transaction ID)"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    user_card_id: Optional[int] = Query(None, description="Filter by wallet user card ID"),
    category: Optional[str] = Query(None, description="Filter by category slug"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves paginated active transactions for the authenticated user.
    Used for device restore, web view, and cross-device sync.
    """
    result = await expense_service.list_transactions(
        db=db,
        user_id=user.id,
        since=since,
        cursor=cursor,
        limit=limit,
        user_card_id=user_card_id,
        category=category,
    )
    return ApiResponse(data=result)


@router.delete(
    "/transactions/{dedupe_hash}",
    response_model=ApiResponse[bool],
)
async def delete_transaction(
    dedupe_hash: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-deletes one transaction record.
    The tombstone ensures subsequent SMS rescans will not re-import this transaction.
    """
    await expense_service.delete_transaction(db, user.id, dedupe_hash)
    return ApiResponse(
        message="Transaction deleted and tombstoned successfully.",
        data=True,
    )


@router.delete(
    "/data",
    response_model=ApiResponse[bool],
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_all_expense_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    DPDP Right to Erasure: Permanently removes all SMS-derived records
    (transactions, bills, consent records, idempotency cache) for the account.
    """
    await expense_service.delete_all_user_data(db, user.id)
    return ApiResponse(
        message="All expense tracking data permanently erased.",
        data=True,
    )


@router.put(
    "/consent",
    response_model=ApiResponse[SmsConsentResponse],
)
async def record_consent(
    req: SmsConsentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Records an immutable consent artefact in the DPDP consent ledger.
    """
    client_ip = request.client.host if request.client else None
    ip_hash = None
    if client_ip:
        import hashlib
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:32]

    res = await expense_service.record_consent(
        db=db,
        user_id=user.id,
        req=req,
        ip_hash=ip_hash,
    )
    return ApiResponse(
        message="Consent record saved successfully.",
        data=res,
    )


@router.get(
    "/milestones",
    response_model=ApiResponse[List[CardMilestoneResponse]],
)
async def get_card_milestones(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves spend milestone definitions for the cards held in the user's wallet.
    Calculates progress against spend windows using anniversary months.
    """
    milestones = await expense_service.get_milestones(db, user.id)
    return ApiResponse(data=milestones)


@router.get(
    "/analytics/summary",
    response_model=ApiResponse[SpendAnalyticsSummaryResponse],
)
async def get_spend_analytics_summary(
    from_date: Optional[datetime] = Query(None, alias="from", description="Start timestamp filter"),
    to_date: Optional[datetime] = Query(None, alias="to", description="End timestamp filter"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Computes net spend, gross debits, total refunds, and breakdowns
    by category, by card, top merchants, and monthly trend.
    """
    summary = await expense_service.get_analytics_summary(
        db=db,
        user_id=user.id,
        from_date=from_date,
        to_date=to_date,
    )
    return ApiResponse(data=summary)


@router.get(
    "/sender-registry",
    response_model=ApiResponse[SenderRegistryResponse],
)
async def get_sender_registry(
    version: Optional[int] = Query(None, description="Current client registry version"),
):
    """
    Public registry of Indian bank DLT SMS header cores and body keywords.
    Allows dynamic header updates without requiring an app store release.
    """
    registry = expense_service.get_sender_registry(client_version=version)
    return ApiResponse(data=registry)
