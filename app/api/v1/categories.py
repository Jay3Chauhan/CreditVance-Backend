"""
Spend Categories API Router.
"""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.category import CategoryResponse
from app.schemas.common import ApiResponse
from app.services.card_service import card_service

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=ApiResponse[List[CategoryResponse]])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Retrieves all 16 supported spend categories (Dining, Flights, Grocery, etc.)."""
    cats = await card_service.get_all_categories(db)
    return ApiResponse(
        data=[CategoryResponse.model_validate(c) for c in cats]
    )
