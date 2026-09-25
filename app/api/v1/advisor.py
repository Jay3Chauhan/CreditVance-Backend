"""
Smart Advisor API Router.
Answers: "Which card should I use for this purchase?"
"""

from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_optional_user
from app.models.user import User
from app.schemas.advisor import (
    CardRecommendationRequest,
    CardRecommendationResponse,
)
from app.schemas.common import ApiResponse
from app.services.advisor_service import advisor_service

router = APIRouter(prefix="/advisor", tags=["Smart Advisor"])


@router.post("/recommend", response_model=ApiResponse[CardRecommendationResponse])
async def recommend_best_card(
    req: CardRecommendationRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ranks the user's credit cards for a specific transaction (amount + category)
    and highlights the optimal card with estimated cashback/reward value.
    If the user is not authenticated or has no cards, returns market leaders.
    """
    user_id = user.id if user else 0
    rec = await advisor_service.get_recommendation_for_user(
        db=db,
        user_id=user_id,
        req=req,
    )
    return ApiResponse(
        message="Card recommendations generated successfully.",
        data=rec,
    )
