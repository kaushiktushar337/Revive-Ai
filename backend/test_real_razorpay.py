from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
import main
import razorpay_adapter

class FakeResponse:
    def __init__(self, payload, status=200): self._payload=payload; self.status_code=status; self.ok=status<400; self.text=str(payload)
    def json(self): return self._payload
    def raise_for_status(self):
        if not self.ok: raise RuntimeError(f'HTTP {self.status_code}')

def test_merchant_razorpay_connection_and_link_and_sync(monkeypatch):
    tmp = Path(tempfile.mkdtemp())/'revive.db'
    monkeypatch.setattr(main, 'DB', tmp)
    monkeypatch.setattr(main, 'SEED', tmp.parent/'none.json')
    main.init_db()
    client = TestClient(main.app)
    reg = client.post('/api/auth/register', json={
        'business_name':'Test Shop','login_email':'shop@example.com','password':'password123',
        'sender_email':'recover@example.com','use_demo_email':True
    })
    assert reg.status_code == 200
    token = reg.json()['token']; headers={'Authorization':f'Bearer {token}'}
    fake_state={'links':{}}
    def fake_request(method, url, **kwargs):
        if method=='GET' and url.endswith('/payments'):
            return FakeResponse({'items':[]})
        if method=='POST' and url.endswith('/payment_links'):
            data=kwargs['json']; link={'id':'plink_real_test_1','short_url':'https://rzp.io/l/test1','status':'created','amount':data['amount'],'currency':'INR','reference_id':data['reference_id'],'amount_paid':0}
            fake_state['links'][link['id']]=link; return FakeResponse(link)
        if method=='GET' and '/payment_links/' in url:
            return FakeResponse(fake_state['links']['plink_real_test_1'])
        raise AssertionError((method,url))
    monkeypatch.setattr(razorpay_adapter.requests, 'request', fake_request)
    r=client.put('/api/integrations/razorpay/settings',headers=headers,json={'key_id':'rzp_test_123456789','key_secret':'secret_123456789','webhook_secret':'webhook_secret_123','mode':'test'})
    assert r.status_code==200
    r=client.get('/api/integrations/razorpay/test-merchant',headers=headers)
    assert r.status_code==200 and r.json()['ok'] is True
    # Force real adapter mode for this test
    monkeypatch.setattr(razorpay_adapter, 'MOCK_EXTERNAL_ACTIONS', False)
    e=client.post('/api/events',headers=headers,json={'event_type':'invoice_overdue','customer':'Alice','amount':18500,'currency':'INR','source':'razorpay_test','failure_reason':None,'days_overdue':7,'previous_success_rate':0.9,'customer_value':50000,'customer_email':'alice@example.com','consent_to_email':True})
    assert e.status_code==200
    event_id=e.json()['id']
    ex=client.post(f'/api/events/{event_id}/execute',headers=headers)
    assert ex.status_code==200 and ex.json()['action_payload']['id']=='plink_real_test_1'
    fake_state['links']['plink_real_test_1']['status']='paid'; fake_state['links']['plink_real_test_1']['amount_paid']=18500*100
    sync=client.post(f'/api/events/{event_id}/sync-payment-link',headers=headers)
    assert sync.status_code==200 and sync.json()['recovered'] is True
