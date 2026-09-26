"""
Editorial guides and published offers.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.content import PromotionResponse, TrackEventRequest
from app.services.content_service import content_service

router = APIRouter(prefix="/promotions", tags=["Promotions"])


@router.get("", response_model=ApiResponse[List[PromotionResponse]])
async def list_promotions(
    featured: Optional[bool] = Query(None, description="Only home-featured rows"),
    promo_type: Optional[str] = Query(None, description="editorial, feature, welcome_bonus, cashback, ..."),
    category_slug: Optional[str] = Query(None, description="Match a spend category such as Dining"),
    card_slug: Optional[str] = Query(
        None,
        description="Promotions linked to this card, or to one of the card's categories",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Live promotions. Use card_slug on the card detail screen."""
    items = await content_service.list_promotions(
        db,
        featured=featured,
        promo_type=promo_type,
        category_slug=category_slug,
        card_slug=card_slug,
    )
    return ApiResponse(data=items)


@router.get("/{slug}", response_model=ApiResponse[PromotionResponse])
async def get_promotion(slug: str, db: AsyncSession = Depends(get_db)):
    """One promotion, including description and terms."""
    item = await content_service.get_promotion(db, slug)
    return ApiResponse(data=item)


@router.post("/{promotion_id}/track", response_model=ApiResponse[PromotionResponse])
async def track_promotion(
    promotion_id: int,
    req: TrackEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Records an impression or a click."""
    updated = await content_service.track_promotion(db, promotion_id, req.event)
    return ApiResponse(message="Promotion event recorded.", data=updated)
