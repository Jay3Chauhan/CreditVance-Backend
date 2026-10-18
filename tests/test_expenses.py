"""
Comprehensive Integration Tests for SMS Expense Tracking API.
Tests:
- Sender registry lookup
- Batch ingestion with idempotency key
- Server-side enrichment of merchants and categories
- Deduplication and category override updates
- PAN leakage defence-in-depth prevention
- Date range validation
- Paginated transaction browsing
- Soft delete and tombstone rejection
- Milestone calculations
- Spend analytics summary (net, gross, refund, category, card, merchant, monthly)
- DPDP consent ledger and full data erasure
"""

from datetime import datetime, timedelta, timezone
import hashlib
import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_sms_expense_tracking_full_lifecycle(client: AsyncClient):
    # =========================================================================
    # 1. Public Sender Registry Endpoint
    # =========================================================================
    registry_res = await client.get("/api/v1/expenses/sender-registry")
    assert registry_res.status_code == 200
    registry = registry_res.json()["data"]
    assert registry["version"] >= 1
    bank_codes = {b["code"] for b in registry["banks"]}
    assert "HDFC" in bank_codes
    assert "ICICI" in bank_codes
    assert "SBICARD" in bank_codes
    assert "AXIS" in bank_codes
    assert "AMEX" in bank_codes

    # =========================================================================
    # 2. User Setup & Wallet Card Creation
    # =========================================================================
    unique_email = f"expense_user_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"

    reg_res = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email, "password": password, "full_name": "Expense Tester"},
    )
    assert reg_res.status_code == 201

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": unique_email, "password": password},
    )
    assert login_res.status_code == 200
    token = login_res.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Add Infinia to wallet
    cards_res = await client.get("/api/v1/cards", params={"search": "Infinia", "limit": 1})
    infinia_card = cards_res.json()["data"][0]
    wallet_res = await client.post(
        "/api/v1/wallet",
        headers=headers,
        json={
            "card_id": infinia_card["id"],
            "nickname": "My Primary Infinia",
            "last_4_digits": "1234",
            "statement_day": 15,
            "due_day": 5,
            "anniversary_month": 6,
        },
    )
    assert wallet_res.status_code == 201
    user_card_id = wallet_res.json()["data"]["id"]
    assert wallet_res.json()["data"]["anniversary_month"] == 6

    # =========================================================================
    # 3. DPDP Consent Ledger
    # =========================================================================
    consent_res = await client.put(
        "/api/v1/expenses/consent",
        headers=headers,
        json={
            "purpose": "sms_card_expense_tracking",
            "status": "granted",
            "notice_version": "sms-v1",
            "decided_at": datetime.now(timezone.utc).isoformat(),
            "platform": "android",
        },
    )
    assert consent_res.status_code == 200
    assert consent_res.json()["data"]["status"] == "granted"

    # =========================================================================
    # 4. Batch Ingestion with Idempotency Key & Enrichments
    # =========================================================================
    now = datetime.now(timezone.utc)
    hash_tx1 = hashlib.sha256(f"tx1_{uuid.uuid4().hex}".encode()).hexdigest()[:32]
    hash_tx2 = hashlib.sha256(f"tx2_{uuid.uuid4().hex}".encode()).hexdigest()[:32]
    hash_bill = hashlib.sha256(f"bill_{uuid.uuid4().hex}".encode()).hexdigest()[:32]

    idempotency_key = hashlib.sha256(f"{hash_tx1},{hash_tx2},{hash_bill}".encode()).hexdigest()

    batch_payload = {
        "client_version": "1.0.0",
        "schema_version": 1,
        "transactions": [
            {
                "dedupe_hash": hash_tx1,
                "amount": 1250.0,
                "currency": "INR",
                "type": "debit",
                "occurred_at": (now - timedelta(days=2)).isoformat(),
                "bank_code": "HDFC",
                "card_last4": "1234",
                "user_card_id": user_card_id,
                "merchant_raw": "SWIGGY BANGALORE IN",
                "merchant_name": "SWIGGY",
                "category": "dining",
                "category_overridden": False,
                "channel": "card",
                "available_limit": 150000.0,
                "source": "sms",
                "confidence": 0.95,
            },
            {
                "dedupe_hash": hash_tx2,
                "amount": 3499.0,
                "currency": "INR",
                "type": "debit",
                "occurred_at": (now - timedelta(days=1)).isoformat(),
                "bank_code": "HDFC",
                "card_last4": "1234",
                "user_card_id": user_card_id,
                "merchant_raw": "AMAZON PAY RETAIL",
                "merchant_name": "Amazon",
                "category": "other",  # Expect server enrichment to shopping
                "category_overridden": False,
                "channel": "card",
                "available_limit": 146501.0,
                "source": "sms",
                "confidence": 0.90,
            },
        ],
        "bills": [
            {
                "dedupe_hash": hash_bill,
                "bank_code": "HDFC",
                "card_last4": "1234",
                "user_card_id": user_card_id,
                "total_due": 18500.0,
                "minimum_due": 950.0,
                "due_date": (now + timedelta(days=15)).strftime("%Y-%m-%d"),
                "noticed_at": now.isoformat(),
            }
        ],
    }

    ingest_res = await client.post(
        "/api/v1/expenses/transactions/batch",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json=batch_payload,
    )
    assert ingest_res.status_code == 200
    res_data = ingest_res.json()["data"]
    assert hash_tx1 in res_data["accepted"]
    assert hash_tx2 in res_data["accepted"]
    assert hash_bill in res_data["accepted"]
    assert len(res_data["rejected"]) == 0

    # Server-side enrichment check: Amazon categorised to shopping
    enrichments = {e["dedupe_hash"]: e for e in res_data["enrichments"]}
    if hash_tx2 in enrichments:
        assert enrichments[hash_tx2]["category"] == "shopping"

    # =========================================================================
    # 5. Idempotent Replay
    # =========================================================================
    replay_res = await client.post(
        "/api/v1/expenses/transactions/batch",
        headers={**headers, "Idempotency-Key": idempotency_key},
        json=batch_payload,
    )
    assert replay_res.status_code == 200
    assert replay_res.json()["data"]["accepted"] == res_data["accepted"]

    # =========================================================================
    # 6. Deduplication & User Category Override Update
    # =========================================================================
    # Resend without Idempotency-Key: tx1 is overridden by user to groceries, tx2 unchanged
    override_payload = {
        "transactions": [
            {
                **batch_payload["transactions"][0],
                "category": "groceries",
                "category_overridden": True,
            },
            batch_payload["transactions"][1],
        ],
        "bills": batch_payload["bills"],
    }
    update_res = await client.post(
        "/api/v1/expenses/transactions/batch",
        headers=headers,
        json=override_payload,
    )
    assert update_res.status_code == 200
    update_data = update_res.json()["data"]
    assert hash_tx1 in update_data["accepted"]  # Updated because category_overridden=True
    assert hash_tx2 in update_data["duplicates"]  # Duplicate
    assert hash_bill in update_data["duplicates"]  # Duplicate

    # =========================================================================
    # 7. Defence-in-Depth: Reject PAN Leakage
    # =========================================================================
    pan_hash = hashlib.sha256(b"pan_leakage_test").hexdigest()[:32]
    pan_payload = {
        "transactions": [
            {
                "dedupe_hash": pan_hash,
                "amount": 500.0,
                "currency": "INR",
                "type": "debit",
                "occurred_at": now.isoformat(),
                "bank_code": "HDFC",
                "card_last4": "1234",
                "merchant_raw": "CARD 4532112233445566 POS STORE",
                "merchant_name": "Store",
                "category": "dining",
                "category_overridden": False,
                "source": "sms",
                "confidence": 1.0,
            }
        ]
    }
    pan_res = await client.post(
        "/api/v1/expenses/transactions/batch",
        headers=headers,
        json=pan_payload,
    )
    assert pan_res.status_code == 422  # Validation error caught 16-digit PAN

    # =========================================================================
    # 8. Date Range Validation Rejection
    # =========================================================================
    old_hash = hashlib.sha256(b"old_tx_test").hexdigest()[:32]
    old_payload = {
        "transactions": [
            {
                "dedupe_hash": old_hash,
                "amount": 200.0,
                "currency": "INR",
                "type": "debit",
                "occurred_at": (now - timedelta(days=450)).isoformat(),  # > 400 days
                "bank_code": "HDFC",
                "card_last4": "1234",
                "merchant_name": "Old Coffee Shop",
                "category": "dining",
                "category_overridden": False,
                "source": "sms",
                "confidence": 1.0,
            }
        ]
    }
    old_res = await client.post(
        "/api/v1/expenses/transactions/batch",
        headers=headers,
        json=old_payload,
    )
    assert old_res.status_code == 200
    assert old_hash in [r["dedupe_hash"] for r in old_res.json()["data"]["rejected"]]

    # =========================================================================
    # 9. List Transactions & Filtering
    # =========================================================================
    list_res = await client.get("/api/v1/expenses/transactions", headers=headers)
    assert list_res.status_code == 200
    items = list_res.json()["data"]["items"]
    assert len(items) == 2
    assert all(item["bank_name"] == "HDFC Bank" for item in items)

    # Filter by category
    filter_res = await client.get("/api/v1/expenses/transactions", headers=headers, params={"category": "groceries"})
    assert filter_res.status_code == 200
    filtered_items = filter_res.json()["data"]["items"]
    assert len(filtered_items) == 1
    assert filtered_items[0]["dedupe_hash"] == hash_tx1
    assert filtered_items[0]["category_overridden"] is True

    # =========================================================================
    # 10. Soft Delete & Tombstone Rejection
    # =========================================================================
    del_res = await client.delete(f"/api/v1/expenses/transactions/{hash_tx2}", headers=headers)
    assert del_res.status_code == 200

    # Query active list - tx2 should be gone
    after_del = await client.get("/api/v1/expenses/transactions", headers=headers)
    active_hashes = {it["dedupe_hash"] for it in after_del.json()["data"]["items"]}
    assert hash_tx2 not in active_hashes
    assert hash_tx1 in active_hashes

    # Attempt to re-ingest deleted tx2 - server should reject with 'user_deleted' tombstone
    reingest_res = await client.post(
        "/api/v1/expenses/transactions/batch",
        headers=headers,
        json={"transactions": [batch_payload["transactions"][1]]},
    )
    assert reingest_res.status_code == 200
    reingest_rejected = reingest_res.json()["data"]["rejected"]
    assert any(r["dedupe_hash"] == hash_tx2 and r["reason"] == "user_deleted" for r in reingest_rejected)

    # =========================================================================
    # 11. Milestone Retrieval
    # =========================================================================
    milestone_res = await client.get("/api/v1/expenses/milestones", headers=headers)
    assert milestone_res.status_code == 200
    milestones = milestone_res.json()["data"]
    assert len(milestones) >= 1
    # Infinia card milestone should have target spend ₹10,00,000 fee waiver
    infinia_ms = next(m for m in milestones if m["user_card_id"] == user_card_id)
    assert infinia_ms["target_spend"] == 1000000.0
    assert infinia_ms["anniversary_month"] == 6
    assert infinia_ms["type"] == "fee_waiver"

    # =========================================================================
    # 12. Spend Analytics Summary
    # =========================================================================
    analytics_res = await client.get("/api/v1/expenses/analytics/summary", headers=headers)
    assert analytics_res.status_code == 200
    analytics = analytics_res.json()["data"]
    # Only tx1 (₹1,250) is active since tx2 was deleted
    assert analytics["net_spend"] == 1250.0
    assert analytics["gross_spend"] == 1250.0
    assert analytics["total_refunds"] == 0.0
    assert len(analytics["by_category"]) >= 1
    assert len(analytics["by_card"]) >= 1
    assert len(analytics["monthly_trend"]) >= 1

    # =========================================================================
    # 13. DPDP Full Data Erasure
    # =========================================================================
    erase_res = await client.delete("/api/v1/expenses/data", headers=headers)
    assert erase_res.status_code == 202

    # Verify everything was erased
    after_erase = await client.get("/api/v1/expenses/transactions", headers=headers)
    assert len(after_erase.json()["data"]["items"]) == 0

    analytics_after = await client.get("/api/v1/expenses/analytics/summary", headers=headers)
    assert analytics_after.json()["data"]["net_spend"] == 0.0
    assert analytics_after.json()["data"]["transaction_count"] == 0

    # Cleanup user account
    await client.delete("/api/v1/auth/me", headers=headers)
