"""
User Card Portfolio SQLAlchemy Model.
Manages which cards a user owns in their digital wallet.
PCI-DSS Safe: Full 16-digit PANs and CVVs are held purely in local frontend secure storage.
"""

from typing import TYPE_CHECKING, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.card import CreditCard
    from app.models.user import User


class UserCard(Base, TimestampMixin):
    __tablename__ = "user_cards"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", "nickname", name="uq_user_card_instance"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    card_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("credit_cards.id", ondelete="CASCADE"), nullable=False, index=True
    )

    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_4_digits: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    billing_cycle_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="cards")
    card: Mapped["CreditCard"] = relationship("CreditCard", back_populates="user_holdings")

    def __repr__(self) -> str:
        return f"<UserCard(id={self.id}, user_id={self.user_id}, card_id={self.card_id})>"
