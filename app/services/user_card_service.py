"""
User Wallet Service.
Manages adding, updating, and removing cards from a user's wallet.
Zero PCI-DSS scope: Card numbers are held on device in the Flutter app.
"""

from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import CreditCard
from app.models.user_card import UserCard
from app.schemas.card import CardSummaryResponse
from app.schemas.user_card import (
    AddUserCardRequest,
    UpdateUserCardRequest,
    UserCardResponse,
)


class UserCardService:
    async def add_card(
        self, db: AsyncSession, user_id: int, req: AddUserCardRequest
    ) -> UserCardResponse:
        # Verify Card Exists
        card_stmt = select(CreditCard).options(selectinload(CreditCard.bank)).where(CreditCard.id == req.card_id)
        card = (await db.execute(card_stmt)).scalar_one_or_none()
        if not card:
            raise NotFoundError(f"Credit card with ID {req.card_id} does not exist.")

        # Check Duplicate
        dup_stmt = select(UserCard).where(
            UserCard.user_id == user_id,
            UserCard.card_id == req.card_id,
            UserCard.nickname == req.nickname,
        )
        existing = (await db.execute(dup_stmt)).scalar_one_or_none()
        if existing:
            raise ConflictError("This card is already added to your wallet with the same nickname.")

        user_card = UserCard(
            user_id=user_id,
            card_id=req.card_id,
            nickname=req.nickname or card.display_name,
            last_4_digits=req.last_4_digits,
            billing_cycle_day=req.billing_cycle_day,
            is_active=True,
        )
        db.add(user_card)
        await db.commit()
        await db.refresh(user_card)

        return self._to_response(user_card, card)

    async def list_cards(self, db: AsyncSession, user_id: int) -> List[UserCardResponse]:
        stmt = (
            select(UserCard)
            .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
            .where(UserCard.user_id == user_id)
            .order_by(UserCard.created_at.desc())
        )
        results = (await db.execute(stmt)).scalars().all()
        return [self._to_response(uc, uc.card) for uc in results]

    async def update_card(
        self, db: AsyncSession, user_id: int, user_card_id: int, req: UpdateUserCardRequest
    ) -> UserCardResponse:
        stmt = (
            select(UserCard)
            .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
            .where(UserCard.id == user_card_id, UserCard.user_id == user_id)
        )
        uc = (await db.execute(stmt)).scalar_one_or_none()
        if not uc:
            raise NotFoundError("Card not found in your wallet.")

        if req.nickname is not None:
            uc.nickname = req.nickname
        if req.last_4_digits is not None:
            uc.last_4_digits = req.last_4_digits
        if req.billing_cycle_day is not None:
            uc.billing_cycle_day = req.billing_cycle_day
        if req.is_active is not None:
            uc.is_active = req.is_active

        await db.commit()
        await db.refresh(uc)
        return self._to_response(uc, uc.card)

    async def remove_card(self, db: AsyncSession, user_id: int, user_card_id: int) -> bool:
        stmt = select(UserCard).where(
            UserCard.id == user_card_id, UserCard.user_id == user_id
        )
        uc = (await db.execute(stmt)).scalar_one_or_none()
        if not uc:
            raise NotFoundError("Card not found in your wallet.")

        await db.delete(uc)
        await db.commit()
        return True

    def _to_response(self, uc: UserCard, card: CreditCard) -> UserCardResponse:
        card_summary = None
        if card:
            card_summary = CardSummaryResponse(
                id=card.id,
                slug=card.slug,
                title=card.title,
                display_name=card.display_name,
                bank_name=card.bank.name if card.bank else None,
                bank_slug=card.bank.slug if card.bank else None,
                bank_logo_url=card.bank.logo_url if card.bank else None,
                web_logo_url=card.web_logo_url,
                card_image_url=card.card_image_url,
                joining_fee=card.joining_fee,
                renewal_fee=card.renewal_fee,
                forex_markup_percent=card.forex_markup_percent,
                return_percentage_raw=card.return_percentage_raw,
                return_min_percent=card.return_min_percent,
                return_max_percent=card.return_max_percent,
                network_type=card.network_type,
                lounge_types=card.lounge_types or [],
                benefit_types=card.benefit_types or [],
                category_slugs=card.category_slugs or [],
                is_popular=card.is_popular,
                is_currently_issuing=card.is_currently_issuing,
            )

        return UserCardResponse(
            id=uc.id,
            user_id=uc.user_id,
            card_id=uc.card_id,
            nickname=uc.nickname,
            last_4_digits=uc.last_4_digits,
            billing_cycle_day=uc.billing_cycle_day,
            is_active=uc.is_active,
            card=card_summary,
        )


# Global Singleton User Card Service
user_card_service = UserCardService()
