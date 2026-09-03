from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

import requests

from config import MOCK_EXTERNAL_ACTIONS

TEST_ACCOUNTS_URL = "https://uat-accounts.payu.in"
LIVE_ACCOUNTS_URL = "https://accounts.payu.in"
TEST_API_URL = "https://uatoneapi.payu.in"
LIVE_API_URL = "https://oneapi.payu.in"


def _base(mode: str) -> str:
    return LIVE_API_URL if mode == "live" else TEST_API_URL


def _accounts_base(mode: str) -> str:
    return LIVE_ACCOUNTS_URL if mode == "live" else TEST_ACCOUNTS_URL


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    return requests.request(method, url, timeout=20, **kwargs)


def get_access_token(client_id: str, client_secret: str, mode: str = "test", scope: str = "create_payment_links read_payment_links update_payment_links") -> str:
    if not client_id or not client_secret:
        raise ValueError("PayU Client ID and Client Secret are required")
    response = _request(
        "POST",
        f"{_accounts_base(mode)}/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": scope,
        },
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError(f"PayU token response did not contain access_token: {payload}")
    return token


def test_connection(merchant_id: str, client_id: str, client_secret: str, mode: str = "test") -> dict[str, Any]:
    if not merchant_id or not client_id or not client_secret:
        return {"configured": False, "ok": False, "mode": mode, "message": "PayU merchant ID, Client ID and Client Secret are required."}
    try:
        token = get_access_token(client_id, client_secret, mode, "read_payment_links")
        return {"configured": True, "ok": bool(token), "mode": mode, "merchant_id": merchant_id, "message": "PayU API credentials verified."}
    except Exception as exc:
        return {"configured": True, "ok": False, "mode": mode, "merchant_id": merchant_id, "message": f"PayU connection failed: {exc}"}


def _alnum(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value)


def create_payment_link(
    amount_inr: float,
    customer: str,
    description: str,
    reference_id: str,
    merchant_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    mode: str = "test",
    customer_email: str | None = None,
) -> dict[str, Any]:
    """Create a PayU payment link using the documented OAuth Payment Links API."""
    if MOCK_EXTERNAL_ACTIONS or not merchant_id or not client_id or not client_secret:
        return {
            "mode": "demo",
            "id": f"payu_demo_{reference_id}",
            "invoiceNumber": f"REV{_alnum(reference_id)[:18]}",
            "paymentLink": f"http://localhost:5500/pay/{reference_id}",
            "reference_id": reference_id,
            "status": "created",
        }

    token = get_access_token(client_id, client_secret, mode, "create_payment_links")
    invoice_number = f"REV{_alnum(reference_id)[:18]}"
    payload = {
        "invoiceNumber": invoice_number,
        "isAmountFilledByCustomer": False,
        "subAmount": int(round(amount_inr)),
        "description": description,
        "source": "API",
        "currency": "INR",
        "isPartialPaymentAllowed": False,
        "customer": {"name": customer, "email": customer_email or ""},
        "viaEmail": False,
        "viaSms": False,
        "viaWhatsapp": False,
        "udf": {"udf1": reference_id[:255]},
    }
    response = _request(
        "POST",
        f"{_base(mode)}/payment-links/",
        headers={
            "merchantId": merchant_id,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        json=payload,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("status") not in (0, "0"):
        raise RuntimeError(result.get("message") or f"PayU payment link creation failed: {result}")
    link = result.get("result") or {}
    return {**result, **link, "mode": mode, "reference_id": reference_id}


def fetch_payment_link(invoice_number: str, merchant_id: str, client_id: str, client_secret: str, mode: str = "test") -> dict[str, Any]:
    token = get_access_token(client_id, client_secret, mode, "read_payment_links")
    response = _request(
        "GET",
        f"{_base(mode)}/payment-links/{invoice_number}",
        headers={"mid": merchant_id, "Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("result"):
        return {**payload, **payload["result"]}
    return payload


def verify_response_hash(data: dict[str, Any], salt: str) -> bool:
    """Verify PayU response hash using documented reverse-hash logic."""
    received = (data.get("hash") or "").strip().lower()
    if not received or not salt:
        return False
    status = data.get("status", "")
    udf1 = data.get("udf1", "")
    udf2 = data.get("udf2", "")
    udf3 = data.get("udf3", "")
    udf4 = data.get("udf4", "")
    udf5 = data.get("udf5", "")
    email = data.get("email", "")
    firstname = data.get("firstname", "")
    productinfo = data.get("productinfo", "")
    amount = data.get("amount", "")
    txnid = data.get("txnid", "")
    key = data.get("key", "")
    value = "|".join([salt, status, "", "", "", "", "", udf5, udf4, udf3, udf2, udf1, email, firstname, productinfo, amount, txnid, key])
    expected = hashlib.sha512(value.encode("utf-8")).hexdigest().lower()
    return hmac.compare_digest(expected, received)
