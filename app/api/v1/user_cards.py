"""
User Cards Wallet API Router.
"""

from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.user_card import (
    AddUserCardRequest,
    UpdateUserCardRequest,
    UserCardResponse,
)
from app.services.user_card_service import user_card_service

router = APIRouter(prefix="/user-cards", tags=["User Wallet"])


@router.get("", response_model=ApiResponse[List[UserCardResponse]])
async def list_user_cards(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieves all credit cards in the authenticated user's portfolio."""
    cards = await user_card_service.list_cards(db, user.id)
    return ApiResponse(data=cards)


@router.post("", response_model=ApiResponse[UserCardResponse], status_code=status.HTTP_201_CREATED)
async def add_card_to_wallet(
    req: AddUserCardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Adds a credit card from our catalog to the user's personal wallet."""
    card = await user_card_service.add_card(db, user.id, req)
    return ApiResponse(
        message="Card added to wallet successfully.",
        data=card,
    )


@router.patch("/{user_card_id}", response_model=ApiResponse[UserCardResponse])
async def update_user_card(
    user_card_id: int,
    req: UpdateUserCardRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates nickname, last 4 digits, or billing cycle of a wallet card."""
    updated = await user_card_service.update_card(db, user.id, user_card_id, req)
    return ApiResponse(
        message="Card updated successfully.",
        data=updated,
    )


@router.delete("/{user_card_id}", response_model=ApiResponse[None])
async def remove_user_card(
    user_card_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Removes a card from the user's wallet."""
    await user_card_service.remove_card(db, user.id, user_card_id)
    return ApiResponse(
        message="Card removed from wallet.",
        data=None,
    )
