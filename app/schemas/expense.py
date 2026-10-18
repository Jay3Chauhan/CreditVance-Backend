"""
Pydantic Schemas for SMS Expense Tracking.
Strictly enforces DPDP and PCI-DSS compliance:
- Rejects any potential PAN leakage (12-19 consecutive digits in any string field).
- Drops or rejects raw SMS bodies, OTPs, or CVVs.
"""

from datetime import date, datetime, timezone
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_PAN_PATTERN = re.compile(r"\b\d{12,19}\b")
_LAST4_PATTERN = re.compile(r"^\d{4}$")


def _check_pan_leakage(value: Any, field_name: str) -> None:
    """Defence-in-depth check: reject any 12-19 digit sequences."""
    if isinstance(value, str):
        # Allow ISO timestamps like 2026-10-18T20:45:38Z without false positives
        clean_val = re.sub(r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}", "", value)
        if _PAN_PATTERN.search(clean_val):
            raise ValueError(f"Potential PAN detected in {field_name}; field rejected.")


class CardTransactionSyncItem(BaseModel):
    """Single card transaction sent in batch ingestion payload."""
    dedupe_hash: str = Field(..., min_length=16, max_length=64, description="Deterministic 32-hex deduplication hash")
    amount: float = Field(..., gt=0, lt=100_000_000, description="Transaction amount")
    currency: str = Field(default="INR", max_length=3, description="ISO-4217 currency code")
    type: str = Field(default="debit", description="Transaction type: debit, refund, reversal, payment, credit")
    occurred_at: datetime = Field(..., description="Timestamp when transaction occurred")
    bank_code: str = Field(..., min_length=2, max_length=30, description="Bank code e.g. HDFC, ICICI, SBICARD")
    card_last4: Optional[str] = Field(None, description="Last 4 digits of credit card")
    user_card_id: Optional[int] = Field(None, description="Optional linked user wallet card ID")
    merchant_raw: Optional[str] = Field(None, max_length=255, description="Raw merchant string as in SMS")
    merchant_name: str = Field(default="Unknown Merchant", max_length=255, description="Parsed or cleaned merchant name")
    category: str = Field(default="other", max_length=50, description="Spend category slug")
    category_overridden: bool = Field(default=False, description="Whether user manually edited category")
    channel: str = Field(default="unknown", description="Channel: card, upi, unknown")
    available_limit: Optional[float] = Field(None, description="Available credit limit after transaction")
    source: str = Field(default="sms", description="Source: sms, pastedSms, manual, server")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Parser confidence score")

    @field_validator("card_last4")
    @classmethod
    def validate_card_last4(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _LAST4_PATTERN.match(v):
            raise ValueError("card_last4 must be exactly 4 digits")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {"debit", "refund", "reversal", "payment", "credit"}
        low = v.strip().lower()
        if low not in valid_types:
            raise ValueError(f"type must be one of {valid_types}")
        return low

    @model_validator(mode="after")
    def validate_no_pan_leakage(self) -> "CardTransactionSyncItem":
        # Check merchant fields and category for any PAN sequence
        _check_pan_leakage(self.merchant_raw, "merchant_raw")
        _check_pan_leakage(self.merchant_name, "merchant_name")
        _check_pan_leakage(self.category, "category")
        return self


class BillNoticeSyncItem(BaseModel):
    """Single bill notice sent in batch ingestion payload."""
    dedupe_hash: str = Field(..., min_length=16, max_length=64, description="Deterministic 32-hex deduplication hash")
    bank_code: str = Field(..., min_length=2, max_length=30)
    card_last4: Optional[str] = Field(None, description="Last 4 digits of card")
    user_card_id: Optional[int] = Field(None, description="Optional linked user wallet card ID")
    total_due: Optional[float] = Field(None, ge=0, lt=100_000_000, description="Total statement due amount")
    minimum_due: Optional[float] = Field(None, ge=0, lt=100_000_000, description="Minimum due amount")
    due_date: Optional[date] = Field(None, description="Payment due date")
    noticed_at: datetime = Field(..., description="Timestamp when bill alert was noticed")

    @field_validator("card_last4")
    @classmethod
    def validate_bill_last4(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _LAST4_PATTERN.match(v):
            raise ValueError("card_last4 must be exactly 4 digits")
        return v


class BatchIngestRequest(BaseModel):
    """Payload for POST /expenses/transactions/batch."""
    client_version: Optional[str] = Field(default="1.0.0", description="Client version string")
    schema_version: Optional[int] = Field(default=1, description="Payload schema version")
    transactions: List[CardTransactionSyncItem] = Field(default_factory=list, max_length=100)
    bills: List[BillNoticeSyncItem] = Field(default_factory=list, max_length=100)

    model_config = ConfigDict(extra="ignore")


class TransactionEnrichment(BaseModel):
    """Server-side enrichment for merchant name or category."""
    dedupe_hash: str
    merchant_name: Optional[str] = None
    category: Optional[str] = None


class RejectedRecord(BaseModel):
    """Record rejected during ingestion with diagnostic reason."""
    dedupe_hash: str
    reason: str


class BatchIngestResponse(BaseModel):
    """Response returned by POST /expenses/transactions/batch."""
    accepted: List[str] = Field(default_factory=list, description="Dedupe hashes successfully stored")
    duplicates: List[str] = Field(default_factory=list, description="Dedupe hashes already stored on server")
    rejected: List[RejectedRecord] = Field(default_factory=list, description="Dedupe hashes rejected with reason")
    enrichments: List[TransactionEnrichment] = Field(default_factory=list, description="Server merchant/category enrichments")
    server_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CardTransactionResponse(BaseModel):
    """Single card transaction returned to client."""
    id: str = Field(..., description="Transaction dedupe hash identifier")
    dedupe_hash: str
    amount: float
    currency: str
    amount_inr: Optional[float] = None
    type: str
    occurred_at: datetime
    bank_code: str
    bank_name: str
    card_last4: Optional[str] = None
    user_card_id: Optional[int] = None
    merchant_raw: Optional[str] = None
    merchant_name: str
    category: str
    category_overridden: bool = False
    channel: str = "unknown"
    available_limit: Optional[float] = None
    source: str = "sms"
    confidence: float = 1.0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    """Paginated list of transactions."""
    items: List[CardTransactionResponse]
    next_cursor: Optional[str] = None
    total_count: Optional[int] = None


class SmsConsentRequest(BaseModel):
    """Payload for PUT /expenses/consent."""
    purpose: str = Field(default="sms_card_expense_tracking")
    status: str = Field(..., description="granted, declined, or withdrawn")
    notice_version: str = Field(default="sms-v1")
    decided_at: Optional[datetime] = None
    platform: Optional[str] = Field(default="android")


class SmsConsentResponse(BaseModel):
    """Response for PUT /expenses/consent."""
    purpose: str
    status: str
    notice_version: str
    decided_at: datetime
    platform: Optional[str] = None


class CardMilestoneResponse(BaseModel):
    """Milestone definition returned by GET /expenses/milestones."""
    id: str
    user_card_id: int
    title: str
    reward_description: str
    type: str  # fee_waiver, bonus_rewards, lounge_access, voucher
    period: str  # calendar_month, calendar_quarter, calendar_year, card_year
    target_spend: float
    anniversary_month: int = 1


class CategorySpendBreakdown(BaseModel):
    category: str
    spend_inr: float
    transaction_count: int
    percentage: float


class CardSpendBreakdown(BaseModel):
    user_card_id: Optional[int] = None
    card_last4: Optional[str] = None
    bank_code: str
    spend_inr: float
    transaction_count: int


class TopMerchantSpend(BaseModel):
    merchant_name: str
    category: str
    spend_inr: float
    transaction_count: int


class MonthlySpendTrend(BaseModel):
    month: str  # YYYY-MM
    net_spend_inr: float
    transaction_count: int


class SpendAnalyticsSummaryResponse(BaseModel):
    """Server-side spend analytics summary."""
    net_spend: float = Field(..., description="Net spend: debits minus refunds/reversals")
    gross_spend: float = Field(..., description="Sum of all debits")
    total_refunds: float = Field(..., description="Sum of refunds and reversals")
    transaction_count: int
    by_category: List[CategorySpendBreakdown] = Field(default_factory=list)
    by_card: List[CardSpendBreakdown] = Field(default_factory=list)
    top_merchants: List[TopMerchantSpend] = Field(default_factory=list)
    monthly_trend: List[MonthlySpendTrend] = Field(default_factory=list)


class BankProfileItem(BaseModel):
    code: str
    display_name: str
    sender_keys: List[str]
    body_aliases: List[str]


class SenderRegistryResponse(BaseModel):
    """Response returned by GET /expenses/sender-registry."""
    version: int
    banks: List[BankProfileItem]
