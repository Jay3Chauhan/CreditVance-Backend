import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_workflow(client: AsyncClient):
    unique_email = f"testuser_{uuid.uuid4().hex[:8]}@example.com"
    # 1. Register User
    reg_payload = {
        "email": unique_email,
        "password": "Password123!",
        "full_name": "Test User",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    assert reg_res.json()["success"] is True

    # Duplicate registration should return 409
    dup_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409

    # 2. Login
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()["data"]
    token = token_data["access_token"]
    assert token is not None

    # 3. Get Profile
    me_res = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    user_data = me_res.json()["data"]
    assert user_data["email"] == unique_email
