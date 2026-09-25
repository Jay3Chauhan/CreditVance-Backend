"""
User Card Portfolio (Wallet) Pydantic Schemas.
Stores only non-sensitive card metadata. Full card numbers are stored locally in the Flutter app.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.card import CardSummaryResponse


class AddUserCardRequest(BaseModel):
    card_id: int = Field(..., description="ID of the credit card model from our catalog")
    nickname: Optional[str] = Field(None, max_length=100, description="Optional custom nickname (e.g., 'Primary Fuel Card')")
    last_4_digits: Optional[str] = Field(None, min_length=4, max_length=4, description="Last 4 digits for UI display (e.g. '1234')")
    billing_cycle_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month when bill generates (e.g. 15)")


class UpdateUserCardRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=100)
    last_4_digits: Optional[str] = Field(None, min_length=4, max_length=4)
    billing_cycle_day: Optional[int] = Field(None, ge=1, le=31)
    is_active: Optional[bool] = None


class UserCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    card_id: int
    nickname: Optional[str] = None
    last_4_digits: Optional[str] = None
    billing_cycle_day: Optional[int] = None
    is_active: bool
    card: Optional[CardSummaryResponse] = None
