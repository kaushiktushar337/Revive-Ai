from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
import main


def setup_client():
    tmp = Path(tempfile.mkdtemp()) / 'revive.db'
    main.DB = tmp
    main.SEED = tmp.parent / 'none.json'
    main.init_db()
    client = TestClient(main.app)
    reg = client.post('/api/auth/register', json={
        'business_name': 'Hardening Shop', 'login_email': 'hardening@example.com',
        'password': 'password123', 'sender_email': 'recover@example.com', 'use_demo_email': True
    })
    assert reg.status_code == 200
    return client, {'Authorization': f"Bearer {reg.json()['token']}"}


def test_gateway_secret_update_preserves_existing_secret(monkeypatch):
    client, headers = setup_client()
    monkeypatch.setattr(main, 'RAZORPAY_KEY_ID', '')
    saved = client.put('/api/integrations/razorpay/settings', headers=headers, json={
        'key_id': 'rzp_test_1234567890', 'key_secret': 'supersecret123',
        'webhook_secret': 'webhooksecret123', 'mode': 'test'
    })
    assert saved.status_code == 200
    saved2 = client.put('/api/integrations/razorpay/settings', headers=headers, json={
        'key_id': 'rzp_test_1234567890', 'mode': 'test'
    })
    assert saved2.status_code == 200
    conn = main.db(); row = conn.execute('SELECT razorpay_key_secret, razorpay_webhook_secret FROM merchants WHERE login_email=?', ('hardening@example.com',)).fetchone(); conn.close()
    assert row['razorpay_key_secret'] == 'supersecret123'
    assert row['razorpay_webhook_secret'] == 'webhooksecret123'


def test_event_keeps_gateway_when_merchant_switches(monkeypatch):
    client, headers = setup_client()
    main.MOCK_EXTERNAL_ACTIONS = True
    # Configure PayU and create a recovery event on PayU.
    p = client.put('/api/integrations/payu/settings', headers=headers, json={
        'merchant_id':'MID123','client_id':'client12345','client_secret':'secret12345','key':'key','salt':'salt','mode':'test'
    })
    assert p.status_code == 200
    e = client.post('/api/events', headers=headers, json={
        'event_type':'invoice_overdue','customer':'Alice','amount':1000,'currency':'INR','source':'test','days_overdue':7,
        'previous_success_rate':0.9,'customer_value':4000,'customer_email':'alice@example.com','consent_to_email':True
    })
    assert e.status_code == 200
    eid=e.json()['id']
    # Configure Razorpay; active gateway changes, but historical event remains PayU.
    r = client.put('/api/integrations/razorpay/settings', headers=headers, json={
        'key_id':'rzp_test_1234567890','key_secret':'supersecret123','webhook_secret':'webhooksecret123','mode':'test'
    })
    assert r.status_code == 200
    conn=main.db(); row=conn.execute('SELECT payment_gateway FROM events WHERE id=?',(eid,)).fetchone(); conn.close()
    assert row['payment_gateway'] == 'payu'


def test_simulation_creates_a_small_calculated_batch():
    client, headers = setup_client()
    response = client.post('/api/simulate-leaks', headers=headers, json={'count': 3})
    assert response.status_code == 200
    created = response.json()['created']
    assert len(created) == 3
    assert all(item['amount'] > 0 and 0 <= item['risk_score'] <= 100 for item in created)
    dashboard = client.get('/api/dashboard', headers=headers).json()
    assert len(dashboard['events']) >= 3
    assert len(dashboard['metrics']) > 0

def test_customer_history_derives_revenue_risk_from_unpaid_overdue_bill():
    client, headers = setup_client()
    response = client.post('/api/customers/history', headers=headers, json={
        'name': 'History Customer', 'email': 'history@example.com',
        'segment': 'SaaS',
        'bills': [
            {'invoice_id': 'HIST-1', 'amount': 1000, 'due_date': '2026-08-01', 'paid_date': '2026-08-02', 'status': 'paid', 'payment_method': 'UPI'},
            {'invoice_id': 'HIST-2', 'amount': 2500, 'due_date': '2026-08-20', 'status': 'unpaid'},
        ]
    })
    assert response.status_code == 200
    history = client.get(f"/api/customers/{response.json()['customer_id']}/history", headers=headers)
    assert history.status_code == 200
    assert len(history.json()['bills']) == 2
    scan = client.post('/api/customers/scan', headers=headers)
    assert scan.status_code == 200
    assert scan.json()['count'] == 1
    assert scan.json()['created'][0]['amount'] == 2500


def test_customer_history_is_merchant_isolated():
    tmp = Path(tempfile.mkdtemp()) / 'revive.db'
    main.DB = tmp
    main.SEED = tmp.parent / 'none.json'
    main.init_db()
    client = TestClient(main.app)
    ra = client.post('/api/auth/register', json={'business_name':'Shop A','login_email':'a-unique@example.com','password':'password123','sender_email':'a@x.com','use_demo_email':True})
    rb = client.post('/api/auth/register', json={'business_name':'Shop B','login_email':'b-unique@example.com','password':'password123','sender_email':'b@x.com','use_demo_email':True})
    assert ra.status_code == 200 and rb.status_code == 200
    a=ra.json(); b=rb.json()
    ha={'Authorization':f"Bearer {a['token']}"}; hb={'Authorization':f"Bearer {b['token']}"}
    ca=client.post('/api/customers/history',headers=ha,json={'name':'Alice','email':'alice@x.com','bills':[{'invoice_id':'A-1','amount':1000,'due_date':'2026-08-01','status':'unpaid'}]}).json()
    assert client.get('/api/customers',headers=hb).json()['customers'] == []
    assert client.get(f"/api/customers/{ca['customer_id']}/history",headers=hb).status_code == 404
