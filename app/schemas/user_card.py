from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.card import CardSummaryResponse


class AddUserCardRequest(BaseModel):
    card_id: int = Field(..., description="ID of the credit card model from our catalog")
    nickname: Optional[str] = Field(None, max_length=100, description="Optional custom nickname (e.g., 'Primary Fuel Card')")
    last_4_digits: Optional[str] = Field(None, min_length=4, max_length=4, description="Last 4 digits for UI display (e.g. '1234')")
    billing_cycle_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month when bill generates (e.g. 15)")
    statement_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month when statement generates (e.g. 15)")
    due_day: Optional[int] = Field(None, ge=1, le=31, description="Day of month when payment is due (e.g. 5)")
    sort_order: Optional[int] = Field(0, description="Display order in wallet")


class UpdateUserCardRequest(BaseModel):
    nickname: Optional[str] = Field(None, max_length=100)
    last_4_digits: Optional[str] = Field(None, min_length=4, max_length=4)
    billing_cycle_day: Optional[int] = Field(None, ge=1, le=31)
    statement_day: Optional[int] = Field(None, ge=1, le=31)
    due_day: Optional[int] = Field(None, ge=1, le=31)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class WalletOrderRequest(BaseModel):
    ids: List[int] = Field(..., description="Ordered list of user_card IDs reflecting desired display position")


class UserCardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    card_id: int
    nickname: Optional[str] = None
    last_4_digits: Optional[str] = None
    billing_cycle_day: Optional[int] = None
    statement_day: Optional[int] = None
    due_day: Optional[int] = None
    sort_order: int = 0
    is_active: bool
    created_at: datetime
    updated_at: datetime
    card: Optional[CardSummaryResponse] = None

