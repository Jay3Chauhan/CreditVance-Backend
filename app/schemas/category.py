"""
Spend Category Pydantic Schemas.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    icon_url: Optional[str] = None
    icon_key: Optional[str] = None
    display_order: int = 0
    savesage_category_id: Optional[int] = None
