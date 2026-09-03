from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import APP_ENV, CORS_ORIGINS, RAZORPAY_KEY_ID, RAZORPAY_WEBHOOK_SECRET
from engine import bounded_decision
from model import predict_probability
from razorpay_adapter import create_payment_link, test_connection, verify_webhook_signature
from email_adapter import send_email
from auth import hash_password, issue_token, verify_password, verify_token

BASE = Path(__file__).resolve().parent
DB = BASE / "revive.db"
SEED = BASE / "seed_events.json"

app = FastAPI(title="Revive API", version="0.3.0", description="AI revenue recovery prototype API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MerchantSignupIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    login_email: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    sender_email: str = Field(min_length=5, max_length=200)
    use_demo_email: bool = True
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None

class MerchantLoginIn(BaseModel):
    login_email: str
    password: str

class MerchantEmailSettingsIn(BaseModel):
    sender_email: str = Field(min_length=5, max_length=200)
    use_demo_email: bool = True
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None


def merchant_from_token(authorization: str | None) -> sqlite3.Row:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Authentication required')
    payload = verify_token(authorization.split(' ', 1)[1].strip())
    if not payload or not payload.get('sub'):
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    conn = db()
    row = conn.execute('SELECT * FROM merchants WHERE id=? AND active=1', (payload['sub'],)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail='Merchant account not found')
    return row


class EventIn(BaseModel):
    event_type: str
    customer: str = Field(min_length=1)
    amount: float = Field(gt=0)
    currency: str = "INR"
    external_id: str | None = None
    source: str = "simulator"
    failure_reason: str | None = None
    days_overdue: int = Field(default=0, ge=0)
    previous_success_rate: float = Field(default=0.7, ge=0, le=1)
    days_since_last_success: int = Field(default=30, ge=0)
    prior_contacts: int = Field(default=0, ge=0)
    customer_value: float = Field(default=0, ge=0)
    event_age_hours: float = Field(default=1, ge=0)
    is_subscription: bool = False
    customer_email: str | None = None
    consent_to_email: bool = False


class CheckoutEventIn(BaseModel):
    session_id: str = Field(min_length=3)
    customer: str = Field(min_length=1)
    amount: float = Field(gt=0)
    currency: str = "INR"
    stage: str = Field(pattern="^(started|completed)$")


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    conn = db()
    conn.execute("""CREATE TABLE IF NOT EXISTS merchants (
            id TEXT PRIMARY KEY,
            business_name TEXT NOT NULL,
            login_email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            sender_email TEXT NOT NULL,
            use_demo_email INTEGER NOT NULL DEFAULT 1,
            smtp_host TEXT,
            smtp_port INTEGER DEFAULT 587,
            smtp_username TEXT,
            smtp_password TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )""")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            customer TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            status TEXT NOT NULL,
            recovery_probability REAL NOT NULL,
            risk_score INTEGER NOT NULL,
            recommended_action TEXT NOT NULL,
            action_reason TEXT NOT NULL,
            risk_reason TEXT NOT NULL,
            delay_hours INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            action_status TEXT NOT NULL DEFAULT 'pending',
            recovered INTEGER NOT NULL DEFAULT 0,
            lifecycle_status TEXT NOT NULL DEFAULT 'DETECTED',
            recovery_link_id TEXT,
            recovery_link_url TEXT,
            recovery_expires_at TEXT,
            recovered_at TEXT,
            recovered_amount REAL,
            outcome_source TEXT
        )"""
    )
    ensure_column(conn, "events", "merchant_id", "TEXT")
    ensure_column(conn, "events", "external_id", "TEXT")
    ensure_column(conn, "events", "source", "TEXT DEFAULT 'simulator'")
    ensure_column(conn, "events", "action_reference", "TEXT")
    ensure_column(conn, "events", "action_payload", "TEXT")
    ensure_column(conn, "events", "lifecycle_status", "TEXT DEFAULT 'DETECTED'")
    ensure_column(conn, "events", "recovery_link_id", "TEXT")
    ensure_column(conn, "events", "recovery_link_url", "TEXT")
    ensure_column(conn, "events", "recovery_expires_at", "TEXT")
    ensure_column(conn, "events", "recovered_at", "TEXT")
    ensure_column(conn, "events", "recovered_amount", "REAL")
    ensure_column(conn, "events", "outcome_source", "TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_external_id ON events(external_id) WHERE external_id IS NOT NULL")
    ensure_column(conn, "events", "customer_email", "TEXT")
    ensure_column(conn, "events", "consent_to_email", "INTEGER DEFAULT 0")
    ensure_column(conn, "events", "contact_count", "INTEGER DEFAULT 0")
    ensure_column(conn, "events", "last_contact_at", "TEXT")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            merchant_id TEXT,
            event_id TEXT,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS checkout_sessions (
            session_id TEXT PRIMARY KEY,
            merchant_id TEXT,
            customer TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            event_id TEXT
        )"""
    )
    ensure_column(conn, "audit_logs", "merchant_id", "TEXT")
    ensure_column(conn, "checkout_sessions", "merchant_id", "TEXT")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS webhook_events (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            event_name TEXT NOT NULL,
            external_id TEXT,
            received_at TEXT NOT NULL,
            payload TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_webhook_external_id ON webhook_events(source, external_id) WHERE external_id IS NOT NULL")
    demo = conn.execute("SELECT id FROM merchants WHERE login_email=?", ("demo@revive.local",)).fetchone()
    if not demo:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("INSERT INTO merchants(id,business_name,login_email,password_hash,sender_email,use_demo_email,active,created_at) VALUES(?,?,?,?,?,?,?,?)", ("m_demo", "Revive Demo Merchant", "demo@revive.local", hash_password("demo12345"), "demo@revive.local", 1, 1, now))
    conn.execute("UPDATE events SET merchant_id='m_demo' WHERE merchant_id IS NULL")
    conn.execute("UPDATE checkout_sessions SET merchant_id='m_demo' WHERE merchant_id IS NULL")
    conn.commit()
    conn.close()


def audit(event_id: str | None, action: str, status: str, detail: str, merchant_id: str | None = "m_demo"):
    conn = db()
    conn.execute(
        "INSERT INTO audit_logs(id,merchant_id,event_id,action,status,detail,created_at) VALUES(?,?,?,?,?,?,?)",
        (f"log_{uuid.uuid4().hex[:10]}", merchant_id, event_id, action, status, detail, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def hydrate(event: dict[str, Any]):
    p = predict_probability(event)
    return bounded_decision(event, p)


def insert_event(event: dict[str, Any], decision, merchant_id: str = "m_demo"):
    event_id = event.get("id") or f"evt_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = db()
    conn.execute(
        """INSERT OR REPLACE INTO events
        (id,merchant_id,event_type,customer,amount,currency,status,recovery_probability,risk_score,recommended_action,action_reason,risk_reason,delay_hours,created_at,action_status,recovered,external_id,source,action_reference,action_payload,lifecycle_status,recovery_link_id,recovery_link_url,recovery_expires_at,recovered_at,recovered_amount,outcome_source,customer_email,consent_to_email)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            merchant_id,
            event["event_type"],
            event["customer"],
            event["amount"],
            event.get("currency", "INR"),
            "at_risk",
            decision.recovery_probability,
            decision.risk_score,
            decision.recommended_action,
            decision.action_reason,
            decision.risk_reason,
            decision.delay_hours,
            now,
            "pending",
            0,
            event.get("external_id"),
            event.get("source", "simulator"),
            None,
            None,
            "DETECTED",
            None,
            None,
            None,
            None,
            None,
            None,
            event.get("customer_email"),
            1 if event.get("consent_to_email") else 0,
        ),
    )
    conn.commit()
    conn.close()
    conn = db()
    lifecycle = "ESCALATION_REQUIRED" if decision.recommended_action == "escalate" else ("NO_ACTION" if decision.recommended_action == "do_nothing" else "RECOMMENDED")
    conn.execute("UPDATE events SET lifecycle_status=? WHERE id=?", (lifecycle, event_id))
    conn.commit()
    conn.close()
    audit(event_id, "decision", "recommended", f"{decision.recommended_action}: {decision.action_reason}", merchant_id)
    return event_id


def event_payload_to_internal(payload: dict[str, Any], source: str = "razorpay") -> dict[str, Any] | None:
    event_name = payload.get("event", "")
    payment = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
    payment_link = (((payload.get("payload") or {}).get("payment_link") or {}).get("entity") or {})
    order = (((payload.get("payload") or {}).get("order") or {}).get("entity") or {})

    entity = payment or payment_link or order
    amount = float(entity.get("amount") or 0) / 100
    customer = entity.get("email") or entity.get("contact") or (payment_link.get("customer") or {}).get("email") or (payment_link.get("customer") or {}).get("contact") or "Razorpay Customer"
    external_id = entity.get("id")
    common = {
        "customer": customer,
        "customer_email": entity.get("email") or (payment_link.get("customer") or {}).get("email"),
        "consent_to_email": False,
        "amount": amount,
        "currency": entity.get("currency") or payment_link.get("currency") or order.get("currency") or "INR",
        "external_id": payment.get("id") or external_id,
        "source": source,
        "previous_success_rate": 0.75,
        "customer_value": amount * 4,
        "event_age_hours": 0.2,
        "days_since_last_success": 7,
        "prior_contacts": 0,
        "is_subscription": bool(payment.get("subscription_id")),
    }
    if event_name in {"payment.failed", "order.payment_failed"}:
        return {**common, "event_type": "payment_failed", "failure_reason": payment.get("error_reason") or payment.get("error_description") or "temporary_decline"}
    if event_name in {"payment.captured", "order.paid", "payment.authorized"}:
        return {**common, "event_type": "payment_captured"}
    if event_name in {"payment_link.paid", "payment_link.partially_paid", "payment_link.cancelled", "payment_link.expired"}:
        paid_amount = float(payment_link.get("amount_paid") or 0) / 100
        return {
            **common,
            "event_type": event_name,
            "payment_link_id": payment_link.get("id"),
            "payment_link_reference_id": payment_link.get("reference_id"),
            "payment_link_url": payment_link.get("short_url"),
            "recovery_paid_amount": paid_amount,
            "payment_id": payment.get("id"),
            "order_id": order.get("id") or payment.get("order_id"),
            "payment_link_status": payment_link.get("status"),
            "recovery_expires_at": payment_link.get("expire_by"),
        }
    if event_name in {"payment.captured", "order.paid", "payment.authorized"}:
        return {**common, "event_type": "payment_captured"}
    return None


@app.on_event("startup")
def startup():
    init_db()
    conn = db()
    count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    conn.close()
    if count == 0 and SEED.exists():
        events = json.loads(SEED.read_text(encoding="utf-8"))
        for event in events:
            decision = hydrate(event)
            insert_event(event, decision)


@app.post("/api/auth/register")
def register_merchant(payload: MerchantSignupIn):
    init_db()
    email = payload.login_email.strip().lower()
    sender = payload.sender_email.strip().lower()
    conn = db()
    if conn.execute("SELECT id FROM merchants WHERE login_email=?", (email,)).fetchone():
        conn.close(); raise HTTPException(status_code=409, detail="An account with this login email already exists")
    merchant_id = f"m_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO merchants(id,business_name,login_email,password_hash,sender_email,use_demo_email,smtp_host,smtp_port,smtp_username,smtp_password,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (merchant_id,payload.business_name.strip(),email,hash_password(payload.password),sender,1 if payload.use_demo_email else 0,payload.smtp_host,payload.smtp_port,payload.smtp_username,payload.smtp_password,1,now))
    conn.commit(); conn.close()
    token = issue_token(merchant_id)
    return {"ok": True, "token": token, "merchant": {"id": merchant_id, "business_name": payload.business_name.strip(), "login_email": email, "sender_email": sender, "use_demo_email": payload.use_demo_email}}

@app.post("/api/auth/login")
def login_merchant(payload: MerchantLoginIn):
    conn = db(); row = conn.execute("SELECT * FROM merchants WHERE login_email=? AND active=1", (payload.login_email.strip().lower(),)).fetchone(); conn.close()
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid login email or password")
    token = issue_token(row["id"])
    return {"ok": True, "token": token, "merchant": {"id": row["id"], "business_name": row["business_name"], "login_email": row["login_email"], "sender_email": row["sender_email"], "use_demo_email": bool(row["use_demo_email"])}}

@app.get("/api/auth/me")
def me(merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    return {
        "id": merchant["id"],
        "business_name": merchant["business_name"],
        "login_email": merchant["login_email"],
        "sender_email": merchant["sender_email"],
        "use_demo_email": bool(merchant["use_demo_email"]),
        "smtp_host": merchant["smtp_host"],
        "smtp_port": merchant["smtp_port"],
        "smtp_username": merchant["smtp_username"],
        "smtp_configured": bool(merchant["smtp_host"] and merchant["smtp_username"] and merchant["smtp_password"]),
    }

@app.put("/api/auth/email-settings")
def update_email_settings(payload: MerchantEmailSettingsIn, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    sender = payload.sender_email.strip().lower()
    if not payload.use_demo_email:
        if not payload.smtp_host or not payload.smtp_username or not payload.smtp_password:
            raise HTTPException(status_code=400, detail="Real SMTP mode requires SMTP host, username, and password/app password")
    conn = db()
    conn.execute(
        "UPDATE merchants SET sender_email=?,use_demo_email=?,smtp_host=?,smtp_port=?,smtp_username=?,smtp_password=? WHERE id=?",
        (sender,1 if payload.use_demo_email else 0,payload.smtp_host,payload.smtp_port,payload.smtp_username,payload.smtp_password,merchant["id"]),
    )
    conn.commit(); conn.close()
    return {"ok": True, "sender_email": sender, "use_demo_email": payload.use_demo_email}


class EmailTestIn(BaseModel):
    recipient: str = Field(min_length=5, max_length=200)


@app.post("/api/auth/email-test")
def test_email_delivery(payload: EmailTestIn, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    recipient = payload.recipient.strip().lower()
    if "@" not in recipient:
        raise HTTPException(status_code=400, detail="Enter a valid test recipient email")
    if not merchant["sender_email"]:
        raise HTTPException(status_code=400, detail="Set a recovery sender email first")
    if not merchant["use_demo_email"] and not (merchant["smtp_host"] and merchant["smtp_username"] and merchant["smtp_password"]):
        raise HTTPException(status_code=400, detail="Configure SMTP before sending a real test email")

    subject = "ReviveAI test email"
    body = (
        f"Hi {merchant['business_name']},\n\n"
        "This is a test email from ReviveAI. Your recovery sender configuration is working.\n\n"
        f"Sender: {merchant['sender_email']}\n"
        f"Mode: {'Demo' if merchant['use_demo_email'] else 'SMTP'}\n\n"
        "You can now use ReviveAI to send recovery emails.\n"
    )
    result = send_email(
        recipient, subject, body,
        {
            "from_email": merchant["sender_email"],
            "mocked": bool(merchant["use_demo_email"]),
            "smtp_host": merchant["smtp_host"],
            "smtp_port": merchant["smtp_port"],
            "smtp_username": merchant["smtp_username"],
            "smtp_password": merchant["smtp_password"],
        },
    )
    audit(None, "email_test", "sent" if result.get("ok") else "failed", f"Test email {'sent' if result.get('ok') else 'failed'} to {recipient}.", merchant["id"])
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Email send failed"))
    return {
        "ok": True,
        "recipient": recipient,
        "sender": merchant["sender_email"],
        "mocked": bool(result.get("mocked")),
        "provider": result.get("provider"),
        "message_id": result.get("message_id"),
        "message": "Test email sent in demo mode." if result.get("mocked") else "Test email sent successfully.",
    }

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "revive-api",
        "environment": APP_ENV,
        "razorpay": {"configured": bool(RAZORPAY_KEY_ID), "webhook_verification": bool(RAZORPAY_WEBHOOK_SECRET)},
    }


@app.get("/api/integrations/razorpay/test")
def razorpay_test_connection():
    return test_connection()


@app.get("/api/dashboard")
def dashboard(merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    rows = conn.execute("SELECT * FROM events WHERE merchant_id=? ORDER BY created_at DESC", (merchant["id"],)).fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    at_risk = sum(r["amount"] for r in items if not r["recovered"] and r["action_status"] not in {"recovered"})
    recovered = sum(r["amount"] for r in items if r["recovered"])
    expected = sum(r["amount"] * r["recovery_probability"] for r in items if not r["recovered"])
    active = sum(1 for r in items if r["action_status"] in {"pending", "recommended"})
    return {
        "metrics": {
            "revenue_at_risk": round(at_risk, 2),
            "expected_recovery": round(expected, 2),
            "recovered": round(recovered, 2),
            "events": len(items),
            "active_actions": active,
            "recoverable_events": sum(1 for r in items if r["recommended_action"] != "do_nothing" and not r["recovered"]),
        },
        "events": items,
    }


@app.get("/api/audit")
def get_audit(limit: int = 100, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    rows = conn.execute("SELECT * FROM audit_logs WHERE merchant_id=? ORDER BY created_at DESC LIMIT ?", (merchant["id"], min(limit, 500))).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@app.post("/api/events")
def create_event(event: EventIn, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    payload = event.model_dump()
    if not payload["customer_value"]:
        payload["customer_value"] = payload["amount"]
    if payload.get("external_id"):
        conn = db()
        existing = conn.execute("SELECT id FROM events WHERE external_id=?", (payload["external_id"],)).fetchone()
        conn.close()
        if existing:
            return {"id": existing["id"], "deduplicated": True}
    decision = hydrate(payload)
    event_id = insert_event(payload, decision, merchant["id"])
    return {"id": event_id, "deduplicated": False, **payload, **decision.__dict__}


@app.post("/api/events/{event_id}/execute")
def execute_event(event_id: str, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    row = conn.execute("SELECT * FROM events WHERE id=? AND merchant_id=?", (event_id, merchant["id"])).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    action = row["recommended_action"]
    action_payload: dict[str, Any] = {}
    status = "STOPPED"
    lifecycle = "NO_ACTION"
    reference = None
    link_id = None
    link_url = None
    expires_at = None

    if action == "do_nothing":
        message = "Agent stopped the workflow because the expected benefit did not justify intervention."
        lifecycle = "NO_ACTION"
    elif action == "escalate":
        status = "ESCALATION_REQUIRED"
        lifecycle = "ESCALATION_REQUIRED"
        message = "Agent escalated the case because the bounded policy requires human approval."
    elif action == "send_payment_link":
        result = create_payment_link(row["amount"], row["customer"], f"Revive recovery for {row['customer']}", event_id)
        reference = result.get("short_url") or result.get("id")
        link_id = result.get("id")
        link_url = result.get("short_url")
        expires_at = result.get("expire_by")
        action_payload = result
        status = "EXECUTED"
        lifecycle = "AWAITING_OUTCOME"
        message = f"Recovery payment link created: {reference}"
    else:
        status = "EXECUTED"
        lifecycle = "AWAITING_OUTCOME"
        message = f"{action.replace('_', ' ').title()} queued in demo mode."

    conn = db()
    conn.execute(
        "UPDATE events SET action_status=?, action_reference=?, action_payload=?, lifecycle_status=?, recovery_link_id=COALESCE(?, recovery_link_id), recovery_link_url=COALESCE(?, recovery_link_url), recovery_expires_at=COALESCE(?, recovery_expires_at) WHERE id=?",
        (status, reference, json.dumps(action_payload) if action_payload else None, lifecycle, link_id, link_url, str(expires_at) if expires_at else None, event_id),
    )
    conn.commit()
    conn.close()
    audit(event_id, action, status.lower(), message)
    return {"id": event_id, "action": action, "status": status, "lifecycle_status": lifecycle, "recovered": False, "amount": row["amount"], "reference": reference, "action_payload": action_payload, "message": message}


@app.post("/api/events/{event_id}/confirm-recovered")
def confirm_recovered(event_id: str, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    row = conn.execute("SELECT * FROM events WHERE id=? AND merchant_id=?", (event_id, merchant["id"])).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE events SET action_status='recovered', lifecycle_status='RECOVERED', recovered=1, recovered_at=?, recovered_amount=amount, outcome_source='manual_demo' WHERE id=?", (now, event_id))
    conn.commit()
    conn.close()
    audit(event_id, "recovery_confirmed", "recovered", f"₹{row['amount']:,.2f} marked recovered in demo.")
    return {"id": event_id, "status": "recovered", "recovered": True, "amount": row["amount"]}


@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: str | None = Header(default=None), x_revive_merchant_id: str | None = Header(default=None)):
    raw = await request.body()
    if RAZORPAY_WEBHOOK_SECRET and not verify_webhook_signature(raw, x_razorpay_signature or "", RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Razorpay webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    event_name = payload.get("event", "unknown")
    webhook_external_id = payload.get("id") or f"wh_{uuid.uuid4().hex[:10]}"
    internal = event_payload_to_internal(payload)
    webhook_merchant_id = x_revive_merchant_id or "m_demo"

    conn = db()
    existing = conn.execute("SELECT id FROM webhook_events WHERE source=? AND external_id=?", ("razorpay", webhook_external_id)).fetchone()
    if not existing:
        conn.execute("INSERT OR IGNORE INTO webhook_events(id,source,event_name,external_id,received_at,payload) VALUES(?,?,?,?,?,?)", (webhook_external_id, "razorpay", event_name, webhook_external_id, datetime.now(timezone.utc).isoformat(), json.dumps(payload)))
        conn.commit()
    conn.close()
    if existing:
        return {"ok": True, "deduplicated": True, "event": event_name}

    if not internal or internal.get("amount", 0) <= 0:
        audit(None, "webhook", "ignored", f"Unsupported Razorpay event {event_name}.")
        return {"ok": True, "ignored": True, "reason": "Unsupported event", "event": event_name}

    # Recovery payment-link lifecycle events. These are the strongest signal for links created by Revive.
    if event_name.startswith("payment_link."):
        link_id = internal.get("payment_link_id")
        reference_id = internal.get("payment_link_reference_id")
        conn = db()
        row = None
        if reference_id:
            row = conn.execute("SELECT id FROM events WHERE merchant_id=? AND (id=? OR recovery_link_id=? OR action_reference=?) ORDER BY created_at DESC LIMIT 1", (webhook_merchant_id, reference_id, link_id, internal.get("payment_link_url"))).fetchone()
        if not row and link_id:
            row = conn.execute("SELECT id FROM events WHERE recovery_link_id=? AND merchant_id=? ORDER BY created_at DESC LIMIT 1", (link_id, webhook_merchant_id)).fetchone()
        if not row and internal.get("payment_id"):
            row = conn.execute("SELECT id FROM events WHERE external_id=? AND merchant_id=? ORDER BY created_at DESC LIMIT 1", (internal.get("payment_id"), webhook_merchant_id)).fetchone()

        if row:
            event_id = row["id"]
            status_map = {
                "payment_link.paid": ("recovered", "RECOVERED", 1, "payment_link_webhook"),
                "payment_link.partially_paid": ("partially_recovered", "AWAITING_OUTCOME", 0, "payment_link_webhook_partial"),
                "payment_link.cancelled": ("expired", "LINK_CANCELLED", 0, "payment_link_webhook"),
                "payment_link.expired": ("expired", "LINK_EXPIRED", 0, "payment_link_webhook"),
            }
            action_status, lifecycle, recovered, source = status_map[event_name]
            recovered_at = datetime.now(timezone.utc).isoformat() if recovered else None
            recovered_amount = internal.get("recovery_paid_amount") if recovered else 0
            conn.execute("UPDATE events SET action_status=?, lifecycle_status=?, recovered=?, recovered_at=?, recovered_amount=?, outcome_source=?, recovery_link_id=COALESCE(?, recovery_link_id), recovery_link_url=COALESCE(?, recovery_link_url) WHERE id=?", (action_status, lifecycle, recovered, recovered_at, recovered_amount, source, link_id, internal.get("payment_link_url"), event_id))
            conn.commit()
            conn.close()
            audit(event_id, "payment_link_reconciled", lifecycle.lower(), f"Razorpay {event_name} updated recovery outcome.")
            return {"ok": True, "reconciled": True, "event_id": event_id, "event": event_name, "lifecycle_status": lifecycle, "recovered_amount": recovered_amount}
        conn.close()
        return {"ok": True, "reconciled": False, "event": event_name, "reason": "No matching Revive payment link"}

    if internal["event_type"] == "payment_captured":
        conn = db()
        row = conn.execute("SELECT id FROM events WHERE external_id=? AND merchant_id=? ORDER BY created_at DESC LIMIT 1", (internal.get("external_id"), webhook_merchant_id)).fetchone()
        if row:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE events SET action_status='recovered', lifecycle_status='RECOVERED', recovered=1, recovered_at=?, recovered_amount=amount, outcome_source='payment_webhook' WHERE id=?", (now, row["id"]))
            conn.commit()
            conn.close()
            audit(row["id"], "payment_reconciled", "recovered", f"Razorpay {event_name} reconciled the payment.")
            return {"ok": True, "reconciled": True, "event_id": row["id"], "event": event_name}
        conn.close()
        return {"ok": True, "reconciled": False, "event": event_name, "reason": "No matching risk event"}

    if internal["event_type"] == "payment_failed" and internal.get("external_id"):
        conn = db()
        existing_event = conn.execute("SELECT id FROM events WHERE external_id=?", (internal["external_id"],)).fetchone()
        conn.close()
        if existing_event:
            return {"ok": True, "deduplicated": True, "event": event_name, "event_id": existing_event["id"]}

    decision = hydrate(internal)
    event_id = insert_event(internal, decision, webhook_merchant_id)
    audit(event_id, "webhook", "ingested", f"Razorpay event {event_name} ingested.")
    return {"ok": True, "event_id": event_id, "recommended_action": decision.recommended_action, "recovery_probability": decision.recovery_probability, "lifecycle_status": "RECOMMENDED"}


@app.post("/api/checkout/events")
def checkout_event(event: CheckoutEventIn, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    now = datetime.now(timezone.utc).isoformat()
    if event.stage == "started":
        conn.execute(
            "INSERT OR REPLACE INTO checkout_sessions(session_id,merchant_id,customer,amount,currency,started_at,completed_at,event_id) VALUES(?,?,?,?,?,?,?)",
            (event.session_id, merchant["id"], event.customer, event.amount, event.currency, now, None, None),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "stage": "started"}

    row = conn.execute("SELECT * FROM checkout_sessions WHERE session_id=? AND merchant_id=?", (event.session_id, merchant["id"])).fetchone()
    conn.execute("UPDATE checkout_sessions SET completed_at=? WHERE session_id=?", (now, event.session_id))
    conn.commit()
    conn.close()
    return {"ok": True, "stage": "completed", "had_started": bool(row)}


@app.post("/api/checkouts/scan")
def scan_abandoned_checkouts(older_than_hours: float = 1.0, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    rows = conn.execute("SELECT * FROM checkout_sessions WHERE completed_at IS NULL AND merchant_id=?", (merchant["id"],)).fetchall()
    conn.close()
    created = []
    now = datetime.now(timezone.utc)
    for row in rows:
        started = datetime.fromisoformat(row["started_at"])
        age = (now - started).total_seconds() / 3600
        if age < older_than_hours:
            continue
        event = {
            "event_type": "checkout_abandoned",
            "customer": row["customer"],
            "amount": row["amount"],
            "currency": row["currency"],
            "external_id": f"checkout:{row['session_id']}",
            "source": "checkout_scanner",
            "previous_success_rate": 0.78,
            "customer_value": row["amount"] * 4,
            "event_age_hours": age,
            "days_since_last_success": 15,
            "prior_contacts": 0,
            "is_subscription": False,
        }
        decision = hydrate(event)
        created.append(insert_event(event, decision, merchant["id"]))
    return {"created": created, "count": len(created)}


@app.post("/api/invoices/import")
async def import_invoices(file: UploadFile = File(...), merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to parse CSV") from exc

    required = {"customer", "amount", "due_date"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain: {', '.join(sorted(required))}")

    today = datetime.now(timezone.utc).date()
    created = []
    for row in reader:
        try:
            due_date = datetime.fromisoformat(row["due_date"]).date()
            days_overdue = max(0, (today - due_date).days)
            amount = float(row["amount"])
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid invoice row: {row}") from exc
        if days_overdue <= 0:
            continue
        event = {
            "event_type": "invoice_overdue",
            "customer": row["customer"],
            "amount": amount,
            "currency": row.get("currency") or "INR",
            "external_id": row.get("invoice_id") or hashlib.sha256(f"{row['customer']}|{row['amount']}|{row['due_date']}".encode()).hexdigest()[:32],
            "source": "invoice_csv",
            "days_overdue": days_overdue,
            "previous_success_rate": float(row.get("previous_success_rate") or 0.72),
            "customer_value": float(row.get("customer_value") or amount * 4),
            "prior_contacts": int(row.get("prior_contacts") or 0),
            "days_since_last_success": int(row.get("days_since_last_success") or 10),
            "event_age_hours": days_overdue * 24,
        }
        conn = db()
        existing = conn.execute("SELECT id FROM events WHERE external_id=?", (event["external_id"],)).fetchone()
        conn.close()
        if existing:
            continue
        decision = hydrate(event)
        created.append(insert_event(event, decision, merchant["id"]))
    return {"created": created, "count": len(created)}


class RecoveryEmailIn(BaseModel):
    event_id: str
    recipient: str = Field(min_length=3)
    consent: bool = False


def _email_content(row: sqlite3.Row) -> tuple[str, str]:
    action = row["recommended_action"]
    if action == "send_payment_link" and row["recovery_link_url"]:
        subject = f"Payment link for your {row['currency']} {row['amount']:,.0f} invoice"
        body = (
            f"Hi {row['customer']},\n\n"
            f"We noticed your recent payment for {row['currency']} {row['amount']:,.0f} did not complete. "
            f"You can securely complete it here: {row['recovery_link_url']}\n\n"
            "If you have already paid, please ignore this message.\n\n"
            "Thanks"
        )
    elif action in {"retry_payment", "send_email"}:
        subject = "Your payment needs attention"
        body = (
            f"Hi {row['customer']},\n\n"
            f"We couldn't complete your {row['currency']} {row['amount']:,.0f} payment. "
            "Please try again when convenient.\n\nThanks"
        )
    else:
        subject = "Payment follow-up"
        body = f"Hi {row['customer']},\n\nPlease review your outstanding payment of {row['currency']} {row['amount']:,.0f}.\n\nThanks"
    return subject, body


@app.get("/api/events/{event_id}/email-preview")
def email_preview(event_id: str, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db(); row = conn.execute("SELECT * FROM events WHERE id=? AND merchant_id=?", (event_id, merchant["id"])).fetchone(); conn.close()
    if not row: raise HTTPException(status_code=404, detail="Event not found")
    subject, body = _email_content(row)
    return {"event_id": event_id, "recipient": row["customer_email"], "sender": merchant["sender_email"], "subject": subject, "body": body, "consent_required": True}


@app.post("/api/recovery/email")
def send_recovery_email(payload: RecoveryEmailIn, merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db(); row = conn.execute("SELECT * FROM events WHERE id=? AND merchant_id=?", (payload.event_id, merchant["id"])).fetchone()
    if not row:
        conn.close(); raise HTTPException(status_code=404, detail="Event not found")
    if not payload.consent:
        conn.close(); raise HTTPException(status_code=400, detail="Email consent is required")
    if row["contact_count"] >= 3:
        conn.close(); raise HTTPException(status_code=429, detail="Contact limit reached")
    subject, body = _email_content(row)
    result = send_email(payload.recipient, subject, body, {"from_email": merchant["sender_email"], "mocked": bool(merchant["use_demo_email"]), "smtp_host": merchant["smtp_host"], "smtp_port": merchant["smtp_port"], "smtp_username": merchant["smtp_username"], "smtp_password": merchant["smtp_password"]})
    now = datetime.now(timezone.utc).isoformat()
    if result.get("ok"):
        conn.execute("UPDATE events SET customer_email=?, consent_to_email=1, contact_count=COALESCE(contact_count,0)+1, last_contact_at=?, action_status='EXECUTED', lifecycle_status='AWAITING_OUTCOME', action_reference=? WHERE id=?", (payload.recipient, now, result.get("message_id"), payload.event_id))
        conn.commit()
    conn.close()
    audit(payload.event_id, "email_recovery", "sent" if result.get("ok") else "failed", f"Recovery email {'sent' if result.get('ok') else 'failed'} to {payload.recipient}.")
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("error", "Email send failed"))
    return {"ok": True, "event_id": payload.event_id, "recipient": payload.recipient, "subject": subject, "message_id": result.get("message_id"), "mocked": result.get("mocked", False)}


@app.post("/api/reset")
def reset_demo(merchant: sqlite3.Row = Depends(lambda authorization=Header(default=None): merchant_from_token(authorization))):
    conn = db()
    conn.execute("DELETE FROM audit_logs WHERE merchant_id=?", (merchant["id"],))
    conn.execute("DELETE FROM events WHERE merchant_id=?", (merchant["id"],))
    conn.execute("DELETE FROM checkout_sessions WHERE merchant_id=?", (merchant["id"],))
    conn.commit()
    conn.close()
    events = json.loads(SEED.read_text(encoding="utf-8"))
    for event in events:
        decision = hydrate(event)
        insert_event(event, decision, merchant["id"])
    return {"ok": True}
