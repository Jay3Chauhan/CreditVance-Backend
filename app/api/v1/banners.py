"""
Public banner placements for home, catalog, wallet, and advisor.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.content import BannerResponse, TrackEventRequest
from app.services.content_service import content_service

router = APIRouter(prefix="/banners", tags=["Banners"])


@router.get("", response_model=ApiResponse[List[BannerResponse]])
async def list_banners(
    placement: Optional[str] = Query(
        None,
        description="home_hero, home_strip, catalog_top, wallet, card_detail, advisor",
    ),
    audience: Optional[str] = Query(
        None,
        description="guest or member. Rows marked all are always included.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Live banners for a placement. Inactive and out-of-schedule rows are omitted."""
    banners = await content_service.list_banners(db, placement=placement, audience=audience)
    return ApiResponse(data=banners)


@router.post("/{banner_id}/track", response_model=ApiResponse[BannerResponse])
async def track_banner(
    banner_id: int,
    req: TrackEventRequest,
    db: AsyncSession = Depends(get_db),
):
    """Records an impression or a click. Safe to call without authentication."""
    updated = await content_service.track_banner(db, banner_id, req.event)
    return ApiResponse(message="Banner event recorded.", data=updated)
