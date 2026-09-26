"""Home feed, banners, promotions, compare, search, shortlist, and wallet insights."""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.billing import days_until_day_of_month


def test_due_day_uses_real_calendar():
    assert days_until_day_of_month(26, today=date(2026, 9, 26)) == 0
    assert days_until_day_of_month(1, today=date(2026, 9, 26)) == 5
    # 31st in February lands on the 28th, not a fake 30-day cycle.
    assert days_until_day_of_month(31, today=date(2026, 2, 1)) == 27


@pytest.mark.asyncio
async def test_content_platform(client: AsyncClient):
    cards_res = await client.get("/api/v1/cards?limit=2")
    assert cards_res.status_code == 200
    sample = cards_res.json()["data"]
    assert len(sample) >= 2
    first, second = sample[0], sample[1]

    # Search combined with a bank filter must not 500 (it used to join banks twice).
    both_res = await client.get(
        "/api/v1/cards",
        params={"search": first["title"][:4], "bank_slug": first["bank_slug"], "limit": 5},
    )
    assert both_res.status_code == 200

    home_res = await client.get("/api/v1/home")
    assert home_res.status_code == 200
    home = home_res.json()["data"]
    assert len(home["hero_banners"]) >= 1
    assert home["hero_banners"][0]["action"]["type"] == "screen"
    assert len(home["featured_promotions"]) >= 1
    assert len(home["quick_actions"]) == 4
    assert "collections" in home
    hero_audiences = {banner["audience"] for banner in home["hero_banners"]}
    assert "member" not in hero_audiences

    banners_res = await client.get("/api/v1/banners", params={"placement": "home_hero"})
    assert banners_res.status_code == 200
    hero = banners_res.json()["data"]
    assert hero[0]["placement"] == "home_hero"
    track_res = await client.post(
        f"/api/v1/banners/{hero[0]['id']}/track",
        json={"event": "click"},
    )
    assert track_res.status_code == 200
    assert track_res.json()["data"]["click_count"] >= 1

    promos_res = await client.get("/api/v1/promotions", params={"featured": True})
    assert promos_res.status_code == 200
    promo = promos_res.json()["data"][0]
    detail_res = await client.get(f"/api/v1/promotions/{promo['slug']}")
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["summary"]

    compare_res = await client.post(
        "/api/v1/cards/compare",
        json={"slugs": [first["slug"], second["slug"], first["slug"]]},
    )
    assert compare_res.status_code == 200
    compared = compare_res.json()["data"]
    assert len(compared["cards"]) == 2
    assert len(compared["rows"]) >= 5
    assert compared["rows"][0]["values"][first["slug"]] == first["joining_fee"]
    assert len(compared["category_rates"]) == 6

    missing_res = await client.post(
        "/api/v1/cards/compare",
        json={"slugs": [first["slug"], "not-a-real-card-slug"]},
    )
    assert missing_res.status_code == 404
    assert isinstance(missing_res.json()["detail"], str)

    suggest_res = await client.get(
        "/api/v1/search/suggest",
        params={"q": first["display_name"][:3]},
    )
    assert suggest_res.status_code == 200
    assert any(item["slug"] == first["slug"] for item in suggest_res.json()["data"])

    faq_res = await client.get("/api/v1/meta/faq")
    assert faq_res.status_code == 200
    assert len(faq_res.json()["data"]["items"]) >= 5

    config_res = await client.get("/api/v1/meta/config")
    flags = config_res.json()["data"]["feature_flags"]
    assert flags["home_feed"] is True
    assert flags["card_compare"] is True

    # Admin content: expired banners stay out of the public list.
    admin_headers = {"X-Admin-API-Key": settings.ADMIN_API_KEY}
    denied = await client.get("/api/v1/admin/content/banners")
    assert denied.status_code == 403

    expired_slug = f"expired-{uuid.uuid4().hex[:8]}"
    create_res = await client.post(
        "/api/v1/admin/content/banners",
        headers=admin_headers,
        json={
            "slug": expired_slug,
            "title": "Ended offer",
            "placement": "card_detail",
            "action_type": "none",
            "is_active": True,
            "audience": "all",
            "priority": 1,
            "ends_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        },
    )
    assert create_res.status_code == 201
    created_id = create_res.json()["data"]["id"]

    public_detail = await client.get("/api/v1/banners", params={"placement": "card_detail"})
    assert all(item["id"] != created_id for item in public_detail.json()["data"])

    admin_list = await client.get("/api/v1/admin/content/banners", headers=admin_headers)
    assert any(item["id"] == created_id for item in admin_list.json()["data"])

    linked = await client.post(
        "/api/v1/admin/content/promotions",
        headers=admin_headers,
        json={
            "slug": f"card-offer-{uuid.uuid4().hex[:8]}",
            "title": "Editor note for this card",
            "summary": "Shown on the card detail screen because it is linked to the card.",
            "promo_type": "editorial",
            "card_id": first["id"],
            "action_type": "card",
            "action_target": first["slug"],
            "is_featured": False,
            "is_active": True,
        },
    )
    assert linked.status_code == 201
    linked_id = linked.json()["data"]["id"]
    linked_slug = linked.json()["data"]["slug"]
    by_card = await client.get("/api/v1/promotions", params={"card_slug": first["slug"]})
    assert by_card.status_code == 200
    assert any(item["slug"] == linked_slug for item in by_card.json()["data"])

    # Auth flows: shortlist and insights.
    email = f"content_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Content Tester"},
    )
    assert reg.status_code == 201
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}

    save_res = await client.post(
        "/api/v1/saved-cards",
        headers=headers,
        json={"card_id": first["id"]},
    )
    assert save_res.status_code == 201
    again = await client.post(
        "/api/v1/saved-cards",
        headers=headers,
        json={"card_id": first["id"]},
    )
    assert again.status_code == 201
    listed = await client.get("/api/v1/saved-cards", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["card"]["slug"] == first["slug"]

    wallet = await client.post(
        "/api/v1/wallet",
        headers=headers,
        json={
            "card_id": first["id"],
            "nickname": "Primary",
            "last_4_digits": "4242",
            "statement_day": 5,
            "due_day": 25,
        },
    )
    assert wallet.status_code == 201

    insights = await client.get("/api/v1/wallet/insights", headers=headers)
    assert insights.status_code == 200
    insight_data = insights.json()["data"]
    assert insight_data["card_count"] == 1
    assert insight_data["next_due"]["due_day"] == 25
    assert insight_data["next_due"]["bank_name"] == first["bank_name"]
    assert len(insight_data["category_picks"]) == 6

    reminders = await client.get("/api/v1/notifications/reminders", headers=headers)
    assert reminders.status_code == 200
    due_rows = [row for row in reminders.json()["data"]["reminders"] if row["reminder_type"] == "due_date"]
    assert due_rows
    assert due_rows[0]["bank_name"] == first["bank_name"]
    assert due_rows[0]["days_until_due"] >= 0

    member_home = await client.get("/api/v1/home", headers=headers)
    assert member_home.status_code == 200

    removed = await client.delete(f"/api/v1/saved-cards/{first['id']}", headers=headers)
    assert removed.status_code == 200
    after = await client.get("/api/v1/saved-cards", headers=headers)
    assert after.json()["data"] == []

    await client.delete(f"/api/v1/admin/content/banners/{created_id}", headers=admin_headers)
    await client.delete(f"/api/v1/admin/content/promotions/{linked_id}", headers=admin_headers)
    await client.delete("/api/v1/auth/me", headers=headers)
