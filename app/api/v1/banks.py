"""
Banks Catalog API Router.
"""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.bank import BankResponse
from app.schemas.common import ApiResponse
from app.services.card_service import card_service

router = APIRouter(prefix="/banks", tags=["Banks"])


@router.get("", response_model=ApiResponse[List[BankResponse]])
async def list_banks(db: AsyncSession = Depends(get_db)):
    """Retrieves all indexed issuing banks."""
    banks = await card_service.get_all_banks(db)
    return ApiResponse(
        data=[BankResponse.model_validate(b) for b in banks]
    )
