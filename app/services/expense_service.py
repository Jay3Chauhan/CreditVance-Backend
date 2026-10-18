"""
SMS Expense Tracking Service Layer.
Handles batch transaction ingestion, idempotency, merchant normalisation,
spend analytics calculations, milestone aggregation, and DPDP erasure.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.card import CreditCard
from app.models.expense import (
    CardBill,
    CardMilestoneRule,
    CardTransaction,
    ExpenseConsent,
    ExpenseIdempotency,
    Merchant,
)
from app.models.user_card import UserCard
from app.schemas.expense import (
    BatchIngestRequest,
    BatchIngestResponse,
    CardMilestoneResponse,
    CardSpendBreakdown,
    CardTransactionResponse,
    CategorySpendBreakdown,
    MonthlySpendTrend,
    RejectedRecord,
    SenderRegistryResponse,
    SmsConsentRequest,
    SmsConsentResponse,
    SpendAnalyticsSummaryResponse,
    TopMerchantSpend,
    TransactionEnrichment,
    TransactionListResponse,
)


# Bank display name lookup
BANK_NAMES: Dict[str, str] = {
    "HDFC": "HDFC Bank",
    "ICICI": "ICICI Bank",
    "SBICARD": "SBI Card",
    "AXIS": "Axis Bank",
    "KOTAK": "Kotak Mahindra Bank",
    "AMEX": "American Express",
    "IDFC": "IDFC FIRST Bank",
    "AU": "AU Small Finance Bank",
    "ONECARD": "OneCard",
    "RBL": "RBL Bank",
    "YES": "YES Bank",
    "INDUSIND": "IndusInd Bank",
    "HSBC": "HSBC",
    "SCB": "Standard Chartered",
    "FEDERAL": "Federal Bank",
    "BOB": "BOBCARD",
}

# Known merchant dictionary for server-side enrichment
KNOWN_MERCHANT_ENRICHMENTS = [
    # Dining / Food Delivery
    (re.compile(r"\b(swiggy|instamart)\b", re.I), "Swiggy", "dining"),
    (re.compile(r"\bzomato\b", re.I), "Zomato", "dining"),
    (re.compile(r"\b(mcdonald|domino|starbucks|subway|kfc|pizza hut)\b", re.I), None, "dining"),
    # Groceries
    (re.compile(r"\b(blinkit|zepto|bigbasket|bbdaily)\b", re.I), None, "groceries"),
    (re.compile(r"\b(dmart|nature's basket|spencer|reliance fresh)\b", re.I), None, "groceries"),
    # Shopping / E-Commerce
    (re.compile(r"\b(amazon|amzn)\b", re.I), "Amazon", "shopping"),
    (re.compile(r"\bflipkart\b", re.I), "Flipkart", "shopping"),
    (re.compile(r"\b(myntra|ajio|nykaa|tata cliq)\b", re.I), None, "shopping"),
    # Travel & Cabs
    (re.compile(r"\b(uber|ola cabs|rapido)\b", re.I), None, "travel"),
    (re.compile(r"\b(makemytrip|mmt|cleartrip|yatra|easemytrip|ixigo)\b", re.I), None, "travel"),
    (re.compile(r"\b(indigo|air india|vistara|spicejet|akasa)\b", re.I), None, "travel"),
    (re.compile(r"\b(irctc)\b", re.I), "IRCTC", "travel"),
    # Fuel
    (re.compile(r"\b(hpcl|bpcl|iocl|indian oil|bharat petro|shell)\b", re.I), None, "fuel"),
    # Utilities
    (re.compile(r"\b(bescom|tatapower|adani electricity|mahavitaran|airtel|jio|vi bill)\b", re.I), None, "utilities"),
    # Entertainment & Subscriptions
    (re.compile(r"\b(bookmyshow|pvr|inox)\b", re.I), None, "entertainment"),
    (re.compile(r"\b(netflix|spotify|hotstar|prime video|youtube)\b", re.I), None, "subscriptions"),
    # Health & Pharmacy
    (re.compile(r"\b(apollo pharmacy|netmeds|tata 1mg|pharmeasy)\b", re.I), None, "health"),
]

# Standard milestone catalog fallback for known cards
MILESTONE_CATALOG_FALLBACK = [
    (re.compile(r"infinia", re.I), "Annual fee waiver", "Renewal fee waived", "fee_waiver", "card_year", 1000000.0),
    (re.compile(r"regalia gold", re.I), "Annual fee waiver", "Renewal fee waived", "fee_waiver", "card_year", 400000.0),
    (re.compile(r"sbi cashback|cashback sbi", re.I), "Annual fee waiver", "Renewal fee reversed", "fee_waiver", "card_year", 200000.0),
    (re.compile(r"atlas", re.I), "Silver milestone", "2,500 bonus EDGE Miles", "bonus_rewards", "card_year", 300000.0),
    (re.compile(r"atlas", re.I), "Gold milestone", "2,500 more bonus EDGE Miles", "bonus_rewards", "card_year", 750000.0),
    (re.compile(r"atlas", re.I), "Platinum milestone", "5,000 more bonus EDGE Miles", "bonus_rewards", "card_year", 1500000.0),
    (re.compile(r"platinum travel", re.I), "Travel milestone 1", "15,000 bonus Membership Rewards", "bonus_rewards", "card_year", 190000.0),
    (re.compile(r"platinum travel", re.I), "Travel milestone 2", "25,000 bonus MR + Taj voucher", "voucher", "card_year", 400000.0),
]


class ExpenseService:
    """Service handling SMS expense transactions and spend analytics."""

    async def ingest_batch(
        self,
        db: AsyncSession,
        user_id: int,
        idempotency_key: Optional[str],
        req: BatchIngestRequest,
    ) -> BatchIngestResponse:
        """
        Processes a batch of transactions and bills with idempotency.
        Upserts transactions and returns accepted/duplicate/rejected hashes + enrichments.
        """
        # 1. Check idempotency cache
        if idempotency_key:
            idem_stmt = select(ExpenseIdempotency).where(
                ExpenseIdempotency.user_id == user_id,
                ExpenseIdempotency.idem_key == idempotency_key,
            )
            idem = (await db.execute(idem_stmt)).scalar_one_or_none()
            if idem:
                # Return cached payload if recorded within the last 24 hours
                if (datetime.now(timezone.utc) - idem.created_at) < timedelta(hours=24):
                    return BatchIngestResponse.model_validate(idem.response)

        accepted: List[str] = []
        duplicates: List[str] = []
        rejected: List[RejectedRecord] = []
        enrichments: List[TransactionEnrichment] = []

        now_utc = datetime.now(timezone.utc)
        min_date = now_utc - timedelta(days=400)
        max_date = now_utc + timedelta(days=2)

        # 2. Process Transactions
        tx_hashes = [t.dedupe_hash for t in req.transactions]
        existing_txs_map: Dict[str, CardTransaction] = {}
        if tx_hashes:
            stmt = select(CardTransaction).where(
                CardTransaction.user_id == user_id,
                CardTransaction.dedupe_hash.in_(tx_hashes),
            )
            results = (await db.execute(stmt)).scalars().all()
            for tx in results:
                existing_txs_map[tx.dedupe_hash] = tx

        for item in req.transactions:
            # Validate date window
            if item.occurred_at < min_date or item.occurred_at > max_date:
                rejected.append(
                    RejectedRecord(
                        dedupe_hash=item.dedupe_hash,
                        reason="occurred_at outside acceptable window [now - 400d, now + 2d]",
                    )
                )
                continue

            existing = existing_txs_map.get(item.dedupe_hash)
            if existing:
                # If transaction was soft-deleted by user, tombstone it
                if existing.deleted_at is not None:
                    rejected.append(
                        RejectedRecord(dedupe_hash=item.dedupe_hash, reason="user_deleted")
                    )
                    continue

                # If category override or user_card_id changed, update it
                needs_update = False
                if item.category_overridden and existing.category != item.category:
                    existing.category = item.category
                    existing.category_source = "user"
                    needs_update = True
                if item.user_card_id is not None and existing.user_card_id != item.user_card_id:
                    existing.user_card_id = item.user_card_id
                    needs_update = True

                if needs_update:
                    existing.updated_at = now_utc
                    accepted.append(item.dedupe_hash)
                else:
                    duplicates.append(item.dedupe_hash)
                continue

            # New transaction: determine merchant & category enrichment
            cleaned_merchant = item.merchant_name
            enrich_cat: Optional[str] = None
            enrich_name: Optional[str] = None

            search_str = f"{item.merchant_raw or ''} {item.merchant_name}".strip()
            for pattern, c_name, cat in KNOWN_MERCHANT_ENRICHMENTS:
                if pattern.search(search_str):
                    if c_name:
                        enrich_name = c_name
                    if cat and not item.category_overridden:
                        enrich_cat = cat
                    break

            new_tx = CardTransaction(
                user_id=user_id,
                dedupe_hash=item.dedupe_hash,
                amount=Decimal(str(round(item.amount, 2))),
                currency=item.currency.upper(),
                amount_inr=Decimal(str(round(item.amount, 2))) if item.currency.upper() == "INR" else None,
                type=item.type.lower(),
                occurred_at=item.occurred_at,
                bank_code=item.bank_code.upper(),
                card_last4=item.card_last4,
                user_card_id=item.user_card_id,
                merchant_raw=item.merchant_raw,
                merchant_name=enrich_name or cleaned_merchant,
                category=enrich_cat or item.category,
                category_source="user" if item.category_overridden else ("server" if enrich_cat else "device"),
                channel=item.channel.lower(),
                available_limit=Decimal(str(round(item.available_limit, 2))) if item.available_limit is not None else None,
                source=item.source.lower(),
                confidence=Decimal(str(round(item.confidence, 2))),
            )
            db.add(new_tx)
            accepted.append(item.dedupe_hash)

            if (enrich_name and enrich_name != item.merchant_name) or (enrich_cat and enrich_cat != item.category):
                enrichments.append(
                    TransactionEnrichment(
                        dedupe_hash=item.dedupe_hash,
                        merchant_name=enrich_name,
                        category=enrich_cat,
                    )
                )

        # 3. Process Bills
        bill_hashes = [b.dedupe_hash for b in req.bills]
        existing_bills_set = set()
        if bill_hashes:
            stmt = select(CardBill.dedupe_hash).where(
                CardBill.user_id == user_id,
                CardBill.dedupe_hash.in_(bill_hashes),
            )
            existing_bills_set = set((await db.execute(stmt)).scalars().all())

        for b in req.bills:
            if b.dedupe_hash in existing_bills_set:
                duplicates.append(b.dedupe_hash)
                continue

            new_bill = CardBill(
                user_id=user_id,
                dedupe_hash=b.dedupe_hash,
                bank_code=b.bank_code.upper(),
                card_last4=b.card_last4,
                user_card_id=b.user_card_id,
                total_due=Decimal(str(round(b.total_due, 2))) if b.total_due is not None else None,
                minimum_due=Decimal(str(round(b.minimum_due, 2))) if b.minimum_due is not None else None,
                due_date=b.due_date,
                noticed_at=b.noticed_at,
            )
            db.add(new_bill)
            accepted.append(b.dedupe_hash)

        await db.commit()

        response = BatchIngestResponse(
            accepted=accepted,
            duplicates=duplicates,
            rejected=rejected,
            enrichments=enrichments,
            server_time=now_utc,
        )

        # 4. Save response to idempotency table
        if idempotency_key:
            idem_entry = ExpenseIdempotency(
                user_id=user_id,
                idem_key=idempotency_key,
                response=response.model_dump(mode="json"),
            )
            await db.merge(idem_entry)
            await db.commit()

        return response

    async def list_transactions(
        self,
        db: AsyncSession,
        user_id: int,
        since: Optional[datetime] = None,
        cursor: Optional[int] = None,
        limit: int = 50,
        user_card_id: Optional[int] = None,
        category: Optional[str] = None,
    ) -> TransactionListResponse:
        """
        Retrieves paginated transactions for the user, excluding soft-deleted rows.
        """
        conditions = [
            CardTransaction.user_id == user_id,
            CardTransaction.deleted_at.is_(None),
        ]
        if since:
            conditions.append(CardTransaction.occurred_at >= since)
        if user_card_id:
            conditions.append(CardTransaction.user_card_id == user_card_id)
        if category:
            conditions.append(CardTransaction.category == category)
        if cursor:
            conditions.append(CardTransaction.id < cursor)

        fetch_limit = min(limit, 200)
        stmt = (
            select(CardTransaction)
            .where(and_(*conditions))
            .order_by(desc(CardTransaction.occurred_at), desc(CardTransaction.id))
            .limit(fetch_limit + 1)
        )
        rows = list((await db.execute(stmt)).scalars().all())

        next_cursor = None
        if len(rows) > fetch_limit:
            next_cursor = str(rows[fetch_limit - 1].id)
            rows = rows[:fetch_limit]

        items = [
            CardTransactionResponse(
                id=tx.dedupe_hash,
                dedupe_hash=tx.dedupe_hash,
                amount=float(tx.amount),
                currency=tx.currency,
                amount_inr=float(tx.amount_inr) if tx.amount_inr is not None else None,
                type=tx.type,
                occurred_at=tx.occurred_at,
                bank_code=tx.bank_code,
                bank_name=BANK_NAMES.get(tx.bank_code, tx.bank_code),
                card_last4=tx.card_last4,
                user_card_id=tx.user_card_id,
                merchant_raw=tx.merchant_raw,
                merchant_name=tx.merchant_name,
                category=tx.category,
                category_overridden=tx.category_source == "user",
                channel=tx.channel,
                available_limit=float(tx.available_limit) if tx.available_limit is not None else None,
                source=tx.source,
                confidence=float(tx.confidence),
                created_at=tx.created_at,
            )
            for tx in rows
        ]

        return TransactionListResponse(items=items, next_cursor=next_cursor)

    async def delete_transaction(
        self, db: AsyncSession, user_id: int, dedupe_hash: str
    ) -> bool:
        """
        Soft-deletes a single transaction by hash.
        Tombstone prevents re-ingestion of the same SMS alert.
        """
        stmt = (
            update(CardTransaction)
            .where(
                CardTransaction.user_id == user_id,
                CardTransaction.dedupe_hash == dedupe_hash,
            )
            .values(deleted_at=datetime.now(timezone.utc))
        )
        await db.execute(stmt)
        await db.commit()
        return True

    async def delete_all_user_data(self, db: AsyncSession, user_id: int) -> bool:
        """
        DPDP-compliant hard erasure of all SMS-derived records for this account.
        """
        await db.execute(delete(CardTransaction).where(CardTransaction.user_id == user_id))
        await db.execute(delete(CardBill).where(CardBill.user_id == user_id))
        await db.execute(delete(ExpenseConsent).where(ExpenseConsent.user_id == user_id))
        await db.execute(delete(ExpenseIdempotency).where(ExpenseIdempotency.user_id == user_id))
        await db.commit()
        return True

    async def record_consent(
        self, db: AsyncSession, user_id: int, req: SmsConsentRequest, ip_hash: Optional[str] = None
    ) -> SmsConsentResponse:
        """Records user consent artefact in the append-only ledger."""
        decided = req.decided_at or datetime.now(timezone.utc)
        entry = ExpenseConsent(
            user_id=user_id,
            purpose=req.purpose,
            status=req.status.lower(),
            notice_version=req.notice_version,
            decided_at=decided,
            platform=req.platform,
            ip_hash=ip_hash,
        )
        db.add(entry)
        await db.commit()
        return SmsConsentResponse(
            purpose=entry.purpose,
            status=entry.status,
            notice_version=entry.notice_version,
            decided_at=entry.decided_at,
            platform=entry.platform,
        )

    async def get_milestones(
        self, db: AsyncSession, user_id: int
    ) -> List[CardMilestoneResponse]:
        """
        Retrieves applicable milestone rules for user's active wallet cards.
        """
        stmt = (
            select(UserCard)
            .options(selectinload(UserCard.card))
            .where(UserCard.user_id == user_id, UserCard.is_active.is_(True))
        )
        user_cards = list((await db.execute(stmt)).scalars().all())
        if not user_cards:
            return []

        results: List[CardMilestoneResponse] = []

        for uc in user_cards:
            card = uc.card
            if not card:
                continue

            # 1. Query rules configured in DB for this card product
            rule_stmt = select(CardMilestoneRule).where(CardMilestoneRule.card_id == card.id)
            db_rules = list((await db.execute(rule_stmt)).scalars().all())

            anniversary = uc.anniversary_month or 1

            if db_rules:
                for r in db_rules:
                    results.append(
                        CardMilestoneResponse(
                            id=f"rule_{r.id}",
                            user_card_id=uc.id,
                            title=r.title,
                            reward_description=r.reward_description,
                            type=r.type,
                            period=r.period,
                            target_spend=float(r.target_spend),
                            anniversary_month=anniversary,
                        )
                    )
            else:
                # 2. Check catalog fallback patterns
                for pattern, title, reward, m_type, period, target in MILESTONE_CATALOG_FALLBACK:
                    if pattern.search(card.title) or pattern.search(card.display_name) or pattern.search(card.slug):
                        results.append(
                            CardMilestoneResponse(
                                id=f"cat_{uc.id}_{len(results)}",
                                user_card_id=uc.id,
                                title=title,
                                reward_description=reward,
                                type=m_type,
                                period=period,
                                target_spend=target,
                                anniversary_month=anniversary,
                            )
                        )

        return results

    async def get_analytics_summary(
        self,
        db: AsyncSession,
        user_id: int,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> SpendAnalyticsSummaryResponse:
        """
        Computes net, gross, refunds, category breakdown, per-card spend,
        top merchants, and monthly trend from non-deleted card transactions.
        """
        conditions = [
            CardTransaction.user_id == user_id,
            CardTransaction.deleted_at.is_(None),
        ]
        if from_date:
            conditions.append(CardTransaction.occurred_at >= from_date)
        if to_date:
            conditions.append(CardTransaction.occurred_at <= to_date)

        stmt = select(CardTransaction).where(and_(*conditions))
        txs = list((await db.execute(stmt)).scalars().all())

        debit_sum = 0.0
        refund_sum = 0.0

        cat_spend: Dict[str, float] = defaultdict(float)
        cat_count: Dict[str, int] = defaultdict(int)

        card_spend: Dict[Tuple[Optional[int], Optional[str], str], float] = defaultdict(float)
        card_count: Dict[Tuple[Optional[int], Optional[str], str], int] = defaultdict(int)

        merchant_spend: Dict[Tuple[str, str], float] = defaultdict(float)
        merchant_count: Dict[Tuple[str, str], int] = defaultdict(int)

        monthly_spend: Dict[str, float] = defaultdict(float)
        monthly_count: Dict[str, int] = defaultdict(int)

        for tx in txs:
            amt = float(tx.amount_inr if tx.amount_inr is not None else tx.amount)
            tx_type = tx.type.lower()

            if tx_type == "debit":
                debit_sum += amt
                cat_spend[tx.category] += amt
                cat_count[tx.category] += 1

                card_key = (tx.user_card_id, tx.card_last4, tx.bank_code)
                card_spend[card_key] += amt
                card_count[card_key] += 1

                merchant_key = (tx.merchant_name, tx.category)
                merchant_spend[merchant_key] += amt
                merchant_count[merchant_key] += 1

                month_key = tx.occurred_at.strftime("%Y-%m")
                monthly_spend[month_key] += amt
                monthly_count[month_key] += 1

            elif tx_type in ("refund", "reversal"):
                refund_sum += amt
                cat_spend[tx.category] = max(0.0, cat_spend[tx.category] - amt)
                month_key = tx.occurred_at.strftime("%Y-%m")
                monthly_spend[month_key] = max(0.0, monthly_spend[month_key] - amt)

        net_spend = max(0.0, debit_sum - refund_sum)

        # Build breakdowns
        by_category: List[CategorySpendBreakdown] = []
        for cat, spend in sorted(cat_spend.items(), key=lambda x: x[1], reverse=True):
            pct = (spend / net_spend * 100.0) if net_spend > 0 else 0.0
            by_category.append(
                CategorySpendBreakdown(
                    category=cat,
                    spend_inr=round(spend, 2),
                    transaction_count=cat_count[cat],
                    percentage=round(pct, 1),
                )
            )

        by_card: List[CardSpendBreakdown] = []
        for (uc_id, last4, bank), spend in sorted(card_spend.items(), key=lambda x: x[1], reverse=True):
            by_card.append(
                CardSpendBreakdown(
                    user_card_id=uc_id,
                    card_last4=last4,
                    bank_code=bank,
                    spend_inr=round(spend, 2),
                    transaction_count=card_count[(uc_id, last4, bank)],
                )
            )

        top_merchants: List[TopMerchantSpend] = []
        for (m_name, cat), spend in sorted(merchant_spend.items(), key=lambda x: x[1], reverse=True)[:10]:
            top_merchants.append(
                TopMerchantSpend(
                    merchant_name=m_name,
                    category=cat,
                    spend_inr=round(spend, 2),
                    transaction_count=merchant_count[(m_name, cat)],
                )
            )

        monthly_trend: List[MonthlySpendTrend] = []
        for m_key in sorted(monthly_spend.keys()):
            monthly_trend.append(
                MonthlySpendTrend(
                    month=m_key,
                    net_spend_inr=round(monthly_spend[m_key], 2),
                    transaction_count=monthly_count[m_key],
                )
            )

        return SpendAnalyticsSummaryResponse(
            net_spend=round(net_spend, 2),
            gross_spend=round(debit_sum, 2),
            total_refunds=round(refund_sum, 2),
            transaction_count=len(txs),
            by_category=by_category,
            by_card=by_card,
            top_merchants=top_merchants,
            monthly_trend=monthly_trend,
        )

    def get_sender_registry(self, client_version: Optional[int] = None) -> SenderRegistryResponse:
        """
        Returns bank SMS sender registry with DLT header sender keys and body aliases.
        """
        banks = [
            {"code": "HDFC", "display_name": "HDFC Bank", "sender_keys": ["HDFCBK", "HDFCCC"], "body_aliases": ["hdfc bank", "hdfc"]},
            {"code": "ICICI", "display_name": "ICICI Bank", "sender_keys": ["ICICIB", "ICICIT"], "body_aliases": ["icici bank", "icici"]},
            {"code": "SBICARD", "display_name": "SBI Card", "sender_keys": ["SBICRD", "SBICARD"], "body_aliases": ["sbi credit card", "sbi card", "sbicard", "sbi"]},
            {"code": "AXIS", "display_name": "Axis Bank", "sender_keys": ["AXISBK", "AXISCC"], "body_aliases": ["axis bank", "axis"]},
            {"code": "KOTAK", "display_name": "Kotak Mahindra Bank", "sender_keys": ["KOTAKB", "KOTAKC"], "body_aliases": ["kotak mahindra", "kotak bank", "kotak"]},
            {"code": "AMEX", "display_name": "American Express", "sender_keys": ["AMEXIN", "AMEX"], "body_aliases": ["american express", "amex"]},
            {"code": "IDFC", "display_name": "IDFC FIRST Bank", "sender_keys": ["IDFCFB", "IDFCBK"], "body_aliases": ["idfc first", "idfc"]},
            {"code": "AU", "display_name": "AU Small Finance Bank", "sender_keys": ["AUBANK", "AUCARD"], "body_aliases": ["au small finance", "au bank"]},
            {"code": "ONECARD", "display_name": "OneCard", "sender_keys": ["ONECRD", "ONECARD"], "body_aliases": ["onecard", "one card"]},
            {"code": "RBL", "display_name": "RBL Bank", "sender_keys": ["RBLBNK", "RBLCRD"], "body_aliases": ["rbl bank", "rbl"]},
            {"code": "YES", "display_name": "YES Bank", "sender_keys": ["YESBNK", "YESBCC"], "body_aliases": ["yes bank"]},
            {"code": "INDUSIND", "display_name": "IndusInd Bank", "sender_keys": ["INDUSB", "INDUSL"], "body_aliases": ["indusind"]},
            {"code": "HSBC", "display_name": "HSBC", "sender_keys": ["HSBCIN", "HSBCBK"], "body_aliases": ["hsbc"]},
            {"code": "SCB", "display_name": "Standard Chartered", "sender_keys": ["SCBANK", "STANCB"], "body_aliases": ["standard chartered", "stanchart"]},
            {"code": "FEDERAL", "display_name": "Federal Bank", "sender_keys": ["FEDBNK", "FEDFIB"], "body_aliases": ["federal bank"]},
            {"code": "BOB", "display_name": "BOBCARD", "sender_keys": ["BOBCRD", "BOBTXN", "BOBCARD"], "body_aliases": ["bobcard", "bank of baroda"]},
        ]
        return SenderRegistryResponse(version=1, banks=banks)


expense_service = ExpenseService()
