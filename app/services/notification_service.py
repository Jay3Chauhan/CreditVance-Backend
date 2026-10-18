"""
Push preferences, test sends, inbox history, and the daily reminder job.
A reminder is recorded before it is sent so two workers cannot deliver it twice.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.models.card import CreditCard
from app.models.device_token import DeviceToken
from app.models.notification_log import NotificationLog
from app.models.notification_preference import NotificationPreference
from app.models.user_card import UserCard
from app.schemas.notification import (
    NotificationHistoryItem,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    PushDispatchResponse,
)
from app.services.firebase_push_service import firebase_push_service
from app.services.reminder_service import (
    DEFAULT_DUE_REMINDER_DAYS,
    DEFAULT_STATEMENT_REMINDER_DAYS,
    build_reminders,
    push_data,
    push_title,
    select_push_reminders,
)


class NotificationService:
    def _prefs_response(self, row: NotificationPreference | None) -> NotificationPreferencesResponse:
        if row is None:
            return NotificationPreferencesResponse(
                push_enabled=True,
                due_reminder_days=list(DEFAULT_DUE_REMINDER_DAYS),
                statement_reminder_days=list(DEFAULT_STATEMENT_REMINDER_DAYS),
                product_updates=False,
            )
        return NotificationPreferencesResponse(
            push_enabled=row.push_enabled,
            due_reminder_days=list(DEFAULT_DUE_REMINDER_DAYS)
            if row.due_reminder_days is None
            else list(row.due_reminder_days),
            statement_reminder_days=list(DEFAULT_STATEMENT_REMINDER_DAYS)
            if row.statement_reminder_days is None
            else list(row.statement_reminder_days),
            product_updates=row.product_updates,
        )

    async def get_preferences(self, db: AsyncSession, user_id: int) -> NotificationPreferencesResponse:
        row = await db.get(NotificationPreference, user_id)
        return self._prefs_response(row)

    async def update_preferences(
        self, db: AsyncSession, user_id: int, req: NotificationPreferencesUpdate
    ) -> NotificationPreferencesResponse:
        row = await db.get(NotificationPreference, user_id)
        if row is None:
            current = self._prefs_response(None)
            row = NotificationPreference(
                user_id=user_id,
                push_enabled=current.push_enabled,
                due_reminder_days=current.due_reminder_days,
                statement_reminder_days=current.statement_reminder_days,
                product_updates=current.product_updates,
            )
            db.add(row)
        changes = req.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return self._prefs_response(row)

    async def list_history(self, db: AsyncSession, user_id: int, limit: int) -> list[NotificationHistoryItem]:
        stmt = (
            select(NotificationLog)
            .where(NotificationLog.user_id == user_id)
            .order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        items: list[NotificationHistoryItem] = []
        for row in rows:
            data = row.data or {}
            items.append(
                NotificationHistoryItem(
                    id=row.id,
                    notification_type=row.notification_type,
                    title=row.title,
                    body=row.body,
                    route=data.get("route"),
                    status=row.status,
                    created_at=row.created_at,
                )
            )
        return items

    async def send_test_push(self, db: AsyncSession, user_id: int) -> PushDispatchResponse:
        tokens = await self._tokens_for_user(db, user_id)
        if not tokens:
            raise ValidationError(
                "Register this phone with POST /notifications/device-token before sending a test."
            )
        title = "CreditVance notifications are on"
        body = "This is a test from your account. Payment reminders will arrive on this device."
        data = {"type": "test", "route": "/wallet"}
        dedupe_key = f"test:{uuid.uuid4().hex}"
        return await self._deliver(
            db,
            user_id=user_id,
            dedupe_key=dedupe_key,
            notification_type="test",
            title=title,
            body=body,
            data=data,
            token_rows=tokens,
        )

    async def send_to_user(
        self,
        db: AsyncSession,
        user_id: int,
        title: str,
        body: str,
        route: str,
        notification_type: str,
    ) -> PushDispatchResponse:
        tokens = await self._tokens_for_user(db, user_id)
        if not tokens:
            raise NotFoundError("That account has no registered devices.")
        return await self._deliver(
            db,
            user_id=user_id,
            dedupe_key=f"admin:{uuid.uuid4().hex}",
            notification_type=notification_type,
            title=title,
            body=body,
            data={"type": notification_type, "route": route},
            token_rows=tokens,
        )

    async def broadcast_product_update(
        self, db: AsyncSession, title: str, body: str, route: str
    ) -> PushDispatchResponse:
        """Sends only to accounts that turned product updates on."""
        stmt = select(NotificationPreference.user_id).where(
            NotificationPreference.push_enabled.is_(True),
            NotificationPreference.product_updates.is_(True),
        )
        user_ids = list((await db.execute(stmt)).scalars().all())
        total = PushDispatchResponse(targeted_devices=0, success_count=0, failure_count=0, status="sent")
        for user_id in user_ids:
            tokens = await self._tokens_for_user(db, user_id)
            if not tokens:
                continue
            piece = await self._deliver(
                db,
                user_id=user_id,
                dedupe_key=f"product:{datetime.now(timezone.utc).date().isoformat()}:{uuid.uuid4().hex[:8]}",
                notification_type="product",
                title=title,
                body=body,
                data={"type": "product", "route": route},
                token_rows=tokens,
            )
            total.targeted_devices += piece.targeted_devices
            total.success_count += piece.success_count
            total.failure_count += piece.failure_count
            total.invalid_tokens_removed += piece.invalid_tokens_removed
        if total.targeted_devices == 0:
            total.status = "skipped"
        elif total.failure_count and not total.success_count:
            total.status = "failed"
        elif total.failure_count:
            total.status = "partial"
        return total

    async def dispatch_for_user(self, db: AsyncSession, user_id: int) -> PushDispatchResponse:
        """Send today's due and statement pushes for one account."""
        prefs = await self.get_preferences(db, user_id)
        summary = PushDispatchResponse(targeted_devices=0, success_count=0, failure_count=0, status="skipped")
        if not prefs.push_enabled:
            return summary

        cards = await self._active_cards(db, user_id)
        if not cards:
            return summary
        reminders = select_push_reminders(
            build_reminders(cards),
            prefs.due_reminder_days,
            prefs.statement_reminder_days,
        )
        if not reminders:
            return summary

        tokens = await self._tokens_for_user(db, user_id)
        if not tokens:
            return summary

        today = datetime.now(timezone.utc).date().isoformat()
        for item in reminders:
            piece = await self._deliver(
                db,
                user_id=user_id,
                dedupe_key=f"{item.reminder_type}:{item.user_card_id}:{today}",
                notification_type=item.reminder_type,
                title=push_title(item),
                body=item.message,
                data=push_data(item),
                token_rows=tokens,
            )
            if piece.status == "skipped":
                continue
            summary.targeted_devices += piece.targeted_devices
            summary.success_count += piece.success_count
            summary.failure_count += piece.failure_count
            summary.invalid_tokens_removed += piece.invalid_tokens_removed
            summary.status = piece.status
        return summary

    async def dispatch_scheduled_pushes(self, db: AsyncSession) -> dict[str, int]:
        stmt = select(UserCard.user_id).where(UserCard.is_active.is_(True)).distinct()
        user_ids = list((await db.execute(stmt)).scalars().all())
        sent_users = 0
        skipped_users = 0
        for user_id in user_ids:
            result = await self.dispatch_for_user(db, user_id)
            if result.success_count or result.failure_count:
                sent_users += 1
            else:
                skipped_users += 1
        return {"users_considered": len(user_ids), "users_notified": sent_users, "users_skipped": skipped_users}

    async def _active_cards(self, db: AsyncSession, user_id: int) -> list[UserCard]:
        stmt = (
            select(UserCard)
            .options(selectinload(UserCard.card).selectinload(CreditCard.bank))
            .where(UserCard.user_id == user_id, UserCard.is_active.is_(True))
        )
        return list((await db.execute(stmt)).scalars().all())

    async def _tokens_for_user(self, db: AsyncSession, user_id: int) -> list[DeviceToken]:
        stmt = select(DeviceToken).where(DeviceToken.user_id == user_id)
        return list((await db.execute(stmt)).scalars().all())

    async def _deliver(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        dedupe_key: str,
        notification_type: str,
        title: str,
        body: str,
        data: dict[str, str],
        token_rows: list[DeviceToken],
    ) -> PushDispatchResponse:
        existing = (
            await db.execute(
                select(NotificationLog).where(
                    NotificationLog.user_id == user_id,
                    NotificationLog.dedupe_key == dedupe_key,
                )
            )
        ).scalar_one_or_none()
        if existing and existing.status in {"sent", "partial"}:
            return PushDispatchResponse(
                targeted_devices=0,
                success_count=0,
                failure_count=0,
                status="skipped",
            )

        log = existing
        if log is None:
            log = NotificationLog(
                user_id=user_id,
                dedupe_key=dedupe_key,
                notification_type=notification_type,
                title=title[:180],
                body=body[:500],
                data=data,
                status="pending",
            )
            try:
                async with db.begin_nested():
                    db.add(log)
                    await db.flush()
            except IntegrityError:
                return PushDispatchResponse(
                    targeted_devices=0,
                    success_count=0,
                    failure_count=0,
                    status="skipped",
                )

        token_values = [row.token for row in token_rows]
        send_result = await firebase_push_service.send_to_tokens(token_values, title, body, data)
        if send_result.invalid_tokens:
            stale = set(send_result.invalid_tokens)
            for row in token_rows:
                if row.token in stale:
                    await db.delete(row)

        if send_result.error and send_result.success_count == 0:
            log.status = "failed"
        elif send_result.failure_count and send_result.success_count:
            log.status = "partial"
        elif send_result.success_count:
            log.status = "sent"
        else:
            log.status = "failed"
        log.success_count = send_result.success_count
        log.failure_count = send_result.failure_count
        log.error_message = send_result.error
        log.title = title[:180]
        log.body = body[:500]
        await db.commit()

        status = log.status
        return PushDispatchResponse(
            targeted_devices=len(token_values),
            success_count=send_result.success_count,
            failure_count=send_result.failure_count,
            invalid_tokens_removed=len(send_result.invalid_tokens),
            status=status,
        )


notification_service = NotificationService()
