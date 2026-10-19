"""
Metadata & Application Configuration Router.
Provides legal compliance links, app feature flags, and version deprecation policies.
"""

from fastapi import APIRouter
from app.schemas.common import ApiResponse
from app.schemas.content import FaqResponse
from app.schemas.meta import AppConfigResponse, LegalMetaResponse
from app.services.card_service import CATEGORY_METADATA
from app.services.discovery_service import discovery_service

router = APIRouter(prefix="/meta", tags=["Metadata & Config"])


@router.get("/legal", response_model=ApiResponse[LegalMetaResponse])
async def get_legal_links():
    """
    Returns stable public URLs for privacy policy, terms of service,
    and store compliance data deletion policies.
    """
    return ApiResponse(
        data=LegalMetaResponse(
            privacy_policy_url="https://app.notion.com/p/Privacy-Policy-3fda57849d8e80549503fdaeaf1f8d3f",
            terms_of_service_url="https://app.notion.com/p/Terms-N-Conditions-3fda57849d8e80188c4fcb708672d4de",
            contact_email="support@creditvance.app",
            data_deletion_policy_url="https://app.notion.com/p/Account-and-Data-Deletion-Policy-for-Credvert-3fda57849d8e80ed8dafe31046139ef3",
        )
    )


@router.get("/config", response_model=ApiResponse[AppConfigResponse])
async def get_app_config():
    """
    Returns dynamic application configurations including minimum app version,
    maintenance banner status, and curated category display order.
    """
    category_order = list(CATEGORY_METADATA.keys())
    return ApiResponse(
        data=AppConfigResponse(
            min_app_version="1.0.0",
            latest_app_version="1.1.0",
            maintenance_mode=False,
            maintenance_message=None,
            curated_category_order=category_order,
            feature_flags={
                "annual_reward_calculator": True,
                "international_forex_advisor": True,
                "due_date_push_reminders": True,
                "drag_reorder_wallet": True,
                "dynamic_lounge_filters": True,
                "home_feed": True,
                "banners": True,
                "promotions": True,
                "card_compare": True,
                "search_suggest": True,
                "saved_cards": True,
                "wallet_insights": True,
                "faq": True,
                "firebase_push": True,
                "sms_expense_tracking": True,
            },
        )
    )


@router.get("/faq", response_model=ApiResponse[FaqResponse])
async def get_faq():
    """Answers for wallet, advisor, fees, reminders, privacy, and promotions."""
    return ApiResponse(data=discovery_service.faq())
