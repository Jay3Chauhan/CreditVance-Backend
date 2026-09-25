"""
Bank SQLAlchemy Model.
"""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.card import CreditCard


class Bank(Base, TimestampMixin):
    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    savesage_bank_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Relationships
    cards: Mapped[List["CreditCard"]] = relationship(
        "CreditCard", back_populates="bank", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Bank(id={self.id}, name='{self.name}', slug='{self.slug}')>"
