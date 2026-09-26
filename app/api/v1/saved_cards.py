"""
Shortlist of catalog cards the user is considering.
Distinct from the wallet of cards they already hold.
"""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.content import SaveCardRequest, SavedCardResponse
from app.services.discovery_service import discovery_service

router = APIRouter(prefix="/saved-cards", tags=["Saved Cards"])


@router.get("", response_model=ApiResponse[List[SavedCardResponse]])
async def list_saved_cards(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cards on the signed-in user's shortlist, newest first."""
    items = await discovery_service.list_saved(db, user.id)
    return ApiResponse(data=items)


@router.post("", response_model=ApiResponse[SavedCardResponse], status_code=status.HTTP_201_CREATED)
async def save_card(
    req: SaveCardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adds a catalog card to the shortlist. Saving the same card again is safe."""
    item = await discovery_service.save_card(db, user.id, req.card_id)
    return ApiResponse(message="Card saved to your shortlist.", data=item)


@router.delete("/{card_id}", response_model=ApiResponse[None])
async def remove_saved_card(
    card_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Removes a catalog card from the shortlist. `card_id` is the catalog id, not the shortlist row id."""
    await discovery_service.remove_saved(db, user.id, card_id)
    return ApiResponse(message="Card removed from your shortlist.", data=None)
