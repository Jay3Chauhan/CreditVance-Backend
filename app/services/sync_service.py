"""
Sync & Ingestion Orchestration Service.
Coordinates crawler, Neon PostgreSQL idempotent upserts, Upstash Redis cache invalidation, and audit logs.
"""

import re
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from app.core.config import settings
from app.core.redis_client import redis_service
from app.models.bank import Bank
from app.models.category import SpendCategory
from app.models.card import CreditCard
from app.models.card_tab import CardTab
from app.models.sync_audit import SyncAuditLog
from app.services.crawler_service import VALID_TABS, crawler_service

SYNC_LOCK_KEY = "lock:sync:savesage"


def parse_return_percentage(raw_str: Optional[str]) -> tuple[float, float]:
    """
    Parses strings like "0.5% to 1%", "Up to 5%", "3.3%", "1.5% to 33.3%" into (min_pct, max_pct).
    """
    if not raw_str:
        return 0.0, 0.0

    numbers = re.findall(r"(\d+(?:\.\d+)?)", raw_str)
    if not numbers:
        return 0.0, 0.0

    floats = [float(n) for n in numbers]
    if len(floats) == 1:
        return floats[0], floats[0]
    return min(floats), max(floats)


class SyncService:
    """Orchestrates third-party data synchronization into the local database."""

    async def execute_sync(
        self,
        db: AsyncSession,
        sync_type: str = "scheduled",
        sync_tabs: bool = False,
        limit_cards: Optional[int] = None,
    ) -> Dict[str, Any]:
        # Normalize limit_cards: 0 or negative means None (unlimited)
        if limit_cards is not None and limit_cards <= 0:
            limit_cards = None

        # Clean up any stale 'running' audits older than 30 minutes
        try:
            stale_cutoff = datetime.now(timezone.utc)
            stale_stmt = select(SyncAuditLog).where(SyncAuditLog.status == "running")
            stale_audits = (await db.execute(stale_stmt)).scalars().all()
            for sa in stale_audits:
                # If running for more than 15 minutes, mark as interrupted
                diff_seconds = (stale_cutoff - sa.started_at.replace(tzinfo=timezone.utc)).total_seconds()
                if diff_seconds > 900:
                    sa.status = "interrupted"
                    sa.completed_at = stale_cutoff
            await db.commit()
        except Exception as e:
            logger.warning(f"Error cleaning stale audit logs: {e}")

        # 1. Acquire Distributed Lock
        lock_acquired = await redis_service.acquire_lock(
            SYNC_LOCK_KEY, ttl_seconds=settings.REDIS_SYNC_LOCK_TTL_SECONDS
        )
        if not lock_acquired:
            logger.warning("Sync job already running. Aborting duplicate execution.")
            return {
                "status": "skipped",
                "message": "Another sync job is currently in progress.",
            }

        # 2. Initialize Audit Log Entry
        audit = SyncAuditLog(
            sync_type=sync_type,
            status="running",
            details={
                "sync_tabs": sync_tabs,
                "limit_cards": limit_cards,
            },
        )
        db.add(audit)
        await db.commit()
        await db.refresh(audit)

        cards_processed = 0
        tabs_processed = 0
        errors_count = 0

        try:
            logger.info(f"Starting sync job (id={audit.id}, type={sync_type}, tabs={sync_tabs}, limit={limit_cards})...")

            # 3. Ingest Categories & Banks from Calculator Taxonomy
            await self._sync_categories_and_banks(db)

            # 4. Ingest Master Cards Catalog
            raw_cards, filter_meta = await crawler_service.fetch_all_cards_master(
                max_cards=limit_cards
            )

            # Extract and upsert banks found in filter metadata
            if "banks" in filter_meta and "items" in filter_meta["banks"]:
                for b_item in filter_meta["banks"]["items"]:
                    slug = b_item.get("slug")
                    title = b_item.get("title")
                    img = b_item.get("imageUrl")
                    if slug and title:
                        await self._upsert_bank(db, slug=slug, name=title, logo_url=img)

            # 5. Upsert Master Cards
            slug_to_id: Dict[str, int] = {}
            for card_dict in raw_cards:
                try:
                    card_id = await self._upsert_card(db, card_dict)
                    slug_to_id[card_dict["slug"]] = card_id
                    cards_processed += 1
                except Exception as e:
                    errors_count += 1
                    logger.error(f"Error upserting card {card_dict.get('slug')}: {e}")

            # Commit master cards immediately so they are available in DB right away!
            audit.cards_fetched = cards_processed
            await db.commit()
            logger.info(f"Master cards successfully committed to DB! Total: {cards_processed}")

            # 6. Ingest Tabs (if enabled)
            if sync_tabs:
                logger.info(f"Crawling tabs for {len(slug_to_id)} cards (this will take several minutes)...")
                processed_count = 0
                for slug, card_id in slug_to_id.items():
                    for tab_name in VALID_TABS:
                        try:
                            tab_data = await crawler_service.fetch_card_tab(slug, tab_name)
                            if tab_data:
                                await self._upsert_card_tab(
                                    db, card_id=card_id, tab_name=tab_name, raw_content=tab_data
                                )
                                tabs_processed += 1
                        except Exception as e:
                            errors_count += 1
                            logger.warning(f"Error fetching tab '{tab_name}' for '{slug}': {e}")

                    processed_count += 1
                    # Commit in small batches of 10 cards
                    if processed_count % 10 == 0:
                        audit.tabs_fetched = tabs_processed
                        await db.commit()
                        logger.info(f"Progress: crawled tabs for {processed_count}/{len(slug_to_id)} cards ({tabs_processed} tabs).")

            # 7. Invalidate Redis Caches
            await redis_service.invalidate_pattern("catalog:*")
            await redis_service.invalidate_pattern("calc:*")
            logger.info("Invalidated Redis catalog and calculator caches.")

            # 8. Mark Audit as Completed
            audit.status = "completed"
            audit.cards_fetched = cards_processed
            audit.tabs_fetched = tabs_processed
            audit.errors_count = errors_count
            audit.completed_at = datetime.now(timezone.utc)
            audit.details = {
                "sync_tabs": sync_tabs,
                "limit_cards": limit_cards,
                "total_cards_upserted": cards_processed,
                "total_tabs_upserted": tabs_processed,
            }
            await db.commit()

            logger.info(
                f"Sync job {audit.id} finished successfully! (Cards: {cards_processed}, Tabs: {tabs_processed}, Errors: {errors_count})"
            )

            return {
                "status": "completed",
                "audit_id": audit.id,
                "cards_processed": cards_processed,
                "tabs_processed": tabs_processed,
                "errors_count": errors_count,
            }

        except Exception as e:
            logger.exception(f"Fatal error during sync job {audit.id}: {e}")
            audit.status = "failed"
            audit.error_message = f"{str(e)}\n{traceback.format_exc()}"
            audit.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {
                "status": "failed",
                "audit_id": audit.id,
                "error": str(e),
            }

        finally:
            # 9. Release Redis Lock
            await redis_service.release_lock(SYNC_LOCK_KEY)

    async def _sync_categories_and_banks(self, db: AsyncSession):
        """Ingests categories and banks from reward calculator metadata."""
        try:
            categories = await crawler_service.fetch_calculator_categories()
            for cat in categories:
                slug = cat.get("slug") or cat.get("value")
                name = cat.get("label") or slug
                cat_id = cat.get("id")
                if slug and name:
                    stmt = select(SpendCategory).where(SpendCategory.slug == slug)
                    existing = (await db.execute(stmt)).scalar_one_or_none()
                    if not existing:
                        db.add(
                            SpendCategory(
                                slug=slug,
                                name=name,
                                savesage_category_id=cat_id,
                            )
                        )
                    else:
                        existing.name = name
                        existing.savesage_category_id = cat_id

            banks = await crawler_service.fetch_calculator_banks()
            for b in banks:
                b_id = b.get("id")
                name = b.get("label") or "Unknown"
                slug = name.lower().replace(" ", "-")
                logo = b.get("logoUrl")
                await self._upsert_bank(
                    db, slug=slug, name=name, logo_url=logo, savesage_bank_id=b_id
                )

            await db.commit()
        except Exception as e:
            logger.warning(f"Error syncing calculator categories and banks: {e}")

    async def _upsert_bank(
        self,
        db: AsyncSession,
        slug: str,
        name: str,
        logo_url: Optional[str] = None,
        savesage_bank_id: Optional[int] = None,
    ) -> Bank:
        norm_slug = slug.strip().lower().replace("&", "")

        # Check in-memory cache
        if norm_slug in getattr(self, "_bank_cache", {}):
            bank_id = self._bank_cache[norm_slug]
            stmt = select(Bank).where(Bank.id == bank_id)
            bank = (await db.execute(stmt)).scalar_one_or_none()
            if bank:
                if name:
                    bank.name = name
                if logo_url:
                    bank.logo_url = logo_url
                if savesage_bank_id:
                    bank.savesage_bank_id = savesage_bank_id
                return bank

        stmt = select(Bank).where((Bank.slug == slug) | (Bank.slug == norm_slug))
        bank = (await db.execute(stmt)).scalars().first()
        if not bank:
            bank = Bank(
                slug=norm_slug,
                name=name,
                logo_url=logo_url,
                savesage_bank_id=savesage_bank_id,
            )
            db.add(bank)
            await db.flush()
        else:
            if name:
                bank.name = name
            if logo_url:
                bank.logo_url = logo_url
            if savesage_bank_id:
                bank.savesage_bank_id = savesage_bank_id

        if not hasattr(self, "_bank_cache"):
            self._bank_cache = {}
        self._bank_cache[slug] = bank.id
        self._bank_cache[norm_slug] = bank.id
        return bank

    async def _upsert_card(self, db: AsyncSession, data: Dict[str, Any]) -> int:
        slug = data["slug"]
        bank_slug = data.get("bankSlug") or "unknown"
        bank_name = data.get("bankName") or bank_slug.capitalize()

        # Ensure Bank exists
        bank = await self._upsert_bank(db, slug=bank_slug, name=bank_name)

        return_raw = data.get("returnPercentage")
        ret_min, ret_max = parse_return_percentage(return_raw)

        stmt = select(CreditCard).where(CreditCard.slug == slug)
        card = (await db.execute(stmt)).scalar_one_or_none()

        if not card:
            card = CreditCard(
                slug=slug,
                title=data.get("cardTitle") or data.get("displayName") or slug,
                display_name=data.get("displayName") or slug,
                bank_id=bank.id,
                joining_fee=float(data.get("joiningFee") or 0.0),
                renewal_fee=float(data.get("renewalFee") or 0.0),
                forex_markup_percent=(
                    float(data["forexMarkupPercent"])
                    if data.get("forexMarkupPercent") is not None
                    else None
                ),
                return_percentage_raw=return_raw,
                return_min_percent=ret_min,
                return_max_percent=ret_max,
                network_type=data.get("networkType"),
                lounge_types=data.get("loungeTypes") or [],
                benefit_types=data.get("benefitTypes") or [],
                category_slugs=data.get("categorySlugs") or [],
                is_fd_card=bool(data.get("isFdCard", False)),
                is_business_card=bool(data.get("isBusinessCard", False)),
                is_popular=bool(data.get("isPopular", False)),
                is_currently_issuing=bool(data.get("isCurrentlyIssuing", True)),
                web_logo_url=data.get("webLogoUrl"),
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(card)
            await db.flush()
        else:
            card.title = data.get("cardTitle") or card.title
            card.display_name = data.get("displayName") or card.display_name
            card.bank_id = bank.id
            card.joining_fee = float(data.get("joiningFee") or 0.0)
            card.renewal_fee = float(data.get("renewalFee") or 0.0)
            if data.get("forexMarkupPercent") is not None:
                card.forex_markup_percent = float(data["forexMarkupPercent"])
            card.return_percentage_raw = return_raw
            card.return_min_percent = ret_min
            card.return_max_percent = ret_max
            card.network_type = data.get("networkType") or card.network_type
            card.lounge_types = data.get("loungeTypes") or []
            card.benefit_types = data.get("benefitTypes") or []
            card.category_slugs = data.get("categorySlugs") or []
            card.is_fd_card = bool(data.get("isFdCard", False))
            card.is_business_card = bool(data.get("isBusinessCard", False))
            card.is_popular = bool(data.get("isPopular", False))
            card.is_currently_issuing = bool(data.get("isCurrentlyIssuing", True))
            card.web_logo_url = data.get("webLogoUrl") or card.web_logo_url
            card.last_synced_at = datetime.now(timezone.utc)

        return card.id

    async def _upsert_card_tab(
        self, db: AsyncSession, card_id: int, tab_name: str, raw_content: Dict[str, Any]
    ):
        # Also update card overview and high-level card fields if present in tab response
        if "card" in raw_content and isinstance(raw_content["card"], dict):
            c_info = raw_content["card"]
            stmt = select(CreditCard).where(CreditCard.id == card_id)
            c = (await db.execute(stmt)).scalar_one_or_none()
            if c:
                if c_info.get("cardImageLink"):
                    c.card_image_url = c_info["cardImageLink"]
                if c_info.get("applyLink"):
                    c.apply_link = c_info["applyLink"]
                if c_info.get("aprPercent") is not None:
                    c.apr_percent = float(c_info["aprPercent"])
                if c_info.get("addOnCardFee") is not None:
                    c.add_on_card_fee = float(c_info["addOnCardFee"])

        if "cardOverview" in raw_content and isinstance(raw_content["cardOverview"], dict):
            co = raw_content["cardOverview"]
            stmt = select(CreditCard).where(CreditCard.id == card_id)
            c = (await db.execute(stmt)).scalar_one_or_none()
            if c:
                if co.get("overviewText"):
                    c.overview_text = co["overviewText"]
                if co.get("bestSuited"):
                    c.best_suited = co["bestSuited"]

        stmt = select(CardTab).where(
            CardTab.card_id == card_id, CardTab.tab_name == tab_name
        )
        existing_tab = (await db.execute(stmt)).scalar_one_or_none()
        if not existing_tab:
            db.add(
                CardTab(
                    card_id=card_id,
                    tab_name=tab_name,
                    raw_content=raw_content,
                )
            )
        else:
            existing_tab.raw_content = raw_content


# Global Singleton Sync Service
sync_service = SyncService()
