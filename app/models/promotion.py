"""
Editorial guides and promotional offers shown on home, catalog, and card detail.
Real bank campaigns can be added later through the admin API. Seeded rows are
product guides, not invented cashback claims.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.card import CreditCard


class Promotion(Base, TimestampMixin):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    badge: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    promo_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    highlight_value: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    card_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("credit_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category_slug: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    cta_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    action_type: Mapped[str] = mapped_column(String(30), default="screen", nullable=False)
    action_target: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    impression_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    card: Mapped[Optional["CreditCard"]] = relationship("CreditCard")

    def __repr__(self) -> str:
        return f"<Promotion(id={self.id}, slug='{self.slug}', type='{self.promo_type}')>"
