import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_smart_advisor_recommendation(client: AsyncClient):
    unique_email = f"advisor_{uuid.uuid4().hex[:8]}@example.com"
    # 1. Register and Login user
    await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": "Password123!", "full_name": "Advisor Tester"},
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "Password123!"},
    )
    token = login_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Get card details for Infinia and Rubyx
    infinia_res = await client.get("/api/v1/cards/hdfc-infinia-metal")
    infinia = infinia_res.json()["data"]
    rubyx_res = await client.get("/api/v1/cards/icici-rubyx-mastercard")
    rubyx = rubyx_res.json()["data"]

    # 3. Add Infinia and Rubyx to User's Wallet
    await client.post(
        "/api/v1/user-cards",
        headers=headers,
        json={"card_id": infinia["id"], "nickname": "My Infinia", "last_4_digits": "1111"},
    )
    await client.post(
        "/api/v1/user-cards",
        headers=headers,
        json={"card_id": rubyx["id"], "nickname": "My Rubyx", "last_4_digits": "2222"},
    )

    # 4. Ask Advisor: "I am spending ₹10,000 on Dining. Which card should I use?"
    advisor_res = await client.post(
        "/api/v1/advisor/recommend",
        headers=headers,
        json={"category_slug": "Dining", "spend_amount": 10000.0},
    )
    assert advisor_res.status_code == 200
    rec_data = advisor_res.json()["data"]
    assert rec_data["top_recommendation"] is not None
    # Infinia should be top recommended for Dining (highest return)
    assert rec_data["top_recommendation"]["card_slug"] == "hdfc-infinia-metal"
    assert rec_data["top_recommendation"]["estimated_reward_value_inr"] > 0
    assert len(rec_data["alternative_cards"]) >= 1

    # 5. Check Exclusion: "I am spending ₹20,000 on Rent"
    rent_res = await client.post(
        "/api/v1/advisor/recommend",
        headers=headers,
        json={"category_slug": "Rent", "spend_amount": 20000.0},
    )
    assert rent_res.status_code == 200
    rent_data = rent_res.json()["data"]
    # Rent is excluded on both cards so return should be 0
    assert rent_data["top_recommendation"]["estimated_reward_value_inr"] == 0.0
