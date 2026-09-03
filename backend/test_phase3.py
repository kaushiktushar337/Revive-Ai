import hashlib, hmac, json, os, tempfile
from pathlib import Path
os.environ["MOCK_EXTERNAL_ACTIONS"] = "true"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_secret"
from fastapi.testclient import TestClient
import main
main.DB = Path(tempfile.mkstemp(prefix="revive-phase3-", suffix=".db")[1])
main.RAZORPAY_WEBHOOK_SECRET = "test_secret"

def signed(body):
    raw=json.dumps(body,separators=(",",":")).encode(); return hmac.new(b"test_secret",raw,hashlib.sha256).hexdigest(),raw

def hook(client,body):
    sig,raw=signed(body); return client.post('/api/webhooks/razorpay',content=raw,headers={'X-Razorpay-Signature':sig})


def auth_headers(client):
    r = client.post("/api/auth/login", json={"login_email":"demo@revive.local","password":"demo12345"})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}

def test_link_paid_recovery():
    with TestClient(main.app) as c:
        h=auth_headers(c)
        e=c.post('/api/events',headers=h,json={'event_type':'invoice_overdue','customer':'Acme','amount':2500,'days_overdue':7,'previous_success_rate':0.9}).json()
        assert e['recommended_action']=='send_payment_link'
        x=c.post(f"/api/events/{e['id']}/execute", headers=h); assert x.status_code==200
        out=x.json(); assert out['lifecycle_status']=='AWAITING_OUTCOME'; assert out['action_payload']['id']
        paid={'id':'wh_paid','event':'payment_link.paid','payload':{'payment_link':{'entity':{'id':out['action_payload']['id'],'amount':250000,'amount_paid':250000,'currency':'INR','reference_id':e['id'],'short_url':out['reference'],'status':'paid'}},'payment':{'entity':{'id':'pay1','amount':250000,'currency':'INR','status':'captured'}},'order':{'entity':{'id':'ord1','amount':250000,'currency':'INR'}}}}
        r=hook(c,paid); assert r.status_code==200; assert r.json()['lifecycle_status']=='RECOVERED'
        item=next(z for z in c.get('/api/dashboard',headers=h).json()['events'] if z['id']==e['id'])
        assert item['recovered']==1 and item['recovered_amount']==2500 and item['outcome_source']=='payment_link_webhook'

def test_link_expired_and_dedupe():
    with TestClient(main.app) as c:
        h=auth_headers(c)
        e=c.post('/api/events',headers=h,json={'event_type':'invoice_overdue','customer':'Expired','amount':3000,'days_overdue':8,'previous_success_rate':0.85}).json()
        out=c.post(f"/api/events/{e['id']}/execute", headers=h).json()
        body={'id':'wh_exp','event':'payment_link.expired','payload':{'payment_link':{'entity':{'id':out['action_payload']['id'],'amount':300000,'amount_paid':0,'currency':'INR','reference_id':e['id'],'short_url':out['reference'],'status':'expired'}}}}
        r=hook(c,body); assert r.status_code==200; assert r.json()['lifecycle_status']=='LINK_EXPIRED'
        r2=hook(c,body); assert r2.json()['deduplicated'] is True

def test_manual_recovery_lifecycle():
    with TestClient(main.app) as c:
        h=auth_headers(c)
        e=c.post('/api/events',headers=h,json={'event_type':'checkout_abandoned','customer':'Buyer','amount':1200,'event_age_hours':4,'previous_success_rate':0.9}).json()
        r=c.post(f"/api/events/{e['id']}/confirm-recovered", headers=h); assert r.status_code==200
        item=next(z for z in c.get('/api/dashboard',headers=h).json()['events'] if z['id']==e['id'])
        assert item['lifecycle_status']=='RECOVERED' and item['recovered_at'] and item['outcome_source']=='manual_demo'
