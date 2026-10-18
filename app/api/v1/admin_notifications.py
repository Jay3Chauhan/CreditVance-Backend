"""
Admin push sends. Requires X-Admin-API-Key or an admin JWT.
A broadcast without user_id reaches only accounts that opted into product updates.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_admin_key
from app.schemas.common import ApiResponse
from app.schemas.notification import AdminPushRequest, PushDispatchResponse
from app.services.notification_service import notification_service

router = APIRouter(prefix="/admin/notifications", tags=["Admin Notifications"])


@router.post("/send", response_model=ApiResponse[PushDispatchResponse])
async def admin_send_push(
    req: AdminPushRequest,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a push to one account, or to every account with product updates enabled.
    Payment reminders are not sent from here; the daily job owns those.
    """
    if req.user_id is not None:
        result = await notification_service.send_to_user(
            db,
            user_id=req.user_id,
            title=req.title,
            body=req.body,
            route=req.route,
            notification_type="admin",
        )
    else:
        result = await notification_service.broadcast_product_update(
            db, title=req.title, body=req.body, route=req.route
        )
    return ApiResponse(message="Push processed.", data=result)
