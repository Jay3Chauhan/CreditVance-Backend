import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reward_calculator(client: AsyncClient):
    # 1. Fetch Rubyx card details by slug
    card_res = await client.get("/api/v1/cards/icici-rubyx-mastercard")
    rubyx = card_res.json()["data"]

    # 2. Calculate ₹5,000 spend on Grocery
    calc_res = await client.post(
        "/api/v1/calculator/calculate",
        json={
            "card_id": rubyx["id"],
            "category_slug": "Grocery",
            "spendAmount": 5000.0,
        },
    )
    assert calc_res.status_code == 200
    calc_data = calc_res.json()["data"]
    assert calc_data["user_card"]["card_id"] == rubyx["id"]
    assert calc_data["user_card"]["reward_points"] > 0
    assert calc_data["user_card"]["reward_worth"] > 0
    assert "annual_savings" in calc_data
