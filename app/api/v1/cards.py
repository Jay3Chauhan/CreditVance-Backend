"""
Credit Cards Catalog API Router.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.card import (
    CardDetailResponse,
    CardFilterQuery,
    CardSummaryResponse,
    CardTabResponse,
)
from app.schemas.common import ApiResponse
from app.services.card_service import card_service

router = APIRouter(prefix="/cards", tags=["Credit Cards Catalog"])


@router.get("", response_model=ApiResponse[List[CardSummaryResponse]])
async def list_cards(
    search: Optional[str] = Query(None, description="Search by card or bank name"),
    bank_slug: Optional[str] = Query(None, description="Filter by bank slug (e.g. hdfc, icici, axis)"),
    network: Optional[str] = Query(None, description="Filter by network (VISA, MASTERCARD, RUPAY, AMEX)"),
    fee_type: Optional[str] = Query(None, description="Filter: 'free', 'lt1k', '1k5k', 'gt5k'"),
    is_popular: Optional[bool] = Query(None, description="Filter popular cards"),
    sort_by: Optional[str] = Query("popular", description="Sort by 'popular', 'return', 'fee_asc', 'fee_desc', 'name'"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves paginated cards matching multifaceted filter criteria."""
    query_params = CardFilterQuery(
        search=search,
        bank_slug=bank_slug,
        network=network,
        fee_type=fee_type,
        is_popular=is_popular,
        sort_by=sort_by,
        page=page,
        limit=limit,
    )
    items, meta = await card_service.get_filtered_cards(db, query_params)
    return ApiResponse(
        data=items,
        meta=meta,
    )


@router.get("/{slug}", response_model=ApiResponse[CardDetailResponse])
async def get_card_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    """Retrieves full details and available perk tabs for a specific card."""
    card = await card_service.get_card_by_slug(db, slug)
    return ApiResponse(data=card)


@router.get("/{slug}/tabs/{tab_name}", response_model=ApiResponse[CardTabResponse])
async def get_card_tab(slug: str, tab_name: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieves deep tab details for a card.
    Tab must be one of:
    - earn-categories
    - benefits-and-offers
    - lounge-access
    - milestones
    - redemption-options
    """
    tab = await card_service.get_card_tab(db, slug, tab_name)
    return ApiResponse(data=tab)
