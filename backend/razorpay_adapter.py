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


def _request(method: str, path: str, **kwargs: Any) -> requests.Response:
    return requests.request(
        method,
        f"{RAZORPAY_BASE_URL.rstrip('/')}/{path.lstrip('/')}",
        headers={
            "Authorization": _auth_header(),
            "Content-Type": "application/json",
            **kwargs.pop("headers", {}),
        },
        timeout=15,
        **kwargs,
    )


def test_connection() -> dict[str, Any]:
    """Verify Razorpay test credentials using a read-only API call."""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return {"configured": False, "ok": False, "mode": "demo", "message": "Razorpay credentials are not configured."}
    response = _request("GET", "/payments", params={"count": 1})
    if response.ok:
        return {"configured": True, "ok": True, "mode": "live-test-api", "status_code": response.status_code}
    try:
        detail = response.json()
    except ValueError:
        detail = {"error": response.text[:300]}
    return {"configured": True, "ok": False, "mode": "live-test-api", "status_code": response.status_code, "detail": detail}


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
    response = _request("POST", "/payment_links", json=payload)
    response.raise_for_status()
    return response.json()
