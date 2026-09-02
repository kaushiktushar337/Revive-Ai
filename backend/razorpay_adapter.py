from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any

import requests

from config import (
    MOCK_EXTERNAL_ACTIONS,
    RAZORPAY_BASE_URL,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
)


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _auth_header() -> str:
    token = f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


def create_payment_link(amount_inr: float, customer: str, description: str, reference_id: str) -> dict[str, Any]:
    """Create a Razorpay payment link, or return a deterministic demo link in mock mode."""
    if MOCK_EXTERNAL_ACTIONS or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return {
            "mode": "demo",
            "short_url": f"http://localhost:5500/pay/{reference_id}",
            "reference_id": reference_id,
        }

    payload = {
        "amount": int(round(amount_inr * 100)),
        "currency": "INR",
        "description": description,
        "reference_id": reference_id[:40],
        "customer": {"name": customer},
        "notify": {"sms": False, "email": False},
        "reminder_enable": True,
    }
    response = requests.post(
        f"{RAZORPAY_BASE_URL}/payment_links",
        json=payload,
        headers={"Authorization": _auth_header(), "Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
