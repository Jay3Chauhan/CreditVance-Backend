"""
SMS Expense Tracking SQLAlchemy Models.
Stores parsed credit card transactions, bill notices, merchant catalog,
milestone rules, consent audit ledger, and batch idempotency records.

PCI-DSS & DPDP Safe:
- SMS text bodies, full PANs (16 digits), and CVVs are NEVER accepted or persisted.
- Data retention and user-level deletion controls conform to DPDP Rules 2025.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.card import CreditCard
    from app.models.user import User
    from app.models.user_card import UserCard


class Merchant(Base, TimestampMixin):
    """
    Global user-agnostic merchant dictionary.
    Used for MCC and alias-based merchant enrichment.
    """
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    mcc: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    aliases: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)

    transactions: Mapped[List["CardTransaction"]] = relationship(
        "CardTransaction", back_populates="merchant_ref"
    )

    def __repr__(self) -> str:
        return f"<Merchant(id={self.id}, canonical_name='{self.canonical_name}', category='{self.category}')>"


class CardTransaction(Base, TimestampMixin):
    """
    Structured card spend transactions extracted on-device from SMS alerts or entered manually.
    Raw SMS bodies are strictly forbidden and never stored.
    """
    __tablename__ = "card_transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_hash", name="uq_card_transactions_user_hash"),
        Index("ix_card_transactions_user_occurred", "user_id", "occurred_at"),
        Index("ix_card_transactions_user_card", "user_id", "user_card_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dedupe_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    amount_inr: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)

    type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="debit"
    )  # debit, refund, reversal, payment, credit
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    bank_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    card_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )

    merchant_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    merchant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True
    )
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="device"
    )  # device, server, user

    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")  # card, upi, unknown
    available_limit: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="sms")  # sms, pastedSms, manual, server
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, default=1.0)

    # Soft delete / tombstone: if user hides or deletes a transaction, it is not re-imported
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    user_card: Mapped[Optional["UserCard"]] = relationship("UserCard")
    merchant_ref: Mapped[Optional["Merchant"]] = relationship("Merchant", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<CardTransaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, merchant='{self.merchant_name}')>"


class CardBill(Base, TimestampMixin):
    """
    Statement and payment due notices extracted from bank SMS alerts.
    """
    __tablename__ = "card_bills"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_hash", name="uq_card_bills_user_hash"),
        Index("ix_card_bills_user_due", "user_id", "due_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dedupe_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    bank_code: Mapped[str] = mapped_column(String(30), nullable=False)
    card_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    user_card_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True
    )

    total_due: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    minimum_due: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    noticed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
    user_card: Mapped[Optional["UserCard"]] = relationship("UserCard")

    def __repr__(self) -> str:
        return f"<CardBill(id={self.id}, user_id={self.user_id}, bank='{self.bank_code}', total_due={self.total_due})>"


class CardMilestoneRule(Base, TimestampMixin):
    """
    Per-catalog-card milestone rules (e.g. annual fee waiver, bonus EDGE miles, Taj vouchers).
    """
    __tablename__ = "card_milestone_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reward_description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # fee_waiver, bonus_rewards, lounge_access, voucher
    period: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # calendar_month, calendar_quarter, calendar_year, card_year
    target_spend: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    excluded_categories: Mapped[List[str]] = mapped_column(
        JSON, default=lambda: ["rent", "wallet", "fees"], nullable=False
    )
    valid_from: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)

    card: Mapped["CreditCard"] = relationship("CreditCard")

    def __repr__(self) -> str:
        return f"<CardMilestoneRule(id={self.id}, card_id={self.card_id}, title='{self.title}', target={self.target_spend})>"


class ExpenseConsent(Base):
    """
    Append-only consent ledger complying with DPDP Act 2023 & DPDP Rules 2025.
    Logs purpose, status, notice version, timestamp, and client platform.
    """
    __tablename__ = "expense_consents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(100), default="sms_card_expense_tracking", nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # granted, declined, withdrawn
    notice_version: Mapped[str] = mapped_column(String(50), default="sms-v1", nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    platform: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    ip_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ExpenseConsent(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class ExpenseIdempotency(Base):
    """
    Caches batch ingestion responses by (user_id, idempotency_key) for 24 hours.
    Prevents duplicate processing and guarantees safe network retries.
    """
    __tablename__ = "expense_idempotency"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    idem_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ExpenseIdempotency(user_id={self.user_id}, idem_key='{self.idem_key}')>"
