"""
Per-user push preferences.
Missing row means the defaults: payment and statement reminders on, product updates off.
"""

from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class NotificationPreference(Base, TimestampMixin):
    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    due_reminder_days: Mapped[List[int]] = mapped_column(JSON, default=list, nullable=False)
    statement_reminder_days: Mapped[List[int]] = mapped_column(JSON, default=list, nullable=False)
    product_updates: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="notification_preference")

    def __repr__(self) -> str:
        return f"<NotificationPreference(user_id={self.user_id}, push_enabled={self.push_enabled})>"
