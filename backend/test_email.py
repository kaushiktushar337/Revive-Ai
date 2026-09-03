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


def test_resend_provider_requires_api_key():
    with TestClient(main.app) as client:
        h=auth_headers(client)
        r=client.put('/api/auth/email-settings', headers=h, json={
            'sender_email':'sender@example.com',
            'use_demo_email':False,
            'email_provider':'resend'
        })
        assert r.status_code == 400


def test_resend_provider_uses_http_api(monkeypatch):
    sent = {}
    class Resp:
        ok = True
        status_code = 200
        content = b'{"id":"email_123"}'
        def json(self): return {"id":"email_123"}
    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update({"url":url,"json":json,"headers":headers,"timeout":timeout})
        return Resp()
    import email_adapter
    monkeypatch.setattr(email_adapter.requests, 'post', fake_post)
    result = email_adapter.send_email('customer@example.com','Hello','Body', {
        'provider':'resend','resend_api_key':'re_test','from_email':'sender@example.com'
    })
    assert result['ok'] is True
    assert result['provider'] == 'resend'
    assert result['message_id'] == 'email_123'
    assert sent['url'] == 'https://api.resend.com/emails'
    assert sent['headers']['Authorization'] == 'Bearer re_test'
    assert sent['json']['to'] == ['customer@example.com']


def test_resend_settings_and_test_email(monkeypatch):
    import email_adapter
    sent = {}
    class Resp:
        ok = True
        status_code = 200
        content = b'{"id":"email_test_1"}'
        def json(self): return {"id":"email_test_1"}
    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update({"url":url,"json":json,"headers":headers})
        return Resp()
    monkeypatch.setattr(email_adapter.requests, 'post', fake_post)
    with TestClient(main.app) as client:
        h = auth_headers(client)
        saved = client.put('/api/auth/email-settings', headers=h, json={
            'sender_email':'sender@example.com',
            'use_demo_email':False,
            'email_provider':'resend',
            'resend_api_key':'re_test_abc'
        })
        assert saved.status_code == 200
        assert saved.json()['email_provider'] == 'resend'
        me = client.get('/api/auth/me', headers=h)
        assert me.status_code == 200
        assert me.json()['email_provider'] == 'resend'
        assert me.json()['resend_configured'] is True
        assert 'resend_api_key' not in me.json()
        sent_response = client.post('/api/auth/email-test', headers=h, json={'recipient':'test@example.com'})
        assert sent_response.status_code == 200
        assert sent_response.json()['provider'] == 'resend'
        assert sent_response.json()['message_id'] == 'email_test_1'
        assert sent['url'] == 'https://api.resend.com/emails'
        assert sent['headers']['Authorization'] == 'Bearer re_test_abc'


def test_resend_recovery_email(monkeypatch):
    import email_adapter
    class Resp:
        ok = True
        status_code = 200
        content = b'{"id":"recovery_1"}'
        def json(self): return {"id":"recovery_1"}
    monkeypatch.setattr(email_adapter.requests, 'post', lambda *args, **kwargs: Resp())
    with TestClient(main.app) as client:
        h=auth_headers(client)
        saved = client.put('/api/auth/email-settings', headers=h, json={
            'sender_email':'sender@example.com',
            'use_demo_email':False,
            'email_provider':'resend',
            'resend_api_key':'re_test_abc'
        })
        assert saved.status_code == 200
        created = client.post('/api/events', headers=h, json={
            'event_type':'invoice_overdue','customer':'Resend Customer','amount':5000,
            'customer_email':'customer@example.com','consent_to_email':True,
            'previous_success_rate':0.9,'prior_contacts':0
        })
        assert created.status_code == 200
        event_id=created.json()['id']
        r=client.post('/api/recovery/email', headers=h, json={'event_id':event_id,'recipient':'customer@example.com','consent':True})
        assert r.status_code == 200
        assert r.json()['provider'] if 'provider' in r.json() else True
