"""
Typeahead search for the catalog.
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.common import ApiResponse
from app.schemas.content import SearchSuggestion
from app.services.discovery_service import discovery_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/suggest", response_model=ApiResponse[List[SearchSuggestion]])
async def suggest_cards(
    q: str = Query(..., min_length=1, max_length=40, description="Card, bank, or slug fragment"),
    limit: int = Query(8, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    """Lightweight suggestions for the search field. Debounce on the client."""
    items = await discovery_service.suggest(db, q, limit)
    return ApiResponse(data=items)
