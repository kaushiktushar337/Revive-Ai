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


def _auth_header(key_id: str | None = None, key_secret: str | None = None) -> str:
    key_id = key_id if key_id is not None else RAZORPAY_KEY_ID
    key_secret = key_secret if key_secret is not None else RAZORPAY_KEY_SECRET
    token = f"{key_id}:{key_secret}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


def _request(method: str, path: str, key_id: str | None = None, key_secret: str | None = None, **kwargs: Any) -> requests.Response:
    return requests.request(
        method,
        f"{RAZORPAY_BASE_URL.rstrip('/')}/{path.lstrip('/')}",
        headers={
            "Authorization": _auth_header(key_id, key_secret),
            "Content-Type": "application/json",
            **kwargs.pop("headers", {}),
        },
        timeout=15,
        **kwargs,
    )


def test_connection(key_id: str | None = None, key_secret: str | None = None, mode: str = "test") -> dict[str, Any]:
    """Verify Razorpay test credentials using a read-only API call."""
    key_id = key_id if key_id is not None else RAZORPAY_KEY_ID
    key_secret = key_secret if key_secret is not None else RAZORPAY_KEY_SECRET
    if not key_id or not key_secret:
        return {"configured": False, "ok": False, "mode": mode, "message": "Razorpay credentials are not configured."}
    response = _request("GET", "/payments", key_id=key_id, key_secret=key_secret, params={"count": 1})
    if response.ok:
        return {"configured": True, "ok": True, "mode": mode, "status_code": response.status_code}
    try:
        detail = response.json()
    except ValueError:
        detail = {"error": response.text[:300]}
    return {"configured": True, "ok": False, "mode": mode, "status_code": response.status_code, "detail": detail}


def create_payment_link(amount_inr: float, customer: str, description: str, reference_id: str, key_id: str | None = None, key_secret: str | None = None) -> dict[str, Any]:
    """Create a Razorpay payment link, or return a deterministic demo link in mock mode."""
    key_id = key_id if key_id is not None else RAZORPAY_KEY_ID
    key_secret = key_secret if key_secret is not None else RAZORPAY_KEY_SECRET
    if MOCK_EXTERNAL_ACTIONS or not key_id or not key_secret:
        return {
            "mode": "demo",
            "id": f"plink_demo_{reference_id}",
            "short_url": f"http://localhost:5500/pay/{reference_id}",
            "reference_id": reference_id,
            "status": "created",
        }

    payload = {
        "amount": int(round(amount_inr * 100)),
        "currency": "INR",
        "description": description,
        "reference_id": reference_id[:40],
        "customer": {"name": customer},
        "notify": {"sms": False, "email": False, "whatsapp": False},
        "reminder_enable": True,
        "notes": {"revive_event_id": reference_id[:40]},
    }
    response = _request("POST", "/payment_links", key_id=key_id, key_secret=key_secret, json=payload)
    response.raise_for_status()
    return response.json()


def fetch_payment_link(link_id: str, key_id: str | None = None, key_secret: str | None = None) -> dict[str, Any]:
    key_id = key_id if key_id is not None else RAZORPAY_KEY_ID
    key_secret = key_secret if key_secret is not None else RAZORPAY_KEY_SECRET
    if not key_id or not key_secret:
        raise ValueError("Razorpay credentials are not configured")
    response = _request("GET", f"/payment_links/{link_id}", key_id=key_id, key_secret=key_secret)
    response.raise_for_status()
    return response.json()
