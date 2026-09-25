"""
Advisor Recommendation Pydantic Schemas.
Powers the "Which card should I use right now?" decision engine.
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.card import CardSummaryResponse


class CardRecommendationRequest(BaseModel):
    category_slug: str = Field(..., description="Spend category (e.g. 'Dining', 'Grocery', 'Flights', 'Fuel', 'Online Shopping', 'Rent')")
    spend_amount: float = Field(..., gt=0, description="Spend amount in INR (e.g. 2500.00)")
    merchant_name: Optional[str] = Field(None, description="Optional merchant name (e.g. 'Swiggy', 'Zomato', 'Amazon', 'MakeMyTrip')")
    is_international: bool = Field(False, description="Set True if transaction is in foreign currency")


class RecommendedCardItem(BaseModel):
    user_card_id: Optional[int] = None
    card_id: int
    card_title: str
    card_slug: str
    bank_name: str
    bank_logo_url: Optional[str] = None
    card_image_url: Optional[str] = None
    nickname: Optional[str] = None
    last_4_digits: Optional[str] = None
    rank: int
    estimated_reward_points: float
    estimated_reward_value_inr: float
    effective_return_percent: float
    reward_type: str = "points"  # "cashback" or "points"
    benefit_highlight: str
    notes_or_exclusions: Optional[str] = None


class CardRecommendationResponse(BaseModel):
    category_slug: str
    spend_amount: float
    top_recommendation: Optional[RecommendedCardItem] = None
    alternative_cards: List[RecommendedCardItem] = Field(default_factory=list)
    market_benchmark_card: Optional[RecommendedCardItem] = Field(None, description="Best market card overall for this spend")
    insights: List[str] = Field(default_factory=list)
