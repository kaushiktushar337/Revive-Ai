from __future__ import annotations

import json
from pathlib import Path

from model import train_model

train_model()

seed_events = [
    {
        "id": "evt_1001",
        "event_type": "payment_failed",
        "customer": "Rahul Sharma",
        "amount": 18500,
        "currency": "INR",
        "failure_reason": "insufficient_funds",
        "previous_success_rate": 0.86,
        "days_since_last_success": 27,
        "prior_contacts": 0,
        "customer_value": 78000,
        "event_age_hours": 2,
        "is_subscription": True,
    },
    {
        "id": "evt_1002",
        "event_type": "checkout_abandoned",
        "customer": "Priya Enterprises",
        "amount": 42000,
        "currency": "INR",
        "previous_success_rate": 0.92,
        "days_since_last_success": 14,
        "prior_contacts": 0,
        "customer_value": 125000,
        "event_age_hours": 3,
        "is_subscription": False,
    },
    {
        "id": "evt_1003",
        "event_type": "invoice_overdue",
        "customer": "ABC Foods Pvt Ltd",
        "amount": 120000,
        "currency": "INR",
        "days_overdue": 18,
        "previous_success_rate": 0.67,
        "days_since_last_success": 44,
        "prior_contacts": 2,
        "customer_value": 410000,
        "event_age_hours": 432,
        "is_subscription": False,
    },
    {
        "id": "evt_1004",
        "event_type": "payment_failed",
        "customer": "Neha Kapoor",
        "amount": 2999,
        "currency": "INR",
        "failure_reason": "expired_card",
        "previous_success_rate": 0.79,
        "days_since_last_success": 31,
        "prior_contacts": 0,
        "customer_value": 25000,
        "event_age_hours": 1,
        "is_subscription": True,
    },
]

out = Path(__file__).with_name("seed_events.json")
out.write_text(json.dumps(seed_events, indent=2), encoding="utf-8")
print(f"Seeded {len(seed_events)} demo events into {out}")
