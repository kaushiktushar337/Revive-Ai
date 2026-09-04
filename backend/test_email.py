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


def test_demo_email_requires_consent_and_sends():
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


def test_demo_email_test_endpoint():
    with TestClient(main.app) as client:
        h = auth_headers(client)
        r = client.post('/api/auth/email-test', headers=h, json={'recipient':'test-recipient@example.com'})
        assert r.status_code == 200
        assert r.json()['mocked'] is True
        assert r.json()['sender'] == 'demo@revive.local'


def test_brevo_provider_uses_http_api(monkeypatch):
    sent = {}
    class Resp:
        ok = True
        status_code = 201
        content = b'{"messageId":"<email_123>"}'
        def json(self): return {"messageId":"<email_123>"}
    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update({"url":url,"json":json,"headers":headers,"timeout":timeout})
        return Resp()
    import email_adapter
    monkeypatch.setattr(email_adapter.requests, 'post', fake_post)
    result = email_adapter.send_email('customer@example.com','Hello','Body', {
        'provider':'brevo','brevo_api_key':'xkeysib-test','from_email':'sender@example.com','from_name':'ReviveAI'
    })
    assert result['ok'] is True
    assert result['provider'] == 'brevo'
    assert result['message_id'] == '<email_123>'
    assert sent['url'] == 'https://api.brevo.com/v3/smtp/email'
    assert sent['headers']['api-key'] == 'xkeysib-test'
    assert sent['json']['to'] == [{'email':'customer@example.com'}]


def test_brevo_settings_require_server_configuration(monkeypatch):
    original_key = main.BREVO_API_KEY
    original_from = main.EMAIL_FROM
    try:
        main.BREVO_API_KEY = ''
        main.EMAIL_FROM = ''
        with TestClient(main.app) as client:
            h = auth_headers(client)
            r = client.put('/api/auth/email-settings', headers=h, json={
                'sender_email':'sender@example.com',
                'use_demo_email':False,
                'email_provider':'brevo'
            })
            assert r.status_code == 503
    finally:
        main.BREVO_API_KEY = original_key
        main.EMAIL_FROM = original_from


def test_brevo_recovery_email(monkeypatch):
    import email_adapter
    class Resp:
        ok = True
        status_code = 201
        content = b'{"messageId":"<recovery_1>"}'
        def json(self): return {"messageId":"<recovery_1>"}
    monkeypatch.setattr(email_adapter.requests, 'post', lambda *args, **kwargs: Resp())
    original_key = main.BREVO_API_KEY
    original_from = main.EMAIL_FROM
    original_provider = main.EMAIL_PROVIDER
    try:
        main.BREVO_API_KEY = 'xkeysib-test'
        main.EMAIL_FROM = 'sender@example.com'
        main.EMAIL_PROVIDER = 'brevo'
        with TestClient(main.app) as client:
            h=auth_headers(client)
            saved = client.put('/api/auth/email-settings', headers=h, json={
                'sender_email':'sender@example.com',
                'use_demo_email':False,
                'email_provider':'brevo'
            })
            assert saved.status_code == 200
            created = client.post('/api/events', headers=h, json={
                'event_type':'invoice_overdue','customer':'Brevo Customer','amount':5000,
                'customer_email':'customer@example.com','consent_to_email':True,
                'previous_success_rate':0.9,'prior_contacts':0
            })
            assert created.status_code == 200
            event_id=created.json()['id']
            r=client.post('/api/recovery/email', headers=h, json={
                'event_id':event_id,
                'recipient':'customer@example.com',
                'consent':True,
                'subject':'Edited subject',
                'body':'Edited body'
            })
            assert r.status_code == 200
            assert r.json()['provider'] == 'brevo'
    finally:
        main.BREVO_API_KEY = original_key
        main.EMAIL_FROM = original_from
        main.EMAIL_PROVIDER = original_provider
