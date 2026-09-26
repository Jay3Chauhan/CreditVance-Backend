"""
Home and in-app banner placements.
Banners are visual slots. They deep-link into a screen, card, category, URL, or promotion.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Banner(Base, TimestampMixin):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    placement: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    cta_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    action_type: Mapped[str] = mapped_column(String(30), default="screen", nullable=False)
    action_target: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    badge_text: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    background_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    accent_color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(20), default="all", nullable=False)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    impression_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<Banner(id={self.id}, slug='{self.slug}', placement='{self.placement}')>"
