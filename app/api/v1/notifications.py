"""
Notifications, device registration, and Firebase push.
PCI-DSS safe: reminders use the day of the month only. Card numbers are never read.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, get_optional_user
from app.core.exceptions import NotFoundError
from app.models.card import CreditCard
from app.models.device_token import DeviceToken
from app.models.user import User
from app.models.user_card import UserCard
from app.schemas.common import ApiResponse
from app.schemas.device_token import (
    DeviceTokenRegisterRequest,
    DeviceTokenResponse,
    UpcomingRemindersResponse,
)
from app.schemas.notification import (
    NotificationHistoryItem,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    PushDispatchResponse,
    PushStatusResponse,
)
from app.services.firebase_push_service import firebase_push_service
from app.services.notification_service import notification_service
from app.services.reminder_service import build_reminders

router = APIRouter(prefix="/notifications", tags=["Notifications & Reminders"])


@router.get("/status", response_model=ApiResponse[PushStatusResponse])
async def push_status():
    """Whether this server can send Firebase pushes. Does not expose credentials."""
    raw = firebase_push_service.status()
    return ApiResponse(
        data=PushStatusResponse(
            enabled=bool(raw["enabled"]),
            configured=bool(raw["configured"]),
            initialized=bool(raw["initialized"]),
            project_id=raw["project_id"] if isinstance(raw["project_id"], str) else None,
            android_channel_id=str(raw["android_channel_id"]),
        )
    )


@router.post(
    "/device-token",
    response_model=ApiResponse[DeviceTokenResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register_device_token(
    req: DeviceTokenRegisterRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Registers or updates an FCM registration token.
    Call this after login and whenever Firebase refreshes the token.
    A token already stored for another account is moved to the current account.
    """
    stmt = select(DeviceToken).where(DeviceToken.token == req.device_token.strip())
    existing = (await db.execute(stmt)).scalar_one_or_none()
    user_id = user.id if user else None

    if existing:
        existing.user_id = user_id
        existing.platform = req.platform
        target = existing
    else:
        target = DeviceToken(
            user_id=user_id,
            token=req.device_token.strip(),
            platform=req.platform,
        )
        db.add(target)

    await db.commit()
    await db.refresh(target)
    return ApiResponse(
        message="Device token registered successfully.",
        data=DeviceTokenResponse.model_validate(target),
    )


@router.delete("/device-token", response_model=ApiResponse[None])
async def remove_device_token(
    device_token: str = Query(..., min_length=10, max_length=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Call this on logout so a signed-out phone stops receiving this account's reminders."""
    stmt = select(DeviceToken).where(
        DeviceToken.token == device_token.strip(),
        DeviceToken.user_id == user.id,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if not existing:
        raise NotFoundError("Device token not found for this account.")
    await db.delete(existing)
    await db.commit()
    return ApiResponse(message="Device token removed.", data=None)


@router.get("/preferences", response_model=ApiResponse[NotificationPreferencesResponse])
async def get_notification_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reminder offsets and the product-news opt-in. Defaults apply until the user saves."""
    prefs = await notification_service.get_preferences(db, user.id)
    return ApiResponse(data=prefs)


@router.patch("/preferences", response_model=ApiResponse[NotificationPreferencesResponse])
async def update_notification_preferences(
    req: NotificationPreferencesUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update any subset of push preferences. 0 in a day list means 'on that day'."""
    prefs = await notification_service.update_preferences(db, user.id, req)
    return ApiResponse(message="Notification preferences saved.", data=prefs)


@router.post("/test", response_model=ApiResponse[PushDispatchResponse])
async def send_test_notification(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sends one test push to every device registered on this account."""
    result = await notification_service.send_test_push(db, user.id)
    return ApiResponse(message="Test notification processed.", data=result)


@router.get("/history", response_model=ApiResponse[List[NotificationHistoryItem]])
async def notification_history(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent pushes for this account, newest first. Useful as an in-app inbox."""
    items = await notification_service.list_history(db, user.id, limit)
    return ApiResponse(data=items)


@router.get("/reminders", response_model=ApiResponse[UpcomingRemindersResponse])
async def get_upcoming_reminders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upcoming statement and due dates for the signed-in wallet.
    This list is for the app UI. Push delivery uses the same dates, filtered by preferences.
    """
    stmt = (
        select(UserCard)
        .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
        .where(UserCard.user_id == user.id, UserCard.is_active.is_(True))
    )
    user_cards = list((await db.execute(stmt)).scalars().all())
    reminders = build_reminders(user_cards)
    return ApiResponse(data=UpcomingRemindersResponse(reminders=reminders))
