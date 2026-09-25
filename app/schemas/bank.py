"""
Bank Pydantic Schemas.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict


class BankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    logo_url: Optional[str] = None
    savesage_bank_id: Optional[int] = None
