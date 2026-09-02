from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine import bounded_decision
from model import predict_probability

BASE = Path(__file__).resolve().parent
DB = BASE / "revive.db"
SEED = BASE / "seed_events.json"

app = FastAPI(title="Revive API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EventIn(BaseModel):
    event_type: str
    customer: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    failure_reason: str | None = None
    days_overdue: int = 0
    previous_success_rate: float = Field(default=0.7, ge=0, le=1)
    days_since_last_success: int = 30
    prior_contacts: int = Field(default=0, ge=0)
    customer_value: float = 0
    event_age_hours: float = 1
    is_subscription: bool = False


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


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
    conn.commit()
    conn.close()


def hydrate(event: dict[str, Any]):
    p = predict_probability(event)
    decision = bounded_decision(event, p)
    return p, decision


def insert_event(event: dict[str, Any], p: float, decision):
    event_id = event.get("id") or f"evt_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = db()
    conn.execute(
        """INSERT OR REPLACE INTO events
        (id,event_type,customer,amount,currency,status,recovery_probability,risk_score,recommended_action,action_reason,risk_reason,delay_hours,created_at,action_status,recovered)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            event_id,
            event["event_type"],
            event["customer"],
            event["amount"],
            event.get("currency", "INR"),
            "at_risk",
            p,
            decision.risk_score,
            decision.recommended_action,
            decision.action_reason,
            decision.risk_reason,
            decision.delay_hours,
            now,
            "pending",
            0,
        ),
    )
    conn.commit()
    conn.close()
    return event_id


@app.on_event("startup")
def startup():
    init_db()
    if not DB.exists():
        return
    conn = db()
    count = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    conn.close()
    if count == 0 and SEED.exists():
        events = json.loads(SEED.read_text(encoding="utf-8"))
        for event in events:
            p, decision = hydrate(event)
            insert_event(event, p, decision)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "revive-api"}


@app.get("/api/dashboard")
def dashboard():
    conn = db()
    rows = conn.execute("SELECT * FROM events ORDER BY created_at DESC").fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    at_risk = sum(r["amount"] for r in items if not r["recovered"])
    recovered = sum(r["amount"] for r in items if r["recovered"])
    expected = sum(r["amount"] * r["recovery_probability"] for r in items if not r["recovered"])
    return {
        "metrics": {
            "revenue_at_risk": round(at_risk, 2),
            "expected_recovery": round(expected, 2),
            "recovered": round(recovered, 2),
            "events": len(items),
        },
        "events": items,
    }


@app.post("/api/events")
def create_event(event: EventIn):
    payload = event.model_dump()
    if not payload["customer_value"]:
        payload["customer_value"] = payload["amount"]
    p, decision = hydrate(payload)
    event_id = insert_event(payload, p, decision)
    return {"id": event_id, **payload, **decision.__dict__}


@app.post("/api/events/{event_id}/execute")
def execute_event(event_id: str):
    conn = db()
    row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Event not found")

    action = row["recommended_action"]
    if action == "do_nothing":
        status = "stopped"
        recovered = 0
        conn.execute("UPDATE events SET action_status=? WHERE id=?", (status, event_id))
    elif action == "escalate":
        status = "escalated"
        recovered = 0
        conn.execute("UPDATE events SET action_status=? WHERE id=?", (status, event_id))
    else:
        status = "recovered"
        recovered = 1
        conn.execute("UPDATE events SET action_status=?, recovered=? WHERE id=?", (status, recovered, event_id))
    conn.commit()
    conn.close()

    return {
        "id": event_id,
        "action": action,
        "status": status,
        "recovered": bool(recovered),
        "amount": row["amount"],
        "message": f"{action.replace('_', ' ').title()} executed in demo mode.",
    }


@app.post("/api/reset")
def reset_demo():
    conn = db()
    conn.execute("DELETE FROM events")
    conn.commit()
    conn.close()
    events = json.loads(SEED.read_text(encoding="utf-8"))
    for event in events:
        p, decision = hydrate(event)
        insert_event(event, p, decision)
    return {"ok": True}
