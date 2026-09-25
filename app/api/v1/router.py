"""
Master API v1 Router Aggregation.
"""

from fastapi import APIRouter
from app.api.v1.admin_sync import router as admin_sync_router
from app.api.v1.advisor import router as advisor_router
from app.api.v1.auth import router as auth_router
from app.api.v1.banks import router as banks_router
from app.api.v1.calculator import router as calculator_router
from app.api.v1.cards import router as cards_router
from app.api.v1.categories import router as categories_router
from app.api.v1.health import router as health_router
from app.api.v1.user_cards import router as user_cards_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(cards_router)
api_v1_router.include_router(banks_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(user_cards_router)
api_v1_router.include_router(advisor_router)
api_v1_router.include_router(calculator_router)
api_v1_router.include_router(admin_sync_router)
