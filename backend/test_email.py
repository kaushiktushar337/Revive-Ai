from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import main

main.MOCK_EXTERNAL_ACTIONS = True if hasattr(main, 'MOCK_EXTERNAL_ACTIONS') else True
main.RAZORPAY_WEBHOOK_SECRET = ""
main.DB = Path(tempfile.mkstemp(prefix="revive-email-", suffix=".db")[1])
main.init_db()



def auth_headers(client):
    r = client.post("/api/auth/login", json={"login_email":"demo@revive.local","password":"demo12345"})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_email_requires_consent_and_then_sends():
    with TestClient(main.app) as client:
        h=auth_headers(client)
        created = client.post("/api/events", headers=h, json={
            "event_type": "payment_failed",
            "customer": "Email Demo",
            "amount": 18500,
            "customer_email": "demo@example.com",
            "consent_to_email": True,
            "previous_success_rate": 0.86,
            "prior_contacts": 0,
            "failure_reason": "insufficient_funds",
        })
        assert created.status_code == 200
        event_id = created.json()["id"]
        preview = client.get(f"/api/events/{event_id}/email-preview", headers=h)
        assert preview.status_code == 200
        denied = client.post("/api/recovery/email", headers=h, json={"event_id": event_id, "recipient": "demo@example.com", "consent": False})
        assert denied.status_code == 400
        sent = client.post("/api/recovery/email", headers=h, json={"event_id": event_id, "recipient": "demo@example.com", "consent": True})
        assert sent.status_code == 200
        assert sent.json()["mocked"] is True
        row = main.db().execute("SELECT contact_count, lifecycle_status FROM events WHERE id=?", (event_id,)).fetchone()
        assert row["contact_count"] == 1
        assert row["lifecycle_status"] == "AWAITING_OUTCOME"


def test_merchant_email_test_endpoint_in_demo_mode():
    with TestClient(main.app) as client:
        h = auth_headers(client)
        r = client.post('/api/auth/email-test', headers=h, json={'recipient':'test-recipient@example.com'})
        assert r.status_code == 200
        assert r.json()['mocked'] is True
        assert r.json()['sender'] == 'demo@revive.local'


def test_real_smtp_mode_requires_credentials():
    with TestClient(main.app) as client:
        h = auth_headers(client)
        r = client.put('/api/auth/email-settings', headers=h, json={
            'sender_email':'sender@example.com',
            'use_demo_email':False,
            'smtp_host':'smtp.example.com',
            'smtp_port':587,
            'smtp_username':'sender@example.com',
            'smtp_password':None,
        })
        assert r.status_code == 400
