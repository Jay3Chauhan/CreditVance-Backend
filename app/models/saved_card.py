"""
Shortlist of catalog cards a user is considering.
This is separate from the wallet, which only holds cards the user already owns.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.card import CreditCard
    from app.models.user import User


class SavedCard(Base, TimestampMixin):
    __tablename__ = "saved_cards"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_saved_card"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )

    user: Mapped["User"] = relationship("User", back_populates="saved_cards")
    card: Mapped["CreditCard"] = relationship("CreditCard")

    def __repr__(self) -> str:
        return f"<SavedCard(id={self.id}, user_id={self.user_id}, card_id={self.card_id})>"
