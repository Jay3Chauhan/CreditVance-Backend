"""
Spend Category SQLAlchemy Model.
"""

from typing import Optional
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin


class SpendCategory(Base, TimestampMixin):
    __tablename__ = "spend_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    savesage_category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<SpendCategory(id={self.id}, name='{self.name}', slug='{self.slug}')>"
