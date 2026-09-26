"""
Compare, search suggestions, saved-card shortlist, wallet insights, and FAQ.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.bank import Bank
from app.models.card import CreditCard
from app.models.saved_card import SavedCard
from app.models.user_card import UserCard
from app.schemas.card import CardSummaryResponse
from app.schemas.content import (
    CategoryPick,
    CompareCard,
    CompareCategoryRate,
    CompareResponse,
    CompareRow,
    FaqItem,
    FaqResponse,
    SavedCardResponse,
    SearchSuggestion,
    WalletInsightsResponse,
)
from app.schemas.device_token import CardReminderItem
from app.services.billing import days_until_day_of_month
from app.services.card_service import CATEGORY_METADATA, card_service

COMPARE_CATEGORIES = [
    "Dining",
    "Grocery",
    "Online Shopping",
    "Travel",
    "Fuel",
    "International",
]

FAQ_ITEMS: list[FaqItem] = [
    FaqItem(
        id="wallet-vs-shortlist",
        topic="wallet",
        question="What is the difference between my wallet and my shortlist?",
        answer=(
            "The wallet is cards you already hold. The shortlist is catalog cards you are "
            "considering. Card numbers and CVVs stay on this phone. The account only stores "
            "a nickname and the last 4 digits."
        ),
    ),
    FaqItem(
        id="which-card",
        topic="advisor",
        question="How does “which card should I use?” work?",
        answer=(
            "Send the spend category and amount to the advisor. If you are signed in, it ranks "
            "the cards in your wallet. Guests can send card_ids from the catalog. International "
            "spends subtract forex markup including 18% GST."
        ),
    ),
    FaqItem(
        id="annual-value",
        topic="calculator",
        question="Why can a high reward rate still be a poor card?",
        answer=(
            "The annual calculator subtracts the renewal fee unless your spend crosses the waiver "
            "threshold. Net value is rewards minus the fee you will actually pay."
        ),
    ),
    FaqItem(
        id="due-dates",
        topic="reminders",
        question="How do statement and due reminders work?",
        answer=(
            "Set statement_day and due_day (1–31) on each wallet card. The app reads "
            "GET /notifications/reminders. Days follow the real calendar, so a 31st due date "
            "lands on the last day of a shorter month."
        ),
    ),
    FaqItem(
        id="privacy",
        topic="privacy",
        question="Do you store my full card number?",
        answer=(
            "No. The backend never accepts a 16-digit card number or CVV. Keep those in the "
            "device secure storage. Account deletion removes the wallet, shortlist, and device tokens."
        ),
    ),
    FaqItem(
        id="offers",
        topic="promotions",
        question="Are the home banners bank offers?",
        answer=(
            "Seeded banners and guides are product explanations. A row with promo_type such as "
            "welcome_bonus or cashback is an offer an editor published, and it includes terms. "
            "Confirm the live offer on the bank site before you apply."
        ),
    ),
]


def _winner(values: dict[str, float | None], better: str) -> str | None:
    ranked = [(slug, value) for slug, value in values.items() if value is not None]
    if len(ranked) < 2:
        return None
    best = min(value for _, value in ranked) if better == "lower" else max(value for _, value in ranked)
    leaders = [slug for slug, value in ranked if value == best]
    if len(leaders) != 1:
        return None
    return leaders[0]


class DiscoveryService:
    async def compare(self, db: AsyncSession, slugs: list[str]) -> CompareResponse:
        ordered: list[str] = []
        for slug in slugs:
            cleaned = slug.strip()
            if cleaned and cleaned not in ordered:
                ordered.append(cleaned)
        if len(ordered) < 2:
            raise ValidationError("Provide at least two different card slugs to compare.")

        stmt = (
            select(CreditCard)
            .options(selectinload(CreditCard.bank), selectinload(CreditCard.tabs))
            .where(CreditCard.slug.in_(ordered))
        )
        found = {card.slug: card for card in (await db.execute(stmt)).scalars().all()}
        missing = [slug for slug in ordered if slug not in found]
        if missing:
            raise NotFoundError(f"Credit card with slug '{missing[0]}' not found.")

        cards: list[CompareCard] = []
        rate_maps: dict[str, dict[str, float]] = {}
        for slug in ordered:
            card = found[slug]
            summary = card_service.to_summary(card)
            point_value = card_service._resolve_point_value_inr(card)
            waiver = card_service._resolve_fee_waiver_spend(card, list(card.tabs or []))
            cards.append(
                CompareCard(
                    **summary.model_dump(),
                    best_suited=card.best_suited,
                    fee_waiver_spend=waiver,
                    point_value_inr=point_value,
                )
            )
            rate_maps[slug] = {
                item.category_slug: item.rate_percent
                for item in card_service.category_rates_from_card(card)
            }

        def row(key: str, label: str, better: str, values: dict[str, float | None]) -> CompareRow:
            return CompareRow(
                key=key,
                label=label,
                better=better,  # type: ignore[arg-type]
                values=values,
                winner_slug=_winner(values, better),
            )

        rows = [
            row(
                "joining_fee",
                "Joining fee",
                "lower",
                {card.slug: card.joining_fee for card in cards},
            ),
            row(
                "renewal_fee",
                "Renewal fee",
                "lower",
                {card.slug: card.renewal_fee for card in cards},
            ),
            row(
                "forex_markup_percent",
                "Forex markup",
                "lower",
                {card.slug: card.forex_markup_percent for card in cards},
            ),
            row(
                "return_max_percent",
                "Best published return",
                "higher",
                {card.slug: card.return_max_percent for card in cards},
            ),
            row(
                "point_value_inr",
                "Point value (INR)",
                "higher",
                {card.slug: card.point_value_inr for card in cards},
            ),
            row(
                "lounge_count",
                "Lounge types",
                "higher",
                {card.slug: float(len(card.lounge_types or [])) for card in cards},
            ),
        ]
        category_rates: list[CompareCategoryRate] = []
        for category in COMPARE_CATEGORIES:
            rates = {slug: rate_maps[slug].get(category, 0.0) for slug in ordered}
            category_rates.append(
                CompareCategoryRate(
                    category_slug=category,
                    rates=rates,
                    winner_slug=_winner(rates, "higher"),
                )
            )
        return CompareResponse(cards=cards, rows=rows, category_rates=category_rates)

    async def suggest(self, db: AsyncSession, query: str, limit: int) -> list[SearchSuggestion]:
        term = f"%{query.strip()}%"
        stmt = (
            select(CreditCard)
            .join(Bank, CreditCard.bank_id == Bank.id)
            .options(selectinload(CreditCard.bank))
            .where(
                or_(
                    CreditCard.title.ilike(term),
                    CreditCard.display_name.ilike(term),
                    CreditCard.slug.ilike(term),
                    Bank.name.ilike(term),
                )
            )
            .order_by(CreditCard.is_popular.desc(), CreditCard.return_max_percent.desc())
            .limit(limit)
        )
        cards = (await db.execute(stmt)).scalars().all()
        return [
            SearchSuggestion(
                id=card.id,
                slug=card.slug,
                title=card.title,
                display_name=card.display_name,
                bank_name=card.bank.name if card.bank else None,
                card_image_url=card.card_image_url or card.web_logo_url,
            )
            for card in cards
        ]

    async def list_saved(self, db: AsyncSession, user_id: int) -> list[SavedCardResponse]:
        stmt = (
            select(SavedCard)
            .options(selectinload(SavedCard.card).selectinload(CreditCard.bank))
            .where(SavedCard.user_id == user_id)
            .order_by(SavedCard.created_at.desc())
        )
        rows = (await db.execute(stmt)).scalars().all()
        return [self._saved_response(row) for row in rows if row.card]

    async def save_card(self, db: AsyncSession, user_id: int, card_id: int) -> SavedCardResponse:
        card = (
            await db.execute(
                select(CreditCard)
                .options(selectinload(CreditCard.bank))
                .where(CreditCard.id == card_id)
            )
        ).scalar_one_or_none()
        if not card:
            raise NotFoundError(f"Credit card {card_id} not found.")
        existing = (
            await db.execute(
                select(SavedCard).where(SavedCard.user_id == user_id, SavedCard.card_id == card_id)
            )
        ).scalar_one_or_none()
        if existing:
            existing.card = card
            return self._saved_response(existing)
        row = SavedCard(user_id=user_id, card_id=card_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        row.card = card
        return self._saved_response(row)

    async def remove_saved(self, db: AsyncSession, user_id: int, card_id: int) -> None:
        row = (
            await db.execute(
                select(SavedCard).where(SavedCard.user_id == user_id, SavedCard.card_id == card_id)
            )
        ).scalar_one_or_none()
        if not row:
            raise NotFoundError("That card is not on your shortlist.")
        await db.delete(row)
        await db.commit()

    def _saved_response(self, row: SavedCard) -> SavedCardResponse:
        summary: CardSummaryResponse = card_service.to_summary(row.card)
        return SavedCardResponse(
            id=row.id,
            card_id=row.card_id,
            saved_at=row.created_at,
            card=summary,
        )

    async def wallet_insights(self, db: AsyncSession, user_id: int) -> WalletInsightsResponse:
        stmt = (
            select(UserCard)
            .options(
                selectinload(UserCard.card).selectinload(CreditCard.bank),
                selectinload(UserCard.card).selectinload(CreditCard.tabs),
            )
            .where(UserCard.user_id == user_id, UserCard.is_active == True)
            .order_by(UserCard.sort_order.asc(), UserCard.id.asc())
        )
        holdings = (await db.execute(stmt)).scalars().all()
        if not holdings:
            return WalletInsightsResponse(
                card_count=0,
                total_renewal_fee_inr=0.0,
                lifetime_free_count=0,
                lounge_card_count=0,
                next_due=None,
                category_picks=[],
                empty_state_message="Add the cards you hold to see fees, lounge access, and the best card per category.",
            )

        total_fee = 0.0
        free_count = 0
        lounge_count = 0
        next_due: CardReminderItem | None = None
        picks: list[CategoryPick] = []
        rate_by_holding: list[tuple[UserCard, dict[str, float]]] = []

        for holding in holdings:
            card = holding.card
            if not card:
                continue
            total_fee += card.renewal_fee or 0.0
            if (card.joining_fee or 0) == 0 and (card.renewal_fee or 0) == 0:
                free_count += 1
            if card.lounge_types:
                lounge_count += 1
            rates = {
                item.category_slug: item.rate_percent
                for item in card_service.category_rates_from_card(card)
            }
            rate_by_holding.append((holding, rates))
            if holding.due_day:
                days = days_until_day_of_month(holding.due_day)
                if next_due is None or days < (next_due.days_until_due or 99):
                    nickname = holding.nickname or card.display_name
                    next_due = CardReminderItem(
                        user_card_id=holding.id,
                        nickname=nickname,
                        card_title=card.title,
                        bank_name=card.bank.name if card.bank else "Bank",
                        statement_day=holding.statement_day or holding.billing_cycle_day,
                        due_day=holding.due_day,
                        days_until_due=days,
                        reminder_type="due_date",
                        message=(
                            f"Payment for {nickname} is due today."
                            if days == 0
                            else f"Payment for {nickname} is due in {days} days."
                        ),
                    )

        for category in COMPARE_CATEGORIES:
            best: tuple[float, UserCard] | None = None
            for holding, rates in rate_by_holding:
                rate = rates.get(category, 0.0)
                if best is None or rate > best[0]:
                    best = (rate, holding)
            if best is None or not best[1].card:
                continue
            holding = best[1]
            picks.append(
                CategoryPick(
                    category_slug=category,
                    icon_key=CATEGORY_METADATA.get(category, {}).get("icon_key", "category"),
                    rate_percent=round(best[0], 2),
                    user_card_id=holding.id,
                    nickname=holding.nickname,
                    card=card_service.to_summary(holding.card),
                )
            )

        return WalletInsightsResponse(
            card_count=len(holdings),
            total_renewal_fee_inr=round(total_fee, 2),
            lifetime_free_count=free_count,
            lounge_card_count=lounge_count,
            next_due=next_due,
            category_picks=picks,
            empty_state_message=None,
        )

    def faq(self) -> FaqResponse:
        return FaqResponse(items=FAQ_ITEMS)


discovery_service = DiscoveryService()
