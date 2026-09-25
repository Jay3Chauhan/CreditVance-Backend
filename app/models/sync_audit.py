"""
Sync Audit Log SQLAlchemy Model.
Tracks ingestion history, status, card counts, errors, and performance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class SyncAuditLog(Base):
    __tablename__ = "sync_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_type: Mapped[str] = mapped_column(String(50), default="scheduled")  # scheduled, manual, initial
    status: Mapped[str] = mapped_column(String(50), default="running")  # running, completed, failed
    cards_fetched: Mapped[int] = mapped_column(Integer, default=0)
    tabs_fetched: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<SyncAuditLog(id={self.id}, status='{self.status}', cards={self.cards_fetched})>"
