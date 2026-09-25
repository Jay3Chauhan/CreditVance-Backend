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
    savesage_category_id: Optional[int] = None
