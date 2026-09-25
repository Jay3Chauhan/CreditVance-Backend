"""
Reward Calculator Pydantic Schemas.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class RewardCalculateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    card_id: int = Field(..., alias="cardId", description="Target card ID")
    category_slug: str = Field(..., alias="categorySlug", description="Spend category name (e.g. 'Dining', 'Grocery')")
    spend_amount: float = Field(..., alias="spendAmount", gt=0, description="Spend amount in INR (e.g. 10000)")
    bank_id: Optional[int] = Field(None, alias="bankId", description="Optional bank ID")


class CardRewardSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card_id: int
    card_name: str
    bank_name: str
    card_image_link: Optional[str] = None
    reward_points: float
    reward_worth: float
    is_cashback_card: bool = False
    return_percentage: float = 0.0


class RewardCalculateResponse(BaseModel):
    user_card: CardRewardSummary
    suggested_card: CardRewardSummary
    annual_savings: float
    suggested_card_is_same: bool
