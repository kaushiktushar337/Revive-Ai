import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path

os.environ["MOCK_EXTERNAL_ACTIONS"] = "true"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_secret"

from fastapi.testclient import TestClient

import main

_TEST_DB = Path(tempfile.mkstemp(prefix="revive-test-", suffix=".db")[1])
main.DB = _TEST_DB
main.RAZORPAY_WEBHOOK_SECRET = "test_secret"


def signed(body: dict) -> tuple[str, str]:
    raw = json.dumps(body, separators=(",", ":")).encode()
    sig = hmac.new(b"test_secret", raw, hashlib.sha256).hexdigest()
    return sig, raw.decode()



def auth_headers(client):
    r = client.post("/api/auth/login", json={"login_email":"demo@revive.local","password":"demo12345"})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_razorpay_failed_webhook_creates_risk_event():
    payload = {
        "id": "wh_test_1",
        "event": "payment.failed",
        "payload": {"payment": {"entity": {
            "id": "pay_test_1", "amount": 1850000, "currency": "INR",
            "email": "rahul@example.com", "error_reason": "insufficient_funds"
        }}}
    }
    sig, raw = signed(payload)
    with TestClient(main.app) as client:
        h=auth_headers(client)
        response = client.post("/api/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": sig})
        assert response.status_code == 200
        data = response.json()
        assert data["recommended_action"] in {"retry_payment", "send_payment_link", "send_recovery_message", "send_payment_update", "escalate", "do_nothing"}
        duplicate = client.post("/api/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": sig})
        assert duplicate.status_code == 200
        assert duplicate.json()["deduplicated"] is True


def test_invalid_signature_is_rejected():
    payload = {"event": "payment.failed", "payload": {"payment": {"entity": {"id": "pay_bad", "amount": 100, "currency": "INR"}}}}
    raw = json.dumps(payload).encode()
    with TestClient(main.app) as client:
        h=auth_headers(client)
        response = client.post("/api/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": "bad"})
        assert response.status_code == 401


def test_captured_payment_reconciles_existing_failed_payment():
    failed = {
        "id": "wh_failed_2",
        "event": "payment.failed",
        "payload": {"payment": {"entity": {"id": "pay_test_2", "amount": 2500000, "currency": "INR", "email": "buyer@example.com", "error_reason": "temporary_decline"}}}
    }
    captured = {
        "id": "wh_captured_2",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_test_2", "amount": 2500000, "currency": "INR", "email": "buyer@example.com"}}}
    }
    with TestClient(main.app) as client:
        h=auth_headers(client)
        sig, raw = signed(failed)
        first = client.post("/api/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": sig})
        assert first.status_code == 200
        sig, raw = signed(captured)
        second = client.post("/api/webhooks/razorpay", content=raw, headers={"X-Razorpay-Signature": sig})
        assert second.status_code == 200
        assert second.json()["reconciled"] is True
