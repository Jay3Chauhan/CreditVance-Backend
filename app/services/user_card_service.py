"""
User Wallet Service.
Manages adding, updating, reordering, and removing cards from a user's wallet.
Zero PCI-DSS scope: Full card numbers and CVVs are held on device in the Flutter app.
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

        statement_day = req.statement_day or req.billing_cycle_day
        billing_cycle_day = req.billing_cycle_day or req.statement_day

        user_card = UserCard(
            user_id=user_id,
            card_id=req.card_id,
            nickname=req.nickname or card.display_name,
            last_4_digits=req.last_4_digits,
            billing_cycle_day=billing_cycle_day,
            statement_day=statement_day,
            due_day=req.due_day,
            sort_order=req.sort_order if req.sort_order is not None else 0,
            is_active=True,
        )
        db.add(user_card)
        await db.commit()
        await db.refresh(user_card)

        return self._to_response(user_card, card)

    async def list_cards(self, db: AsyncSession, user_id: int) -> List[UserCardResponse]:
        """Retrieves all wallet cards for user ordered by sort_order, then ID."""
        stmt = (
            select(UserCard)
            .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
            .where(UserCard.user_id == user_id)
            .order_by(UserCard.sort_order.asc(), UserCard.id.asc())
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
            uc.nickname = req.nickname.strip() if req.nickname else uc.nickname
        if req.last_4_digits is not None:
            uc.last_4_digits = req.last_4_digits
        if req.billing_cycle_day is not None:
            uc.billing_cycle_day = req.billing_cycle_day
            if req.statement_day is None:
                uc.statement_day = req.billing_cycle_day
        if req.statement_day is not None:
            uc.statement_day = req.statement_day
            if req.billing_cycle_day is None:
                uc.billing_cycle_day = req.statement_day
        if req.due_day is not None:
            uc.due_day = req.due_day
        if req.sort_order is not None:
            uc.sort_order = req.sort_order
        if req.is_active is not None:
            uc.is_active = req.is_active

        await db.commit()
        await db.refresh(uc)
        return self._to_response(uc, uc.card)

    async def reorder_wallet(
        self, db: AsyncSession, user_id: int, ids: List[int]
    ) -> List[UserCardResponse]:
        """
        Updates the sort_order of user's wallet cards according to provided IDs list.
        Supports both user_card.id and card_id matching for maximum client tolerance.
        """
        stmt = (
            select(UserCard)
            .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
            .where(UserCard.user_id == user_id)
        )
        user_cards = (await db.execute(stmt)).scalars().all()
        id_to_card = {uc.id: uc for uc in user_cards}
        card_id_to_card = {uc.card_id: uc for uc in user_cards}

        updated_any = False
        for order_idx, target_id in enumerate(ids):
            target_uc = id_to_card.get(target_id) or card_id_to_card.get(target_id)
            if target_uc:
                target_uc.sort_order = order_idx
                updated_any = True

        if updated_any:
            await db.commit()

        return await self.list_cards(db, user_id)

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
                card_image_url=card.card_image_url or card.web_logo_url,
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
            billing_cycle_day=uc.billing_cycle_day or uc.statement_day,
            statement_day=uc.statement_day or uc.billing_cycle_day,
            due_day=uc.due_day,
            sort_order=uc.sort_order if uc.sort_order is not None else 0,
            is_active=uc.is_active,
            created_at=uc.created_at,
            updated_at=uc.updated_at,
            card=card_summary,
        )


# Global Singleton User Card Service
user_card_service = UserCardService()
