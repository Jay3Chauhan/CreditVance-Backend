"""Firebase push preferences, test delivery, and same-day reminder dedupe."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.schemas.device_token import CardReminderItem
from app.services.firebase_push_service import PushSendResult, firebase_push_service
from app.services.notification_service import notification_service
from app.services.reminder_service import select_push_reminders


def _item(reminder_type: str, days: int) -> CardReminderItem:
    return CardReminderItem(
        user_card_id=1,
        nickname="Primary",
        card_title="Sample Card",
        bank_name="HDFC",
        due_day=10,
        days_until_due=days if reminder_type == "due_date" else None,
        days_until_statement=days if reminder_type == "statement_date" else None,
        reminder_type=reminder_type,
        message="Pay soon",
    )


def test_push_selection_uses_opt_in_offsets_only():
    reminders = [
        _item("due_date", 0),
        _item("due_date", 3),
        _item("due_date", 12),
        _item("statement_date", 1),
        _item("statement_date", 6),
    ]
    chosen = select_push_reminders(reminders, due_days=[0, 1, 3], statement_days=[0, 1])
    assert [item.days_until_due for item in chosen if item.reminder_type == "due_date"] == [0, 3]
    assert len([item for item in chosen if item.reminder_type == "statement_date"]) == 1


def test_firebase_project_is_configured():
    path = settings.resolved_firebase_credentials_path
    if not path.is_file():
        pytest.skip("Firebase service account is not on this machine.")
    assert firebase_push_service.initialize() is True
    status = firebase_push_service.status()
    assert status["configured"] is True
    assert status["project_id"] == "credvance-cb042"
    assert status["android_channel_id"] == "creditvance_reminders"


@pytest.mark.asyncio
async def test_push_preferences_test_send_and_dedupe(client: AsyncClient, monkeypatch):
    calls: list[dict] = []

    async def fake_send(tokens, title, body, data):
        calls.append({"tokens": list(tokens), "title": title, "data": data})
        return PushSendResult(success_count=len(tokens), failure_count=0)

    monkeypatch.setattr(firebase_push_service, "send_to_tokens", fake_send)

    cards = (await client.get("/api/v1/cards?limit=1")).json()["data"]
    assert cards
    card = cards[0]

    email = f"push_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Push Tester"},
    )
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = (
        await client.get("/api/v1/auth/me", headers=headers)
    ).json()["data"]["id"]

    status_res = await client.get("/api/v1/notifications/status")
    assert status_res.status_code == 200
    assert status_res.json()["data"]["android_channel_id"] == "creditvance_reminders"

    prefs = await client.get("/api/v1/notifications/preferences", headers=headers)
    assert prefs.status_code == 200
    assert prefs.json()["data"]["push_enabled"] is True
    assert prefs.json()["data"]["product_updates"] is False

    updated = await client.patch(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"due_reminder_days": [0], "statement_reminder_days": [], "product_updates": True},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["due_reminder_days"] == [0]
    assert updated.json()["data"]["statement_reminder_days"] == []

    device = f"fcm-test-{uuid.uuid4().hex}"
    registered = await client.post(
        "/api/v1/notifications/device-token",
        headers=headers,
        json={"device_token": device, "platform": "Android"},
    )
    assert registered.status_code == 201
    assert registered.json()["data"]["platform"] == "android"

    today = datetime.now(timezone.utc).day
    added = await client.post(
        "/api/v1/wallet",
        headers=headers,
        json={
            "card_id": card["id"],
            "nickname": "Primary",
            "last_4_digits": "4242",
            "due_day": today,
        },
    )
    assert added.status_code == 201

    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        first = await notification_service.dispatch_for_user(session, user_id)
        second = await notification_service.dispatch_for_user(session, user_id)

    assert first.status == "sent"
    assert first.success_count == 1
    assert second.status == "skipped"
    assert len(calls) == 1
    assert calls[0]["data"]["route"] == "/wallet"
    assert calls[0]["data"]["type"] == "due_date"
    assert calls[0]["tokens"] == [device]

    test_res = await client.post("/api/v1/notifications/test", headers=headers)
    assert test_res.status_code == 200
    assert test_res.json()["data"]["success_count"] == 1
    assert len(calls) == 2

    history = await client.get("/api/v1/notifications/history", headers=headers)
    assert history.status_code == 200
    types = {item["notification_type"] for item in history.json()["data"]}
    assert "due_date" in types
    assert "test" in types

    removed = await client.delete(
        "/api/v1/notifications/device-token",
        headers=headers,
        params={"device_token": device},
    )
    assert removed.status_code == 200

    missing = await client.post("/api/v1/notifications/test", headers=headers)
    assert missing.status_code == 422

    await client.delete("/api/v1/auth/me", headers=headers)
