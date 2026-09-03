from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
import main
import payu_adapter

class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload=payload; self.status_code=status; self.ok=status<400; self.text=str(payload)
    def json(self): return self._payload
    def raise_for_status(self):
        if not self.ok: raise RuntimeError(f'HTTP {self.status_code}: {self.text}')

def test_payu_connection_and_link_and_sync(monkeypatch):
    tmp=Path(tempfile.mkdtemp())/'revive.db'
    monkeypatch.setattr(main,'DB',tmp); monkeypatch.setattr(main,'SEED',tmp.parent/'none.json')
    main.init_db(); client=TestClient(main.app)
    reg=client.post('/api/auth/register',json={'business_name':'PayU Shop','login_email':'payu@example.com','password':'password123','sender_email':'recover@example.com','use_demo_email':True})
    assert reg.status_code==200
    token=reg.json()['token']; headers={'Authorization':f'Bearer {token}'}
    state={'link':{}}
    def fake_request(method,url,**kwargs):
        if method=='POST' and url.endswith('/oauth/token'):
            return FakeResponse({'access_token':'token123','token_type':'Bearer','expires_in':7200,'scope':'read_payment_links create_payment_links'})
        if method=='POST' and url.endswith('/payment-links/'):
            body=kwargs['json']; link={'invoiceNumber':body['invoiceNumber'],'paymentLink':'https://pp72.pmny.in/TESTREVIVE','status':'created','subAmount':body['subAmount'],'totalAmount':body['subAmount']}
            state['link']=link; return FakeResponse({'status':0,'message':'paymentLink generated','result':link})
        if method=='GET' and '/payment-links/' in url:
            return FakeResponse({'status':0,'result':state['link']})
        raise AssertionError((method,url,kwargs))
    monkeypatch.setattr(payu_adapter.requests,'request',fake_request)
    saved=client.put('/api/integrations/payu/settings',headers=headers,json={'merchant_id':'MID123','client_id':'client12345','client_secret':'secret12345','key':'testkey','salt':'salttest','mode':'test'})
    assert saved.status_code==200
    test=client.get('/api/integrations/payu/test-merchant',headers=headers)
    assert test.status_code==200 and test.json()['ok'] is True
    monkeypatch.setattr(payu_adapter,'MOCK_EXTERNAL_ACTIONS',False)
    e=client.post('/api/events',headers=headers,json={'event_type':'invoice_overdue','customer':'Alice','amount':18500,'currency':'INR','source':'payu_test','days_overdue':7,'previous_success_rate':0.9,'customer_value':50000,'customer_email':'alice@example.com','consent_to_email':True})
    assert e.status_code==200
    event_id=e.json()['id']
    ex=client.post(f'/api/events/{event_id}/execute',headers=headers)
    assert ex.status_code==200 and ex.json()['action_payload']['gateway']=='payu'
    state['link']['status']='paid'; state['link']['totalAmount']=18500
    sync=client.post(f'/api/events/{event_id}/sync-payment-link',headers=headers)
    assert sync.status_code==200 and sync.json()['recovered'] is True

def test_payu_webhook_hash_reconciliation(monkeypatch):
    import hashlib
    tmp=Path(tempfile.mkdtemp())/'revive.db'
    monkeypatch.setattr(main,'DB',tmp); monkeypatch.setattr(main,'SEED',tmp.parent/'none.json')
    main.init_db(); client=TestClient(main.app)
    reg=client.post('/api/auth/register',json={'business_name':'Webhook Shop','login_email':'wh@example.com','password':'password123','sender_email':'recover@example.com','use_demo_email':True})
    token=reg.json()['token']; headers={'Authorization':f'Bearer {token}'}; mid=reg.json()['merchant']['id']
    conn=main.db(); conn.execute("UPDATE merchants SET payu_salt='salttest', payu_merchant_id='MID123', payu_client_id='c', payu_client_secret='s' WHERE id=?",(mid,)); conn.commit(); conn.close()
    e=client.post('/api/events',headers=headers,json={'event_type':'payment_failed','customer':'Bob','amount':1000,'currency':'INR','source':'payu_test','failure_reason':'temporary_decline','previous_success_rate':0.8,'customer_value':3000,'customer_email':'bob@example.com','consent_to_email':True})
    eid=e.json()['id']
    data={'mihpayid':'M1','status':'success','key':'k','txnid':eid,'amount':'1000.00','email':'bob@example.com','firstname':'Bob','productinfo':'Revive recovery','udf1':eid,'udf2':'','udf3':'','udf4':'','udf5':''}
    value='|'.join(['salttest','success','','','','','',data['udf5'],data['udf4'],data['udf3'],data['udf2'],data['udf1'],data['email'],data['firstname'],data['productinfo'],data['amount'],data['txnid'],data['key']])
    data['hash']=hashlib.sha512(value.encode()).hexdigest()
    r=client.post(f'/api/webhooks/payu/{mid}',headers={'Content-Type':'application/x-www-form-urlencoded'},data=data)
    assert r.status_code==200 and r.json()['recovered'] is True
