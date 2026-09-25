"""
Card Tab SQLAlchemy Model.
Stores discrete tab data (earn-categories, lounge-access, etc.) as structured JSON/JSONB.
"""

from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.card import CreditCard


class CardTab(Base, TimestampMixin):
    __tablename__ = "card_tabs"
    __table_args__ = (
        UniqueConstraint("card_id", "tab_name", name="uq_card_tab"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tab_name: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # earn-categories, benefits-and-offers, lounge-access, milestones, redemption-options

    raw_content: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    card: Mapped["CreditCard"] = relationship("CreditCard", back_populates="tabs")

    def __repr__(self) -> str:
        return f"<CardTab(card_id={self.card_id}, tab_name='{self.tab_name}')>"
