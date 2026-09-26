"""
Notifications & Due-Date Reminders Router.
Allows mobile device registration (FCM/APNs) and serves statement/due date reminder schedules.
PCI-DSS Safe: Only processes day of month, never card numbers.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.deps import get_current_user, get_db, get_optional_user
from app.models.card import CreditCard
from app.models.device_token import DeviceToken
from app.models.user import User
from app.models.user_card import UserCard
from app.services.billing import days_until_day_of_month
from app.schemas.common import ApiResponse
from app.schemas.device_token import (
    CardReminderItem,
    DeviceTokenRegisterRequest,
    DeviceTokenResponse,
    UpcomingRemindersResponse,
)

router = APIRouter(prefix="/notifications", tags=["Notifications & Reminders"])


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
    Registers or updates an FCM/APNs push device token.
    Works for both authenticated users and anonymous guest devices.
    """
    stmt = select(DeviceToken).where(DeviceToken.token == req.device_token.strip())
    existing = (await db.execute(stmt)).scalar_one_or_none()

    user_id = user.id if user else None

    if existing:
        existing.user_id = user_id
        existing.platform = req.platform.lower()
        target = existing
    else:
        target = DeviceToken(
            user_id=user_id,
            token=req.device_token.strip(),
            platform=req.platform.lower(),
        )
        db.add(target)

    await db.commit()
    await db.refresh(target)

    return ApiResponse(
        message="Device token registered successfully.",
        data=DeviceTokenResponse.model_validate(target),
    )


@router.get("/reminders", response_model=ApiResponse[UpcomingRemindersResponse])
async def get_upcoming_reminders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Computes upcoming billing cycle and payment due-date reminders for user's active cards.
    Only days of the month are processed. Zero card data exposure.
    """
    stmt = (
        select(UserCard)
        .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
        .where(UserCard.user_id == user.id, UserCard.is_active == True)
    )
    user_cards = (await db.execute(stmt)).scalars().all()

    reminders: List[CardReminderItem] = []

    for uc in user_cards:
        c = uc.card
        title = c.display_name if c else (uc.nickname or "Card")
        bank = c.bank.name if c and c.bank else "Bank"

        # Check due day
        if uc.due_day:
            diff_due = days_until_day_of_month(uc.due_day)
            if diff_due == 0:
                msg = f"Payment for {uc.nickname or title} is due today!"
            elif diff_due <= 5:
                msg = f"Payment for {uc.nickname or title} is due in {diff_due} days (Day {uc.due_day})."
            else:
                msg = f"Upcoming bill due on Day {uc.due_day} of each month."

            reminders.append(
                CardReminderItem(
                    user_card_id=uc.id,
                    nickname=uc.nickname or title,
                    card_title=c.title if c else title,
                    bank_name=bank,
                    statement_day=uc.statement_day or uc.billing_cycle_day,
                    due_day=uc.due_day,
                    days_until_due=diff_due,
                    reminder_type="due_date",
                    message=msg,
                )
            )

        # Check statement day
        stmt_day = uc.statement_day or uc.billing_cycle_day
        if stmt_day:
            diff_stmt = days_until_day_of_month(stmt_day)
            if diff_stmt == 0:
                msg = f"Statement for {uc.nickname or title} generates today!"
            elif diff_stmt <= 3:
                msg = f"Statement for {uc.nickname or title} generates in {diff_stmt} days."
            else:
                msg = f"Statement generates on Day {stmt_day} of each month."

            reminders.append(
                CardReminderItem(
                    user_card_id=uc.id,
                    nickname=uc.nickname or title,
                    card_title=c.title if c else title,
                    bank_name=bank,
                    statement_day=stmt_day,
                    due_day=uc.due_day,
                    days_until_statement=diff_stmt,
                    reminder_type="statement_date",
                    message=msg,
                )
            )

    # Sort reminders with closest due/statement days first
    reminders.sort(key=lambda r: min(r.days_until_due or 99, r.days_until_statement or 99))

    return ApiResponse(
        data=UpcomingRemindersResponse(reminders=reminders)
    )
