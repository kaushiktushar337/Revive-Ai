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

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import APP_ENV, CORS_ORIGINS, RAZORPAY_KEY_ID, RAZORPAY_WEBHOOK_SECRET
from engine import bounded_decision
from model import predict_probability
from razorpay_adapter import create_payment_link, test_connection, verify_webhook_signature

BASE = Path(__file__).resolve().parent
DB = BASE / "revive.db"
SEED = BASE / "seed_events.json"

app = FastAPI(title="Revive API", version="0.2.0", description="AI revenue recovery prototype API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            recovered INTEGER NOT NULL DEFAULT 0
        )"""
    )
    ensure_column(conn, "events", "external_id", "TEXT")
    ensure_column(conn, "events", "source", "TEXT DEFAULT 'simulator'")
    ensure_column(conn, "events", "action_reference", "TEXT")
    ensure_column(conn, "events", "action_payload", "TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_events_external_id ON events(external_id) WHERE external_id IS NOT NULL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
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
            customer TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            event_id TEXT
        )"""
    )
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
    conn.commit()
    conn.close()


def audit(event_id: str | None, action: str, status: str, detail: str):
    conn = db()
    conn.execute(
        "INSERT INTO audit_logs(id,event_id,action,status,detail,created_at) VALUES(?,?,?,?,?,?)",
        (f"log_{uuid.uuid4().hex[:10]}", event_id, action, status, detail, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def hydrate(event: dict[str, Any]):
    p = predict_probability(event)
    return bounded_decision(event, p)


def insert_event(event: dict[str, Any], decision):
    event_id = event.get("id") or f"evt_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = db()
    conn.execute(
        """INSERT OR REPLACE INTO events
        (id,event_type,customer,amount,currency,status,recovery_probability,risk_score,recommended_action,action_reason,risk_reason,delay_hours,created_at,action_status,recovered,external_id,source,action_reference,action_payload)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
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
        ),
    )
    conn.commit()
    conn.close()
    audit(event_id, "decision", "recommended", f"{decision.recommended_action}: {decision.action_reason}")
    return event_id


def event_payload_to_internal(payload: dict[str, Any], source: str = "razorpay") -> dict[str, Any] | None:
    event_name = payload.get("event", "")
    entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
    if not entity:
        entity = (((payload.get("payload") or {}).get("payment_link") or {}).get("entity") or {})

    amount = float(entity.get("amount") or 0) / 100
    customer = entity.get("email") or entity.get("contact") or "Razorpay Customer"
    external_id = entity.get("id")
    common = {
        "customer": customer,
        "amount": amount,
        "currency": entity.get("currency") or "INR",
        "external_id": external_id,
        "source": source,
        "previous_success_rate": 0.75,
        "customer_value": amount * 4,
        "event_age_hours": 0.2,
        "days_since_last_success": 7,
        "prior_contacts": 0,
        "is_subscription": bool(entity.get("subscription_id")),
    }
    if event_name in {"payment.failed", "order.payment_failed"}:
        return {
            **common,
            "event_type": "payment_failed",
            "failure_reason": entity.get("error_reason") or entity.get("error_description") or "temporary_decline",
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
def dashboard():
    conn = db()
    rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
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
        },
        "events": items,
    }


@app.get("/api/audit")
def get_audit(limit: int = 100):
    conn = db()
    rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (min(limit, 500),)).fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}


@app.post("/api/events")
def create_event(event: EventIn):
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
    event_id = insert_event(payload, decision)
    return {"id": event_id, "deduplicated": False, **payload, **decision.__dict__}


@app.post("/api/events/{event_id}/execute")
def execute_event(event_id: str):
    conn = db()
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")

    action = row["recommended_action"]
    action_payload: dict[str, Any] = {}
    status = "stopped"
    recovered = 0
    reference = None

    if action == "do_nothing":
        status = "stopped"
        message = "Agent stopped the workflow because the expected benefit did not justify intervention."
    elif action == "escalate":
        status = "escalated"
        message = "Agent escalated the case because the bounded policy requires human approval."
    elif action == "send_payment_link":
        result = create_payment_link(row["amount"], row["customer"], f"Revive recovery for {row['customer']}", event_id)
        reference = result.get("short_url") or result.get("id")
        action_payload = result
        status = "executed"
        message = f"Recovery payment link created: {reference}"
    else:
        status = "recovery_triggered"
        message = f"{action.replace('_', ' ').title()} queued in demo mode."

    # Demo semantics: only payment_link execution immediately counts as recovered when the user confirms it later.
    conn = db()
    conn.execute(
        "UPDATE events SET action_status=?, action_reference=?, action_payload=? WHERE id=?",
        (status, reference, json.dumps(action_payload) if action_payload else None, event_id),
    )
    conn.commit()
    conn.close()
    audit(event_id, action, status, message)
    return {
        "id": event_id,
        "action": action,
        "status": status,
        "recovered": bool(recovered),
        "amount": row["amount"],
        "reference": reference,
        "action_payload": action_payload,
        "message": message,
    }


@app.post("/api/events/{event_id}/confirm-recovered")
def confirm_recovered(event_id: str):
    conn = db()
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")
    conn.execute("UPDATE events SET action_status='recovered', recovered=1 WHERE id=?", (event_id,))
    conn.commit()
    conn.close()
    audit(event_id, "recovery_confirmed", "recovered", f"₹{row['amount']:,.2f} marked recovered in demo.")
    return {"id": event_id, "status": "recovered", "recovered": True, "amount": row["amount"]}


@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: str | None = Header(default=None)):
    raw = await request.body()
    if RAZORPAY_WEBHOOK_SECRET and not verify_webhook_signature(raw, x_razorpay_signature or "", RAZORPAY_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Razorpay webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    event_name = payload.get("event", "unknown")
    payload_entity = (((payload.get("payload") or {}).get("payment") or {}).get("entity") or {})
    payment_external_id = payload_entity.get("id")
    webhook_external_id = payload.get("id") or f"wh_{uuid.uuid4().hex[:10]}"

    conn = db()
    existing = conn.execute("SELECT id FROM webhook_events WHERE source=? AND external_id=?", ("razorpay", webhook_external_id)).fetchone()
    if not existing:
        conn.execute(
            "INSERT OR IGNORE INTO webhook_events(id,source,event_name,external_id,received_at,payload) VALUES(?,?,?,?,?,?)",
            (webhook_external_id, "razorpay", event_name, webhook_external_id, datetime.now(timezone.utc).isoformat(), json.dumps(payload)),
        )
        conn.commit()
    conn.close()

    if existing:
        return {"ok": True, "deduplicated": True, "event": event_name, "external_id": payment_external_id}

    internal = event_payload_to_internal(payload)
    if not internal or internal.get("amount", 0) <= 0:
        audit(None, "webhook", "ignored", f"Unsupported Razorpay event {event_name}.")
        return {"ok": True, "ignored": True, "reason": "Unsupported event", "event": event_name}

    # Captured payments are reconciliation events, not new revenue-risk opportunities.
    if internal["event_type"] == "payment_captured":
        conn = db()
        row = conn.execute("SELECT id FROM events WHERE external_id=? ORDER BY created_at DESC LIMIT 1", (internal.get("external_id"),)).fetchone()
        if row:
            conn.execute("UPDATE events SET action_status='recovered', recovered=1 WHERE id=?", (row["id"],))
            conn.commit()
            conn.close()
            audit(row["id"], "payment_reconciled", "recovered", f"Razorpay {event_name} reconciled the payment.")
            return {"ok": True, "reconciled": True, "event_id": row["id"], "event": event_name}
        conn.close()
        return {"ok": True, "reconciled": False, "event": event_name, "reason": "No matching risk event"}

    decision = hydrate(internal)
    event_id = insert_event(internal, decision)
    audit(event_id, "webhook", "ingested", f"Razorpay event {event_name} ingested.")
    return {"ok": True, "event_id": event_id, "recommended_action": decision.recommended_action, "recovery_probability": decision.recovery_probability}


@app.post("/api/checkout/events")
def checkout_event(event: CheckoutEventIn):
    conn = db()
    now = datetime.now(timezone.utc).isoformat()
    if event.stage == "started":
        conn.execute(
            "INSERT OR REPLACE INTO checkout_sessions(session_id,customer,amount,currency,started_at,completed_at,event_id) VALUES(?,?,?,?,?,?,?)",
            (event.session_id, event.customer, event.amount, event.currency, now, None, None),
        )
        conn.commit()
        conn.close()
        return {"ok": True, "stage": "started"}

    row = conn.execute("SELECT * FROM checkout_sessions WHERE session_id=?", (event.session_id,)).fetchone()
    conn.execute("UPDATE checkout_sessions SET completed_at=? WHERE session_id=?", (now, event.session_id))
    conn.commit()
    conn.close()
    return {"ok": True, "stage": "completed", "had_started": bool(row)}


@app.post("/api/checkouts/scan")
def scan_abandoned_checkouts(older_than_hours: float = 1.0):
    conn = db()
    rows = conn.execute("SELECT * FROM checkout_sessions WHERE completed_at IS NULL").fetchall()
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
        created.append(insert_event(event, decision))
    return {"created": created, "count": len(created)}


@app.post("/api/invoices/import")
async def import_invoices(file: UploadFile = File(...)):
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
        created.append(insert_event(event, decision))
    return {"created": created, "count": len(created)}


@app.post("/api/reset")
def reset_demo():
    conn = db()
    conn.execute("DELETE FROM audit_logs")
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM checkout_sessions")
    conn.commit()
    conn.close()
    events = json.loads(SEED.read_text(encoding="utf-8"))
    for event in events:
        decision = hydrate(event)
        insert_event(event, decision)
    return {"ok": True}
