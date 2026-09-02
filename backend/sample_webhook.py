"""Send a locally signed Razorpay-style test webhook to a running Revive API."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/api/webhooks/razorpay")
    parser.add_argument("--secret", default="dev_secret")
    parser.add_argument("--event", choices=["payment.failed", "payment.captured"], default="payment.failed")
    parser.add_argument("--payment-id", default="pay_demo_001")
    args = parser.parse_args()

    entity = {
        "id": args.payment_id,
        "amount": 1850000,
        "currency": "INR",
        "email": "rahul@example.com",
        "contact": "+919999999999",
        "error_reason": "insufficient_funds",
        "subscription_id": "sub_demo_001",
    }
    payload = {"id": f"wh_demo_{args.event.replace(".", "_")}", "event": args.event, "payload": {"payment": {"entity": entity}}}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(args.secret.encode(), raw, hashlib.sha256).hexdigest()
    response = requests.post(args.url, data=raw, headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature}, timeout=10)
    print(response.status_code)
    print(response.text)


if __name__ == "__main__":
    main()
