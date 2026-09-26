"""
Single payload for the home screen.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_optional_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.content import HomeFeedResponse
from app.services.content_service import content_service

router = APIRouter(prefix="/home", tags=["Home"])


@router.get("", response_model=ApiResponse[HomeFeedResponse])
async def get_home_feed(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hero banners, strip banners, featured guides, popular cards, categories,
    curated collections, and quick actions. Guests receive audience=guest banners;
    signed-in users also receive member banners. Rows marked all are included for both.
    """
    feed = await content_service.home_feed(db, user)
    return ApiResponse(data=feed)
