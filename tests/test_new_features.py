import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_all_new_backend_features(client: AsyncClient):
    unique_email = f"feat_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"

    # =========================================================================
    # 1. AUTH FEATURES: Register, Login, Refresh, Patch Name, Reset, Delete
    # =========================================================================
    # 1.1 Register
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": password, "full_name": "Original Name"},
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["data"]["id"]

    # 1.2 Login with refresh_token
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()["data"]
    access_token = login_data["access_token"]
    refresh_token = login_data["refresh_token"]
    assert access_token is not None
    assert refresh_token is not None
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1.3 Refresh token
    refresh_res = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    refreshed_data = refresh_res.json()["data"]
    assert refreshed_data["access_token"] is not None
    new_headers = {"Authorization": f"Bearer {refreshed_data['access_token']}"}

    # 1.4 PATCH /auth/me for full_name
    patch_res = await client.patch(
        "/api/v1/auth/me",
        headers=new_headers,
        json={"full_name": "Updated Full Name"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["full_name"] == "Updated Full Name"

    # 1.5 Password Forgot & Reset
    forgot_res = await client.post(
        "/api/v1/auth/password/forgot",
        json={"email": unique_email},
    )
    assert forgot_res.status_code == 200
    reset_token = forgot_res.json()["data"]["reset_token"]
    assert reset_token is not None

    reset_res = await client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "new_password": "NewSecurePassword456!"},
    )
    assert reset_res.status_code == 200

    # Verify login with new password
    new_login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "NewSecurePassword456!"},
    )
    assert new_login_res.status_code == 200
    auth_headers = {"Authorization": f"Bearer {new_login_res.json()['data']['access_token']}"}

    # =========================================================================
    # 2. ADVISOR: is_international & forex_markup_applied
    # =========================================================================
    # Non-international spend
    dom_res = await client.post(
        "/api/v1/advisor/recommend",
        headers=auth_headers,
        json={"category_slug": "Dining", "spend_amount": 10000.0, "is_international": False},
    )
    assert dom_res.status_code == 200
    benchmark_dom = dom_res.json()["data"]["market_benchmark_card"]
    assert benchmark_dom["forex_markup_applied"] == 0.0

    # International spend: forex_markup_applied must be populated and > 0 if card has markup
    intl_res = await client.post(
        "/api/v1/advisor/recommend",
        headers=auth_headers,
        json={"category_slug": "Dining", "spend_amount": 10000.0, "is_international": True},
    )
    assert intl_res.status_code == 200
    benchmark_intl = intl_res.json()["data"]["market_benchmark_card"]
    assert "forex_markup_applied" in benchmark_intl
    assert benchmark_intl["forex_markup_applied"] >= 0.0

    # =========================================================================
    # 3. ADVISOR: Guest mode with explicit card_ids
    # =========================================================================
    cards_list_res = await client.get("/api/v1/cards?limit=3")
    sample_cards = cards_list_res.json()["data"]
    c_ids = [c["id"] for c in sample_cards[:2]]

    # Guest call without auth header but with card_ids
    guest_rec_res = await client.post(
        "/api/v1/advisor/recommend",
        json={"category_slug": "Dining", "spend_amount": 5000.0, "card_ids": c_ids},
    )
    assert guest_rec_res.status_code == 200
    guest_data = guest_rec_res.json()["data"]
    # Both top_recommendation and alternative_cards must be populated!
    assert guest_data["top_recommendation"] is not None
    assert guest_data["top_recommendation"]["card_id"] in c_ids
    assert len(guest_data["alternative_cards"]) >= 1

    # =========================================================================
    # 4. CARD DETAIL & TABS: Enriched fields & non-404 tabs
    # =========================================================================
    first_slug = sample_cards[0]["slug"]
    card_detail_res = await client.get(f"/api/v1/cards/{first_slug}")
    assert card_detail_res.status_code == 200
    detail = card_detail_res.json()["data"]
    # Check fields are populated
    assert detail["card_image_url"] is not None
    assert detail["overview_text"] is not None
    assert detail["apply_link"] is not None
    assert len(detail["available_tabs"]) >= 3
    assert "fee_waiver_spend" in detail
    assert "point_value_inr" in detail
    assert len(detail["per_category_earn_rates"]) >= 10

    # Tab endpoint must return 200 and not 404
    tab_res = await client.get(f"/api/v1/cards/{first_slug}/tabs/earn-categories")
    assert tab_res.status_code == 200
    assert "content" in tab_res.json()["data"]

    # =========================================================================
    # 5. ANNUAL REWARD CALCULATOR
    # =========================================================================
    calc_annual_res = await client.post(
        "/api/v1/calculator/annual",
        json={
            "card_id": sample_cards[0]["id"],
            "monthly_spend": {
                "Dining": 5000.0,
                "Grocery": 8000.0,
                "Online Shopping": 10000.0,
            },
        },
    )
    assert calc_annual_res.status_code == 200
    calc_data = calc_annual_res.json()["data"]
    assert calc_data["annual_spend"] == (5000 + 8000 + 10000) * 12.0
    assert calc_data["total_annual_reward_inr"] > 0
    assert "fee_waived" in calc_data
    assert "net_annual_value_inr" in calc_data
    assert len(calc_data["category_breakdown"]) == 3

    # =========================================================================
    # 6. WALLET: sort_order, statement_day, due_day, updated_at, PUT /wallet/order
    # =========================================================================
    # Add 2 cards to wallet with statement_day and due_day
    w1_res = await client.post(
        "/api/v1/wallet",
        headers=auth_headers,
        json={
            "card_id": sample_cards[0]["id"],
            "nickname": "Wallet Card 1",
            "last_4_digits": "1234",
            "statement_day": 15,
            "due_day": 5,
        },
    )
    assert w1_res.status_code == 201
    w1_data = w1_res.json()["data"]
    assert w1_data["statement_day"] == 15
    assert w1_data["due_day"] == 5
    assert "updated_at" in w1_data

    w2_res = await client.post(
        "/api/v1/wallet",
        headers=auth_headers,
        json={
            "card_id": sample_cards[1]["id"],
            "nickname": "Wallet Card 2",
            "last_4_digits": "5678",
            "statement_day": 20,
            "due_day": 10,
        },
    )
    assert w2_res.status_code == 201
    w2_data = w2_res.json()["data"]

    # Reorder cards via PUT /wallet/order
    reorder_res = await client.put(
        "/api/v1/wallet/order",
        headers=auth_headers,
        json={"ids": [w2_data["id"], w1_data["id"]]},
    )
    assert reorder_res.status_code == 200
    ordered_cards = reorder_res.json()["data"]
    assert ordered_cards[0]["id"] == w2_data["id"]
    assert ordered_cards[0]["sort_order"] == 0
    assert ordered_cards[1]["id"] == w1_data["id"]
    assert ordered_cards[1]["sort_order"] == 1

    # =========================================================================
    # 7. CATALOG: Lounge filters, sorts, applied_filters in meta
    # =========================================================================
    catalog_res = await client.get("/api/v1/cards?has_lounge=true&sort_by=annual_fee_asc&limit=5")
    assert catalog_res.status_code == 200
    cat_meta = catalog_res.json()["meta"]
    assert cat_meta["applied_filters"]["has_lounge"] is True
    assert cat_meta["applied_filters"]["sort_by"] == "annual_fee_asc"
    assert cat_meta["total"] >= 1

    # =========================================================================
    # 8. NOTIFICATIONS & REMINDERS
    # =========================================================================
    tok_res = await client.post(
        "/api/v1/notifications/device-token",
        headers=auth_headers,
        json={"device_token": "fcm_sample_token_xyz_1234567890", "platform": "android"},
    )
    assert tok_res.status_code == 201

    remind_res = await client.get(
        "/api/v1/notifications/reminders",
        headers=auth_headers,
    )
    assert remind_res.status_code == 200
    reminders = remind_res.json()["data"]["reminders"]
    assert len(reminders) >= 1

    # =========================================================================
    # 9. META & LEGAL & CATEGORIES
    # =========================================================================
    legal_res = await client.get("/api/v1/meta/legal")
    assert legal_res.status_code == 200
    assert "privacy_policy_url" in legal_res.json()["data"]

    config_res = await client.get("/api/v1/meta/config")
    assert config_res.status_code == 200
    assert "curated_category_order" in config_res.json()["data"]

    cats_res = await client.get("/api/v1/categories")
    assert cats_res.status_code == 200
    cats = cats_res.json()["data"]
    assert len(cats) >= 1
    assert "icon_key" in cats[0]
    assert "display_order" in cats[0]

    # =========================================================================
    # 10. ERROR SHAPE: Flattened string "detail"
    # =========================================================================
    err_res = await client.post("/api/v1/auth/login", json={"email": "bad_email"})
    assert err_res.status_code == 422
    err_json = err_res.json()
    assert "detail" in err_json
    assert isinstance(err_json["detail"], str)

    # Clean up: Delete account
    del_res = await client.delete("/api/v1/auth/me", headers=auth_headers)
    assert del_res.status_code == 200
