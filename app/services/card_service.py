"""
Card Catalog & Filter Service.
High-speed data access with Upstash Redis cache-aside caching.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import String, desc, func, or_, select
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
    CategoryEarnRateItem,
)
from app.schemas.category import CategoryResponse
from app.schemas.common import PaginationMeta
from app.services.crawler_service import VALID_TABS, crawler_service

# Standard Category Display Metadata (Icons & Ordering)
CATEGORY_METADATA: Dict[str, Dict[str, Any]] = {
    "Dining": {"icon_key": "restaurant", "display_order": 1},
    "Online Shopping": {"icon_key": "shopping_cart", "display_order": 2},
    "Travel": {"icon_key": "flight_takeoff", "display_order": 3},
    "Grocery": {"icon_key": "local_grocery_store", "display_order": 4},
    "Fuel": {"icon_key": "local_gas_station", "display_order": 5},
    "Utilities": {"icon_key": "receipt_long", "display_order": 6},
    "UPI": {"icon_key": "qr_code", "display_order": 7},
    "International": {"icon_key": "public", "display_order": 8},
    "Flights": {"icon_key": "flight", "display_order": 9},
    "Rent": {"icon_key": "home", "display_order": 10},
    "Education": {"icon_key": "school", "display_order": 11},
    "Insurance": {"icon_key": "shield", "display_order": 12},
    "Jewellery": {"icon_key": "diamond", "display_order": 13},
    "Gift Cards": {"icon_key": "card_giftcard", "display_order": 14},
    "Government": {"icon_key": "account_balance", "display_order": 15},
    "Offline Spends": {"icon_key": "storefront", "display_order": 16},
    "Wallets": {"icon_key": "account_balance_wallet", "display_order": 17},
}

ALL_STANDARD_TABS = [
    "earn-categories",
    "benefits-and-offers",
    "lounge-access",
    "milestones",
    "redemption-options",
]


class CardService:
    """Service layer for querying card catalogs, details, and filter facets."""

    def _generate_cache_key(self, prefix: str, data: Any) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        hashed = hashlib.md5(serialized.encode("utf-8")).hexdigest()
        return f"{prefix}:{hashed}"

    def _resolve_point_value_inr(self, card: CreditCard) -> float:
        """Determines INR worth of 1 reward point for a card."""
        if card.point_value_inr is not None and card.point_value_inr > 0:
            return card.point_value_inr
        if "infinia" in card.slug or "black" in card.slug or "magnus" in card.slug:
            return 1.00
        elif "atlas" in card.slug or "regalia" in card.slug:
            return 0.50
        elif "cashback" in card.slug:
            return 1.00
        return 0.25

    def _resolve_fee_waiver_spend(
        self, card: CreditCard, tabs: List[CardTab]
    ) -> Optional[float]:
        """Resolves annual spend threshold for renewal fee waiver."""
        if card.fee_waiver_spend is not None and card.fee_waiver_spend > 0:
            return card.fee_waiver_spend

        # Attempt to extract from milestones tab
        for t in tabs:
            if t.tab_name == "milestones" and isinstance(t.raw_content, dict):
                tab_data = t.raw_content.get("tabData", {})
                for item in tab_data.get("mileStoneItems", []):
                    if item.get("renewalFeeWaiver") and item.get("spent"):
                        try:
                            return float(item["spent"])
                        except (ValueError, TypeError):
                            pass

        # Curated industry standard waiver spends
        curated_waivers = {
            "hdfc-infinia-metal": 1000000.0,
            "hdfc-diners-club-black": 800000.0,
            "hdfc-regalia-gold": 400000.0,
            "hdfc-millennia": 100000.0,
            "icici-rubyx-mastercard": 300000.0,
            "icici-rubyx-visa": 300000.0,
            "icici-sapphiro": 600000.0,
            "icici-coral": 150000.0,
            "sbi-cashback-credit-card": 200000.0,
            "sbi-simplyclick": 100000.0,
            "axis-atlas": 750000.0,
            "axis-magnus": 1500000.0,
            "flipkart-axis-bank": 200000.0,
            "airtel-axis-bank": 200000.0,
            "axis-bank-ace": 200000.0,
            "tata-neu-infinity": 300000.0,
            "tata-neu-plus": 100000.0,
        }
        if card.slug in curated_waivers:
            return curated_waivers[card.slug]

        if card.renewal_fee == 0:
            return 0.0

        # Generic heuristic: 100x renewal fee
        return round(card.renewal_fee * 100.0, 2)

    def _compute_category_earn_rates(
        self, card: CreditCard, earn_tab: Optional[Dict[str, Any]], point_val: float
    ) -> List[CategoryEarnRateItem]:
        """Calculates per-category return rates for all standard categories."""
        rates: List[CategoryEarnRateItem] = []
        base_rate = (
            card.return_max_percent
            if card.return_max_percent > 0
            else card.return_min_percent
        )
        if base_rate <= 0:
            base_rate = 1.0

        exclusions_set: set[str] = set()
        earn_rows_map: Dict[str, tuple[float, Optional[float]]] = {}

        if earn_tab and "tabData" in earn_tab:
            tab_data = earn_tab.get("tabData", {})
            for excl in tab_data.get("exclusions", []):
                name = (excl.get("name") or "").lower()
                cat = (excl.get("category") or "").lower()
                if name:
                    exclusions_set.add(name)
                if cat:
                    exclusions_set.add(cat)

            for row in tab_data.get("earnRows", []):
                r_cat = (row.get("category") or "").lower()
                r_sub = (row.get("subCategory") or "").lower()
                r_name = (row.get("name") or "").lower()

                pts = float(row.get("points") or 0.0)
                per = float(row.get("per") or 100.0)
                cap_str = row.get("cap")
                cap_val: Optional[float] = None
                if cap_str and isinstance(cap_str, (int, float)):
                    cap_val = float(cap_str)

                if per > 0 and pts > 0:
                    calculated_rate = round((pts / per) * point_val * 100.0, 2)
                    for key in (r_cat, r_sub, r_name):
                        if key and key not in earn_rows_map:
                            earn_rows_map[key] = (calculated_rate, cap_val)

        for cat_slug in CATEGORY_METADATA.keys():
            cat_lower = cat_slug.lower()

            # Check exclusions
            is_excluded = any(ex in cat_lower or cat_lower in ex for ex in exclusions_set)
            if is_excluded:
                rates.append(
                    CategoryEarnRateItem(
                        category_slug=cat_slug, rate_percent=0.0, cap_monthly=None
                    )
                )
                continue

            # Check matching accelerated earn rate
            matched_rate = None
            matched_cap = None
            for key, (rate, cap) in earn_rows_map.items():
                if key in cat_lower or cat_lower in key:
                    matched_rate = rate
                    matched_cap = cap
                    break

            if matched_rate is not None:
                rates.append(
                    CategoryEarnRateItem(
                        category_slug=cat_slug,
                        rate_percent=matched_rate,
                        cap_monthly=matched_cap,
                    )
                )
            else:
                rates.append(
                    CategoryEarnRateItem(
                        category_slug=cat_slug,
                        rate_percent=round(base_rate, 2),
                        cap_monthly=None,
                    )
                )

        return rates

    def to_summary(self, card: CreditCard) -> CardSummaryResponse:
        """Maps a loaded card (with bank) into the catalog summary contract."""
        return CardSummaryResponse(
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

    def category_rates_from_card(self, card: CreditCard) -> List[CategoryEarnRateItem]:
        """
        Builds per-category earn rates from data already stored on the card.
        Does not call the upstream crawler.
        """
        earn_tab: Optional[Dict[str, Any]] = None
        for tab in card.tabs or []:
            if tab.tab_name == "earn-categories" and isinstance(tab.raw_content, dict):
                earn_tab = tab.raw_content
                break
        return self._compute_category_earn_rates(
            card, earn_tab, self._resolve_point_value_inr(card)
        )

    async def get_filtered_cards(
        self, db: AsyncSession, query_params: CardFilterQuery
    ) -> tuple[List[CardSummaryResponse], PaginationMeta]:
        cache_key = self._generate_cache_key("catalog:cards", query_params.model_dump())
        cached = await redis_service.get_json(cache_key)
        if cached:
            items = [CardSummaryResponse(**item) for item in cached["items"]]
            meta = PaginationMeta(**cached["meta"])
            return items, meta

        # Construct SQLAlchemy query. Join banks once — search and bank_slug both need it.
        stmt = select(CreditCard).options(selectinload(CreditCard.bank))
        if query_params.search or query_params.bank_slug:
            stmt = stmt.join(Bank, CreditCard.bank_id == Bank.id)

        # Filter: Search query
        if query_params.search:
            search_term = f"%{query_params.search}%"
            stmt = stmt.where(
                or_(
                    CreditCard.title.ilike(search_term),
                    CreditCard.display_name.ilike(search_term),
                    Bank.name.ilike(search_term),
                )
            )

        # Filter: Bank Slug
        if query_params.bank_slug:
            stmt = stmt.where(Bank.slug == query_params.bank_slug.lower())

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

        # Filter: Lounge access
        effective_has_lounge = (
            query_params.has_lounge
            if query_params.has_lounge is not None
            else query_params.lounge
        )
        if effective_has_lounge is True:
            stmt = stmt.where(
                CreditCard.lounge_types.isnot(None),
                func.cast(CreditCard.lounge_types, String) != "[]",
                func.cast(CreditCard.lounge_types, String) != "null",
            )
        elif effective_has_lounge is False:
            stmt = stmt.where(
                or_(
                    CreditCard.lounge_types.is_(None),
                    func.cast(CreditCard.lounge_types, String) == "[]",
                    func.cast(CreditCard.lounge_types, String) == "null",
                )
            )

        # Filter: Lounge Type (e.g. INTERNATIONAL_LOUNGE)
        if query_params.lounge_type:
            stmt = stmt.where(
                func.cast(CreditCard.lounge_types, String).ilike(
                    f"%{query_params.lounge_type.strip()}%"
                )
            )

        # Filter: Popular
        if query_params.is_popular is not None:
            stmt = stmt.where(CreditCard.is_popular == query_params.is_popular)

        # Count total items matching criteria
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # Sorting
        sort_by = (query_params.sort_by or "popular").lower()
        if sort_by in ("return", "return_desc"):
            stmt = stmt.order_by(desc(CreditCard.return_max_percent))
        elif sort_by == "return_asc":
            stmt = stmt.order_by(CreditCard.return_min_percent.asc())
        elif sort_by == "fee_asc":
            stmt = stmt.order_by(CreditCard.joining_fee.asc())
        elif sort_by == "annual_fee_asc":
            stmt = stmt.order_by(CreditCard.renewal_fee.asc(), CreditCard.joining_fee.asc())
        elif sort_by == "fee_desc":
            stmt = stmt.order_by(CreditCard.joining_fee.desc())
        elif sort_by == "annual_fee_desc":
            stmt = stmt.order_by(CreditCard.renewal_fee.desc(), CreditCard.joining_fee.desc())
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
            applied_filters={
                "search": query_params.search,
                "bank_slug": query_params.bank_slug,
                "network": query_params.network,
                "fee_type": query_params.fee_type,
                "has_lounge": effective_has_lounge,
                "lounge_type": query_params.lounge_type,
                "is_popular": query_params.is_popular,
                "sort_by": sort_by,
            },
        )

        items = [self.to_summary(c) for c in cards]

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

        # On-demand tab & overview enrichment if not present in DB
        if not card.tabs or not card.overview_text or not card.card_image_url:
            try:
                earn_data = await crawler_service.fetch_card_tab(slug, "earn-categories")
                if earn_data:
                    # Update card overview and details from tab
                    if "card" in earn_data and isinstance(earn_data["card"], dict):
                        c_info = earn_data["card"]
                        if c_info.get("cardImageLink"):
                            card.card_image_url = c_info["cardImageLink"]
                        if c_info.get("applyLink"):
                            card.apply_link = c_info["applyLink"]
                        if c_info.get("aprPercent") is not None:
                            card.apr_percent = float(c_info["aprPercent"])
                        if c_info.get("addOnCardFee") is not None:
                            card.add_on_card_fee = float(c_info["addOnCardFee"])

                    if "cardOverview" in earn_data and isinstance(earn_data["cardOverview"], dict):
                        co = earn_data["cardOverview"]
                        if co.get("overviewText"):
                            card.overview_text = co["overviewText"]
                        if co.get("bestSuited"):
                            card.best_suited = co["bestSuited"]

                    # Check if earn tab already exists in DB
                    existing_tab = next((t for t in card.tabs if t.tab_name == "earn-categories"), None)
                    if not existing_tab:
                        new_tab = CardTab(
                            card_id=card.id,
                            tab_name="earn-categories",
                            raw_content=earn_data,
                        )
                        db.add(new_tab)
                        card.tabs.append(new_tab)

                    await db.commit()
                    await db.refresh(card)
            except Exception as e:
                logger.warning(f"On-demand tab fetch failed for '{slug}': {e}")

        # Ensure image URL fallback
        card_image_url = card.card_image_url or card.web_logo_url

        # Ensure editorial overview fallback
        overview_text = card.overview_text
        if not overview_text:
            bank_name = card.bank.name if card.bank else "Bank"
            features = []
            if card.joining_fee == 0:
                features.append("lifetime free zero-joining fee")
            else:
                features.append(f"₹{int(card.joining_fee)} joining fee")
            if card.return_max_percent > 0:
                features.append(f"up to {card.return_max_percent}% reward return")
            if card.lounge_types:
                features.append("airport and railway lounge privileges")
            if card.benefit_types:
                clean_benefits = [b.replace("_", " ").lower() for b in card.benefit_types[:3]]
                features.append(f"perks on {', '.join(clean_benefits)}")
            overview_text = (
                f"{card.display_name} is issued by {bank_name}, providing {', '.join(features)}."
            )

        # Ensure apply link fallback
        apply_link = card.apply_link
        if not apply_link:
            apply_link = f"https://www.google.com/search?q={card.title.replace(' ', '+')}+apply+online"

        # Calculate calculator & reward properties
        point_val = self._resolve_point_value_inr(card)
        fee_waiver = self._resolve_fee_waiver_spend(card, card.tabs)

        earn_tab = next(
            (t.raw_content for t in card.tabs if t.tab_name == "earn-categories"),
            None,
        )
        category_rates = self._compute_category_earn_rates(card, earn_tab, point_val)

        # Available tabs: return all 5 tabs so frontend can render them seamlessly
        available_tabs = ALL_STANDARD_TABS

        response = CardDetailResponse(
            id=card.id,
            slug=card.slug,
            title=card.title,
            display_name=card.display_name,
            bank_name=card.bank.name if card.bank else None,
            bank_slug=card.bank.slug if card.bank else None,
            bank_logo_url=card.bank.logo_url if card.bank else None,
            web_logo_url=card.web_logo_url,
            card_image_url=card_image_url,
            joining_fee=card.joining_fee,
            renewal_fee=card.renewal_fee,
            fee_waiver_spend=fee_waiver,
            point_value_inr=point_val,
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
            apply_link=apply_link,
            overview_text=overview_text,
            best_suited=card.best_suited or "Shopping, Dining, Lifestyle",
            available_tabs=available_tabs,
            per_category_earn_rates=category_rates,
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

        # 1. Check database for existing tab
        stmt = (
            select(CardTab)
            .join(CreditCard, CardTab.card_id == CreditCard.id)
            .where(CreditCard.slug == slug, CardTab.tab_name == tab_name)
        )
        tab = (await db.execute(stmt)).scalar_one_or_none()

        # 2. If not found in DB, attempt on-demand upstream fetch
        if not tab:
            # First fetch card
            c_stmt = select(CreditCard).options(selectinload(CreditCard.bank)).where(CreditCard.slug == slug)
            card = (await db.execute(c_stmt)).scalar_one_or_none()
            if not card:
                raise NotFoundError(f"Credit card with slug '{slug}' not found.")

            upstream_tab_data = None
            if tab_name in VALID_TABS:
                try:
                    upstream_tab_data = await crawler_service.fetch_card_tab(slug, tab_name)
                except Exception as e:
                    logger.warning(f"Upstream fetch failed for {slug} tab {tab_name}: {e}")

            if upstream_tab_data:
                tab = CardTab(
                    card_id=card.id,
                    tab_name=tab_name,
                    raw_content=upstream_tab_data,
                )
                db.add(tab)

                # Also update card fields if present
                if "card" in upstream_tab_data and isinstance(upstream_tab_data["card"], dict):
                    c_info = upstream_tab_data["card"]
                    if c_info.get("cardImageLink"):
                        card.card_image_url = c_info["cardImageLink"]
                    if c_info.get("applyLink"):
                        card.apply_link = c_info["applyLink"]
                if "cardOverview" in upstream_tab_data and isinstance(upstream_tab_data["cardOverview"], dict):
                    co = upstream_tab_data["cardOverview"]
                    if co.get("overviewText"):
                        card.overview_text = co["overviewText"]
                    if co.get("bestSuited"):
                        card.best_suited = co["bestSuited"]

                await db.commit()
                await db.refresh(tab)
            else:
                # 3. Upstream did not have this tab: synthesize rich fallback tab matching SaveSage schema
                point_val = self._resolve_point_value_inr(card)
                fee_waiver = self._resolve_fee_waiver_spend(card, [])

                if tab_name == "earn-categories":
                    content = {
                        "type": "earn-categories",
                        "earnRows": [
                            {
                                "name": "Base Rewards",
                                "category": "All",
                                "subCategory": "Base Spends",
                                "points": card.return_min_percent if card.return_min_percent > 0 else 1,
                                "per": 100,
                                "unit": "Points",
                                "cap": None,
                            }
                        ],
                        "exclusions": [
                            {"name": "Fuel Surcharge", "category": "Fuel"},
                            {"name": "Wallet Reload", "category": "Wallets"},
                            {"name": "Rent Payment", "category": "Rent"},
                        ],
                    }
                elif tab_name == "benefits-and-offers":
                    content = {
                        "type": "benefits-and-offers",
                        "items": [
                            {
                                "title": b.replace("_", " ").title(),
                                "subtitle": f"Complimentary privileges across {b.replace('_', ' ').lower()}.",
                                "tag": "Benefit",
                            }
                            for b in (card.benefit_types or ["REWARDS", "PROTECTION"])
                        ],
                    }
                elif tab_name == "lounge-access":
                    content = {
                        "type": "lounge-access",
                        "items": [
                            {
                                "title": l.replace("_", " ").title(),
                                "subtitle": f"Complimentary visits to participating {l.replace('_', ' ').lower()} lounges.",
                                "type": l,
                            }
                            for b in (card.lounge_types or ["DOMESTIC_LOUNGE"])
                        ],
                    }
                elif tab_name == "milestones":
                    content = {
                        "type": "milestones",
                        "mileStoneItems": [
                            {
                                "milestoneNumber": 1,
                                "spent": fee_waiver or 100000,
                                "renewalFeeWaiver": True,
                                "description": f"Annual spend of ₹{int(fee_waiver or 100000)} waives renewal fee of ₹{int(card.renewal_fee)}.",
                            }
                        ],
                    }
                else:  # redemption-options
                    content = {
                        "type": "redemption-options",
                        "items": [
                            {
                                "title": "Statement Credit & Vouchers",
                                "subtitle": f"Redeem reward points at ~₹{point_val:.2f} per point across flights, hotels, vouchers, and statement cashback.",
                            }
                        ],
                    }

                tab = CardTab(
                    card_id=card.id,
                    tab_name=tab_name,
                    raw_content=content,
                )
                db.add(tab)
                await db.commit()
                await db.refresh(tab)

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

    async def get_all_categories(self, db: AsyncSession) -> List[CategoryResponse]:
        cache_key = "calc:categories:enriched"
        cached = await redis_service.get_json(cache_key)
        if cached:
            return [CategoryResponse(**c) for c in cached]

        stmt = select(SpendCategory)
        categories = (await db.execute(stmt)).scalars().all()

        enriched_categories: List[CategoryResponse] = []
        for c in categories:
            meta = CATEGORY_METADATA.get(c.name) or CATEGORY_METADATA.get(c.slug) or {}
            enriched_categories.append(
                CategoryResponse(
                    id=c.id,
                    slug=c.slug,
                    name=c.name,
                    icon_url=c.icon_url,
                    icon_key=meta.get("icon_key", "category"),
                    display_order=meta.get("display_order", 99),
                    savesage_category_id=c.savesage_category_id,
                )
            )

        # Sort by display order, then alphabetically by name
        enriched_categories.sort(key=lambda x: (x.display_order, x.name))

        await redis_service.set_json(
            cache_key,
            [c.model_dump() for c in enriched_categories],
            ttl_seconds=86400,
        )
        return enriched_categories


# Global Singleton Card Service
card_service = CardService()
