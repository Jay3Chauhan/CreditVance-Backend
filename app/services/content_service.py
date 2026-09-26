"""
Banners, promotions, and the aggregated home feed.
Public reads only return rows that are active and inside their schedule.
The first read seeds editorial content when a table is empty.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.banner import Banner
from app.models.card import CreditCard
from app.models.promotion import Promotion
from app.models.user import User
from app.schemas.card import CardFilterQuery
from app.schemas.content import (
    BannerResponse,
    BannerUpdateRequest,
    BannerWriteRequest,
    ContentAction,
    HomeCollection,
    HomeFeedResponse,
    PromotionResponse,
    PromotionUpdateRequest,
    PromotionWriteRequest,
    QuickAction,
)
from app.services.card_service import card_service

def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_live(is_active: bool, starts_at: datetime | None, ends_at: datetime | None, now: datetime) -> bool:
    if not is_active:
        return False
    start = _as_utc(starts_at)
    end = _as_utc(ends_at)
    if start and start > now:
        return False
    if end and end < now:
        return False
    return True


def _audience_visible(row_audience: str, requested: str | None) -> bool:
    if requested is None or row_audience == "all":
        return True
    return row_audience == requested


class ContentService:
    def banner_response(self, row: Banner) -> BannerResponse:
        return BannerResponse(
            id=row.id,
            slug=row.slug,
            title=row.title,
            subtitle=row.subtitle,
            image_url=row.image_url,
            placement=row.placement,
            badge_text=row.badge_text,
            background_color=row.background_color,
            accent_color=row.accent_color,
            priority=row.priority,
            audience=row.audience,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            action=ContentAction(
                type=row.action_type,
                target=row.action_target,
                label=row.cta_label,
            ),
            impression_count=row.impression_count,
            click_count=row.click_count,
        )

    def promotion_response(self, row: Promotion) -> PromotionResponse:
        card = row.card
        return PromotionResponse(
            id=row.id,
            slug=row.slug,
            title=row.title,
            summary=row.summary,
            description=row.description,
            image_url=row.image_url,
            badge=row.badge,
            promo_type=row.promo_type,
            highlight_value=row.highlight_value,
            terms=row.terms,
            card_id=row.card_id,
            card_slug=card.slug if card else None,
            card_title=card.display_name if card else None,
            category_slug=row.category_slug,
            priority=row.priority,
            is_featured=row.is_featured,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            action=ContentAction(
                type=row.action_type,
                target=row.action_target,
                label=row.cta_label,
            ),
            impression_count=row.impression_count,
            click_count=row.click_count,
        )

    async def ensure_seeded(self, db: AsyncSession) -> None:
        banner_count = (await db.execute(select(func.count()).select_from(Banner))).scalar() or 0
        if banner_count == 0:
            for payload in _SEED_BANNERS:
                db.add(Banner(**payload))
        promo_count = (await db.execute(select(func.count()).select_from(Promotion))).scalar() or 0
        if promo_count == 0:
            for payload in _SEED_PROMOTIONS:
                db.add(Promotion(**payload))
        if banner_count == 0 or promo_count == 0:
            await db.commit()

    async def list_banners(
        self,
        db: AsyncSession,
        placement: str | None = None,
        audience: str | None = None,
        include_inactive: bool = False,
    ) -> list[BannerResponse]:
        await self.ensure_seeded(db)
        rows = (await db.execute(select(Banner).order_by(Banner.priority.desc(), Banner.id.asc()))).scalars().all()
        now = datetime.now(timezone.utc)
        visible: list[BannerResponse] = []
        for row in rows:
            if placement and row.placement != placement:
                continue
            if not include_inactive and not _is_live(row.is_active, row.starts_at, row.ends_at, now):
                continue
            if not include_inactive and not _audience_visible(row.audience, audience):
                continue
            visible.append(self.banner_response(row))
        return visible

    async def track_banner(self, db: AsyncSession, banner_id: int, event: str) -> BannerResponse:
        row = await db.get(Banner, banner_id)
        if not row:
            raise NotFoundError(f"Banner {banner_id} not found.")
        if event == "click":
            row.click_count += 1
        else:
            row.impression_count += 1
        await db.commit()
        await db.refresh(row)
        return self.banner_response(row)

    async def create_banner(self, db: AsyncSession, req: BannerWriteRequest) -> BannerResponse:
        existing = (await db.execute(select(Banner).where(Banner.slug == req.slug))).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Banner slug '{req.slug}' already exists.")
        row = Banner(**req.model_dump())
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return self.banner_response(row)

    async def update_banner(
        self, db: AsyncSession, banner_id: int, req: BannerUpdateRequest
    ) -> BannerResponse:
        row = await db.get(Banner, banner_id)
        if not row:
            raise NotFoundError(f"Banner {banner_id} not found.")
        for key, value in req.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return self.banner_response(row)

    async def delete_banner(self, db: AsyncSession, banner_id: int) -> None:
        row = await db.get(Banner, banner_id)
        if not row:
            raise NotFoundError(f"Banner {banner_id} not found.")
        await db.delete(row)
        await db.commit()

    async def list_promotions(
        self,
        db: AsyncSession,
        *,
        featured: bool | None = None,
        promo_type: str | None = None,
        category_slug: str | None = None,
        card_slug: str | None = None,
        include_inactive: bool = False,
    ) -> list[PromotionResponse]:
        await self.ensure_seeded(db)
        stmt = select(Promotion).options(selectinload(Promotion.card)).order_by(
            Promotion.priority.desc(), Promotion.id.asc()
        )
        rows = (await db.execute(stmt)).scalars().all()
        card_categories: set[str] = set()
        linked_card_id: int | None = None
        if card_slug:
            card = (
                await db.execute(select(CreditCard).where(CreditCard.slug == card_slug))
            ).scalar_one_or_none()
            if not card:
                raise NotFoundError(f"Credit card with slug '{card_slug}' not found.")
            linked_card_id = card.id
            card_categories = {slug.lower() for slug in (card.category_slugs or [])}

        now = datetime.now(timezone.utc)
        visible: list[PromotionResponse] = []
        for row in rows:
            if not include_inactive and not _is_live(row.is_active, row.starts_at, row.ends_at, now):
                continue
            if featured is True and not row.is_featured:
                continue
            if promo_type and row.promo_type != promo_type:
                continue
            if category_slug and (row.category_slug or "").lower() != category_slug.lower():
                continue
            if card_slug:
                matches_card = row.card_id == linked_card_id
                matches_category = bool(
                    row.category_slug and row.category_slug.lower() in card_categories
                )
                if not matches_card and not matches_category:
                    continue
            visible.append(self.promotion_response(row))
        return visible

    async def get_promotion(self, db: AsyncSession, slug: str) -> PromotionResponse:
        await self.ensure_seeded(db)
        stmt = (
            select(Promotion)
            .options(selectinload(Promotion.card))
            .where(Promotion.slug == slug)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise NotFoundError(f"Promotion '{slug}' not found.")
        return self.promotion_response(row)

    async def track_promotion(self, db: AsyncSession, promotion_id: int, event: str) -> PromotionResponse:
        stmt = select(Promotion).options(selectinload(Promotion.card)).where(Promotion.id == promotion_id)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise NotFoundError(f"Promotion {promotion_id} not found.")
        if event == "click":
            row.click_count += 1
        else:
            row.impression_count += 1
        await db.commit()
        await db.refresh(row)
        return self.promotion_response(row)

    async def create_promotion(self, db: AsyncSession, req: PromotionWriteRequest) -> PromotionResponse:
        existing = (
            await db.execute(select(Promotion).where(Promotion.slug == req.slug))
        ).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Promotion slug '{req.slug}' already exists.")
        if req.card_id is not None:
            card = await db.get(CreditCard, req.card_id)
            if not card:
                raise NotFoundError(f"Credit card {req.card_id} not found.")
        row = Promotion(**req.model_dump())
        db.add(row)
        await db.commit()
        await db.refresh(row)
        stmt = select(Promotion).options(selectinload(Promotion.card)).where(Promotion.id == row.id)
        loaded = (await db.execute(stmt)).scalar_one()
        return self.promotion_response(loaded)

    async def update_promotion(
        self, db: AsyncSession, promotion_id: int, req: PromotionUpdateRequest
    ) -> PromotionResponse:
        row = await db.get(Promotion, promotion_id)
        if not row:
            raise NotFoundError(f"Promotion {promotion_id} not found.")
        changes: dict[str, Any] = req.model_dump(exclude_unset=True)
        if "card_id" in changes and changes["card_id"] is not None:
            card = await db.get(CreditCard, changes["card_id"])
            if not card:
                raise NotFoundError(f"Credit card {changes['card_id']} not found.")
        for key, value in changes.items():
            setattr(row, key, value)
        await db.commit()
        stmt = select(Promotion).options(selectinload(Promotion.card)).where(Promotion.id == promotion_id)
        loaded = (await db.execute(stmt)).scalar_one()
        return self.promotion_response(loaded)

    async def delete_promotion(self, db: AsyncSession, promotion_id: int) -> None:
        row = await db.get(Promotion, promotion_id)
        if not row:
            raise NotFoundError(f"Promotion {promotion_id} not found.")
        await db.delete(row)
        await db.commit()

    async def home_feed(self, db: AsyncSession, user: Optional[User]) -> HomeFeedResponse:
        audience = "member" if user else "guest"
        hero = await self.list_banners(db, placement="home_hero", audience=audience)
        strip = await self.list_banners(db, placement="home_strip", audience=audience)
        featured = await self.list_promotions(db, featured=True)
        popular, _ = await card_service.get_filtered_cards(
            db, CardFilterQuery(is_popular=True, sort_by="popular", page=1, limit=8)
        )
        categories = await card_service.get_all_categories(db)
        lifetime_free, _ = await card_service.get_filtered_cards(
            db, CardFilterQuery(fee_type="free", sort_by="return_desc", page=1, limit=6)
        )
        lounge, _ = await card_service.get_filtered_cards(
            db, CardFilterQuery(has_lounge=True, sort_by="return_desc", page=1, limit=6)
        )
        return HomeFeedResponse(
            hero_banners=hero,
            strip_banners=strip,
            featured_promotions=featured[:6],
            popular_cards=popular,
            categories=categories[:8],
            collections=[
                HomeCollection(
                    key="lifetime_free",
                    title="Lifetime free",
                    subtitle="No joining fee. Useful first cards and everyday backups.",
                    action=ContentAction(type="screen", target="/catalog?fee_type=free", label="See all"),
                    cards=lifetime_free,
                ),
                HomeCollection(
                    key="lounge",
                    title="Lounge access",
                    subtitle="Domestic and international lounges, sorted by return.",
                    action=ContentAction(
                        type="screen", target="/catalog?has_lounge=true", label="See all"
                    ),
                    cards=lounge,
                ),
            ],
            quick_actions=_QUICK_ACTIONS,
        )


_QUICK_ACTIONS = [
    QuickAction(
        key="advisor",
        title="Which card?",
        subtitle="Best card for this spend",
        icon_key="auto_awesome",
        action=ContentAction(type="screen", target="/advisor", label="Ask"),
    ),
    QuickAction(
        key="compare",
        title="Compare",
        subtitle="Fees, forex, and returns",
        icon_key="compare_arrows",
        action=ContentAction(type="screen", target="/compare", label="Compare"),
    ),
    QuickAction(
        key="calculator",
        title="Calculator",
        subtitle="Annual value after fees",
        icon_key="calculate",
        action=ContentAction(type="screen", target="/calculator", label="Calculate"),
    ),
    QuickAction(
        key="saved",
        title="Shortlist",
        subtitle="Cards you might apply for",
        icon_key="bookmark",
        action=ContentAction(type="screen", target="/saved", label="Open"),
    ),
]


_SEED_BANNERS: list[dict[str, Any]] = [
    {
        "slug": "advisor-hero",
        "title": "Which card should you use?",
        "subtitle": "Rank the cards you hold for this exact spend.",
        "placement": "home_hero",
        "cta_label": "Ask advisor",
        "action_type": "screen",
        "action_target": "/advisor",
        "badge_text": "Smart",
        "background_color": "#0F2744",
        "accent_color": "#F4C430",
        "priority": 100,
        "is_active": True,
        "audience": "all",
    },
    {
        "slug": "compare-hero",
        "title": "Compare cards side by side",
        "subtitle": "Fees, forex, lounge access, and category returns.",
        "placement": "home_hero",
        "cta_label": "Compare",
        "action_type": "screen",
        "action_target": "/compare",
        "badge_text": "New",
        "background_color": "#1B3A2F",
        "accent_color": "#7DCEA0",
        "priority": 90,
        "is_active": True,
        "audience": "all",
    },
    {
        "slug": "calculator-strip",
        "title": "See the year, not the swipe",
        "subtitle": "Annual rewards, fee waiver, and what you actually keep.",
        "placement": "home_strip",
        "cta_label": "Calculate",
        "action_type": "screen",
        "action_target": "/calculator",
        "background_color": "#2C2140",
        "accent_color": "#C39BD3",
        "priority": 80,
        "is_active": True,
        "audience": "all",
    },
    {
        "slug": "lounge-catalog",
        "title": "Cards with lounge access",
        "subtitle": "Filter domestic and international lounges from the catalog.",
        "placement": "catalog_top",
        "cta_label": "Show lounge cards",
        "action_type": "screen",
        "action_target": "/catalog?has_lounge=true",
        "background_color": "#1A365D",
        "accent_color": "#63B3ED",
        "priority": 70,
        "is_active": True,
        "audience": "all",
    },
    {
        "slug": "wallet-dates",
        "title": "Never miss a due date",
        "subtitle": "Add the statement day and due day for each card you hold.",
        "placement": "wallet",
        "cta_label": "Set dates",
        "action_type": "screen",
        "action_target": "/wallet",
        "background_color": "#3D2914",
        "accent_color": "#F6AD55",
        "priority": 60,
        "is_active": True,
        "audience": "member",
    },
    {
        "slug": "international-advisor",
        "title": "Paying abroad?",
        "subtitle": "Forex markup is shown with 18% GST taken off the reward.",
        "placement": "advisor",
        "cta_label": "International mode",
        "action_type": "screen",
        "action_target": "/advisor?international=true",
        "background_color": "#1A202C",
        "accent_color": "#90CDF4",
        "priority": 50,
        "is_active": True,
        "audience": "all",
    },
]


_SEED_PROMOTIONS: list[dict[str, Any]] = [
    {
        "slug": "fee-waiver-guide",
        "title": "Will the annual fee be waived?",
        "summary": "Check the yearly spend a card needs before the renewal fee drops to zero.",
        "description": (
            "Open the annual calculator, enter a normal month of spending, and read "
            "fee_waived plus net_annual_value_inr. A high reward rate can still lose "
            "money if the renewal fee is not waived."
        ),
        "badge": "Guide",
        "promo_type": "editorial",
        "highlight_value": "Fee waiver",
        "terms": "Waiver thresholds come from card data when the issuer publishes them, otherwise from a documented estimate.",
        "cta_label": "Open calculator",
        "action_type": "screen",
        "action_target": "/calculator",
        "priority": 100,
        "is_featured": True,
        "is_active": True,
    },
    {
        "slug": "dining-picks",
        "title": "Best fit for dining",
        "summary": "Restaurant spends are one of the widest gaps between cards. Ask the advisor before you pay.",
        "description": "Use category Dining in the advisor, or sort the catalog by return and open earn-categories on the card.",
        "badge": "Dining",
        "promo_type": "editorial",
        "highlight_value": "Dining",
        "category_slug": "Dining",
        "cta_label": "Ask for dining",
        "action_type": "screen",
        "action_target": "/advisor?category=Dining",
        "priority": 90,
        "is_featured": True,
        "is_active": True,
    },
    {
        "slug": "zero-forex-edit",
        "title": "International spend, after forex",
        "summary": "A reward rate that ignores forex markup and GST overstates what you keep.",
        "description": "Turn on international mode. The advisor returns forex_markup_applied and subtracts that cost from the reward.",
        "badge": "Travel",
        "promo_type": "editorial",
        "highlight_value": "Forex + GST",
        "category_slug": "International",
        "cta_label": "Check a trip",
        "action_type": "screen",
        "action_target": "/advisor?international=true",
        "priority": 80,
        "is_featured": True,
        "is_active": True,
    },
    {
        "slug": "build-shortlist",
        "title": "Shortlist before you apply",
        "summary": "Save catalog cards you are considering. The wallet stays reserved for cards you already hold.",
        "description": "Saved cards sync to your account. Card numbers and CVVs are never part of this list.",
        "badge": "Shortlist",
        "promo_type": "feature",
        "highlight_value": "Saved cards",
        "cta_label": "Open shortlist",
        "action_type": "screen",
        "action_target": "/saved",
        "priority": 70,
        "is_featured": True,
        "is_active": True,
    },
]


content_service = ContentService()
