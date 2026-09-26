"""
Master API v1 Router Aggregation.
"""

from fastapi import APIRouter
from app.api.v1.admin_content import router as admin_content_router
from app.api.v1.admin_sync import router as admin_sync_router
from app.api.v1.advisor import router as advisor_router
from app.api.v1.auth import router as auth_router
from app.api.v1.banks import router as banks_router
from app.api.v1.banners import router as banners_router
from app.api.v1.calculator import router as calculator_router
from app.api.v1.cards import router as cards_router
from app.api.v1.categories import router as categories_router
from app.api.v1.health import router as health_router
from app.api.v1.home import router as home_router
from app.api.v1.meta import router as meta_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.promotions import router as promotions_router
from app.api.v1.saved_cards import router as saved_cards_router
from app.api.v1.search import router as search_router
from app.api.v1.user_cards import router as user_cards_router
from app.api.v1.wallet import router as wallet_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(cards_router)
api_v1_router.include_router(banks_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(user_cards_router)
api_v1_router.include_router(wallet_router)
api_v1_router.include_router(advisor_router)
api_v1_router.include_router(calculator_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(meta_router)
api_v1_router.include_router(banners_router)
api_v1_router.include_router(promotions_router)
api_v1_router.include_router(home_router)
api_v1_router.include_router(search_router)
api_v1_router.include_router(saved_cards_router)
api_v1_router.include_router(admin_content_router)
api_v1_router.include_router(admin_sync_router)

