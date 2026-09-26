"""
Device Token Model for Push Reminders and Notifications (APNs / FCM).
PCI-DSS Safe: Only records anonymous device push tokens and user linkages.
"""

from typing import Optional
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class DeviceToken(Base, TimestampMixin):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    token: Mapped[str] = mapped_column(String(500), unique=True, index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="android", nullable=False)  # "android", "ios", "web"

    def __repr__(self) -> str:
        return f"<DeviceToken(id={self.id}, platform='{self.platform}')>"
