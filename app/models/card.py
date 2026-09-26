"""
Credit Card Catalog SQLAlchemy Model.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.bank import Bank
    from app.models.card_tab import CardTab
    from app.models.user_card import UserCard


class CreditCard(Base, TimestampMixin):
    __tablename__ = "credit_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Bank Association
    bank_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("banks.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Fees & Financials
    joining_fee: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    renewal_fee: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    fee_waiver_spend: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    forex_markup_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    apr_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    add_on_card_fee: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Reward Rates (Raw string + parsed min/max floats for sorting)
    return_percentage_raw: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    return_min_percent: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    return_max_percent: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    point_value_inr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Classification & Flags
    network_type: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    lounge_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    benefit_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    category_slugs: Mapped[List[str]] = mapped_column(JSON, default=list)

    is_fd_card: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_business_card: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_currently_issuing: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Media & Links
    web_logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    card_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    apply_link: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Editorial & Overviews
    overview_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    best_suited: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    bank: Mapped["Bank"] = relationship("Bank", back_populates="cards")
    tabs: Mapped[List["CardTab"]] = relationship(
        "CardTab", back_populates="card", cascade="all, delete-orphan"
    )
    user_holdings: Mapped[List["UserCard"]] = relationship(
        "UserCard", back_populates="card", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CreditCard(id={self.id}, title='{self.title}', slug='{self.slug}')>"
