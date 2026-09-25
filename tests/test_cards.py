import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cards_catalog_and_filtering(client: AsyncClient):
    # 1. List cards
    res = await client.get("/api/v1/cards?limit=10")
    assert res.status_code == 200
    data = response_json = res.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1
    assert data["meta"]["total"] >= 1

    # 2. Filter by bank
    bank_res = await client.get("/api/v1/cards?bank_slug=hdfc")
    assert bank_res.status_code == 200
    for card in bank_res.json()["data"]:
        assert card["bank_slug"] == "hdfc"

    # 3. Card Detail by Slug
    card_res = await client.get("/api/v1/cards/hdfc-infinia-metal")
    assert card_res.status_code == 200
    card_data = card_res.json()["data"]
    assert card_data["slug"] == "hdfc-infinia-metal"
    assert card_data["joining_fee"] == 12500.0

    # 4. Card Tab Detail
    tab_res = await client.get("/api/v1/cards/hdfc-infinia-metal/tabs/earn-categories")
    assert tab_res.status_code == 200
    tab_data = tab_res.json()["data"]
    assert tab_data["tab_name"] == "earn-categories"
    assert "tabData" in tab_data["content"]
