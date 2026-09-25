"""
Card Catalog & Filter Service.
High-speed data access with Upstash Redis cache-aside caching.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.redis_client import redis_service
from app.models.bank import Bank
from app.models.card import CreditCard
from app.models.card_tab import CardTab
from app.models.category import SpendCategory
from app.schemas.card import (
    CardDetailResponse,
    CardFilterQuery,
    CardSummaryResponse,
    CardTabResponse,
)
from app.schemas.common import PaginationMeta


class CardService:
    """Service layer for querying card catalogs, details, and filter facets."""

    def _generate_cache_key(self, prefix: str, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        hashed = hashlib.md5(serialized.encode("utf-8")).hexdigest()
        return f"{prefix}:{hashed}"

    async def get_filtered_cards(
        self, db: AsyncSession, query_params: CardFilterQuery
    ) -> tuple[List[CardSummaryResponse], PaginationMeta]:
        cache_key = self._generate_cache_key("catalog:cards", query_params.model_dump())
        cached = await redis_service.get_json(cache_key)
        if cached:
            items = [CardSummaryResponse(**item) for item in cached["items"]]
            meta = PaginationMeta(**cached["meta"])
            return items, meta

        # Construct SQLAlchemy query
        stmt = select(CreditCard).options(selectinload(CreditCard.bank))

        # Filter: Search query
        if query_params.search:
            search_term = f"%{query_params.search}%"
            stmt = stmt.join(Bank, CreditCard.bank_id == Bank.id).where(
                or_(
                    CreditCard.title.ilike(search_term),
                    CreditCard.display_name.ilike(search_term),
                    Bank.name.ilike(search_term),
                )
            )

        # Filter: Bank Slug
        if query_params.bank_slug:
            stmt = stmt.join(Bank, CreditCard.bank_id == Bank.id).where(
                Bank.slug == query_params.bank_slug.lower()
            )

        # Filter: Network
        if query_params.network:
            stmt = stmt.where(CreditCard.network_type == query_params.network.upper())

        # Filter: Fee type
        if query_params.fee_type:
            ft = query_params.fee_type.lower()
            if ft == "free":
                stmt = stmt.where(CreditCard.joining_fee == 0.0)
            elif ft == "lt1k":
                stmt = stmt.where(CreditCard.joining_fee < 1000.0)
            elif ft == "1k5k":
                stmt = stmt.where(
                    CreditCard.joining_fee >= 1000.0, CreditCard.joining_fee <= 5000.0
                )
            elif ft == "gt5k":
                stmt = stmt.where(CreditCard.joining_fee > 5000.0)

        # Filter: Popular
        if query_params.is_popular is not None:
            stmt = stmt.where(CreditCard.is_popular == query_params.is_popular)

        # Count total items matching criteria
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # Sorting
        sort_by = query_params.sort_by or "popular"
        if sort_by == "return":
            stmt = stmt.order_by(desc(CreditCard.return_max_percent))
        elif sort_by == "fee_asc":
            stmt = stmt.order_by(CreditCard.joining_fee.asc())
        elif sort_by == "fee_desc":
            stmt = stmt.order_by(CreditCard.joining_fee.desc())
        elif sort_by == "name":
            stmt = stmt.order_by(CreditCard.title.asc())
        else:
            # Default popular & highest return
            stmt = stmt.order_by(
                desc(CreditCard.is_popular), desc(CreditCard.return_max_percent)
            )

        # Pagination
        offset = (query_params.page - 1) * query_params.limit
        stmt = stmt.offset(offset).limit(query_params.limit)

        result = await db.execute(stmt)
        cards = result.scalars().all()

        total_pages = (total + query_params.limit - 1) // query_params.limit if total > 0 else 1
        meta = PaginationMeta(
            total=total,
            page=query_params.page,
            limit=query_params.limit,
            total_pages=total_pages,
            has_next=query_params.page < total_pages,
            has_prev=query_params.page > 1,
        )

        items = []
        for c in cards:
            items.append(
                CardSummaryResponse(
                    id=c.id,
                    slug=c.slug,
                    title=c.title,
                    display_name=c.display_name,
                    bank_name=c.bank.name if c.bank else None,
                    bank_slug=c.bank.slug if c.bank else None,
                    bank_logo_url=c.bank.logo_url if c.bank else None,
                    web_logo_url=c.web_logo_url,
                    card_image_url=c.card_image_url,
                    joining_fee=c.joining_fee,
                    renewal_fee=c.renewal_fee,
                    forex_markup_percent=c.forex_markup_percent,
                    return_percentage_raw=c.return_percentage_raw,
                    return_min_percent=c.return_min_percent,
                    return_max_percent=c.return_max_percent,
                    network_type=c.network_type,
                    lounge_types=c.lounge_types or [],
                    benefit_types=c.benefit_types or [],
                    category_slugs=c.category_slugs or [],
                    is_popular=c.is_popular,
                    is_currently_issuing=c.is_currently_issuing,
                )
            )

        # Store in Redis cache (1 hour)
        await redis_service.set_json(
            cache_key,
            {
                "items": [item.model_dump() for item in items],
                "meta": meta.model_dump(),
            },
            ttl_seconds=settings.REDIS_CACHE_TTL_SECONDS,
        )

        return items, meta

    async def get_card_by_slug(self, db: AsyncSession, slug: str) -> CardDetailResponse:
        cache_key = f"catalog:card:{slug}"
        cached = await redis_service.get_json(cache_key)
        if cached:
            return CardDetailResponse(**cached)

        stmt = (
            select(CreditCard)
            .options(selectinload(CreditCard.bank), selectinload(CreditCard.tabs))
            .where(CreditCard.slug == slug)
        )
        card = (await db.execute(stmt)).scalar_one_or_none()
        if not card:
            raise NotFoundError(f"Credit card with slug '{slug}' not found.")

        available_tabs = [t.tab_name for t in card.tabs]

        response = CardDetailResponse(
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
            apr_percent=card.apr_percent,
            add_on_card_fee=card.add_on_card_fee,
            return_percentage_raw=card.return_percentage_raw,
            return_min_percent=card.return_min_percent,
            return_max_percent=card.return_max_percent,
            network_type=card.network_type,
            lounge_types=card.lounge_types or [],
            benefit_types=card.benefit_types or [],
            category_slugs=card.category_slugs or [],
            is_fd_card=card.is_fd_card,
            is_business_card=card.is_business_card,
            is_popular=card.is_popular,
            is_currently_issuing=card.is_currently_issuing,
            apply_link=card.apply_link,
            overview_text=card.overview_text,
            best_suited=card.best_suited,
            available_tabs=available_tabs,
            bank=card.bank,
        )

        await redis_service.set_json(
            cache_key, response.model_dump(), ttl_seconds=settings.REDIS_CACHE_TTL_SECONDS
        )
        return response

    async def get_card_tab(
        self, db: AsyncSession, slug: str, tab_name: str
    ) -> CardTabResponse:
        cache_key = f"catalog:card:{slug}:tab:{tab_name}"
        cached = await redis_service.get_json(cache_key)
        if cached:
            return CardTabResponse(**cached)

        stmt = (
            select(CardTab)
            .join(CreditCard, CardTab.card_id == CreditCard.id)
            .where(CreditCard.slug == slug, CardTab.tab_name == tab_name)
        )
        tab = (await db.execute(stmt)).scalar_one_or_none()
        if not tab:
            raise NotFoundError(
                f"Tab '{tab_name}' not found for card '{slug}'."
            )

        response = CardTabResponse(
            card_id=tab.card_id,
            card_slug=slug,
            tab_name=tab.tab_name,
            content=tab.raw_content,
        )

        await redis_service.set_json(
            cache_key, response.model_dump(), ttl_seconds=settings.REDIS_CACHE_TTL_SECONDS
        )
        return response

    async def get_all_banks(self, db: AsyncSession) -> List[Bank]:
        cache_key = "calc:banks"
        cached = await redis_service.get_json(cache_key)
        if cached:
            return [Bank(**b) for b in cached]

        stmt = select(Bank).order_by(Bank.name.asc())
        banks = (await db.execute(stmt)).scalars().all()

        bank_dicts = [
            {
                "id": b.id,
                "slug": b.slug,
                "name": b.name,
                "logo_url": b.logo_url,
                "savesage_bank_id": b.savesage_bank_id,
            }
            for b in banks
        ]
        await redis_service.set_json(cache_key, bank_dicts, ttl_seconds=86400)
        return banks

    async def get_all_categories(self, db: AsyncSession) -> List[SpendCategory]:
        cache_key = "calc:categories"
        cached = await redis_service.get_json(cache_key)
        if cached:
            return [SpendCategory(**c) for c in cached]

        stmt = select(SpendCategory).order_by(SpendCategory.name.asc())
        categories = (await db.execute(stmt)).scalars().all()

        cat_dicts = [
            {
                "id": c.id,
                "slug": c.slug,
                "name": c.name,
                "icon_url": c.icon_url,
                "savesage_category_id": c.savesage_category_id,
            }
            for c in categories
        ]
        await redis_service.set_json(cache_key, cat_dicts, ttl_seconds=86400)
        return categories


# Global Singleton Card Service
card_service = CardService()
