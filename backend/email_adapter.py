from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

import requests


RESEND_API_URL = "https://api.resend.com/emails"


def _send_resend(to_email: str, subject: str, body: str, sender: dict[str, Any]) -> dict[str, Any]:
    api_key = (sender.get("resend_api_key") or "").strip()
    from_email = (sender.get("from_email") or "").strip()
    if not api_key or not from_email:
        return {"ok": False, "mocked": False, "provider": "resend", "error": "Resend API key and sender email are required"}

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": "<div style=\"font-family:Arial,sans-serif;white-space:pre-wrap\">" + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>") + "</div>",
        "text": body,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=20)
        data = response.json() if response.content else {}
        if not response.ok:
            message = data.get("message") or data.get("error") or f"Resend API returned HTTP {response.status_code}"
            return {"ok": False, "mocked": False, "provider": "resend", "from_email": from_email, "error": message, "status_code": response.status_code}
        return {
            "ok": True,
            "mocked": False,
            "provider": "resend",
            "from_email": from_email,
            "message_id": data.get("id"),
        }
    except requests.RequestException as exc:
        return {"ok": False, "mocked": False, "provider": "resend", "from_email": from_email, "error": f"Resend network error: {exc}"}
    except ValueError as exc:
        return {"ok": False, "mocked": False, "provider": "resend", "from_email": from_email, "error": f"Invalid Resend response: {exc}"}


def send_email(to_email: str, subject: str, body: str, sender: dict[str, Any] | None = None) -> dict[str, Any]:
    sender = sender or {}
    provider = (sender.get("provider") or "").strip().lower()
    mocked = bool(sender.get("mocked", False)) or provider == "demo"

    if mocked:
        return {
            "ok": True,
            "mocked": True,
            "provider": "demo",
            "from_email": sender.get("from_email") or "demo@revive.local",
            "message_id": f"demo-email-{abs(hash((to_email, subject, body))) % 10_000_000}",
        }

    if provider == "resend":
        return _send_resend(to_email, subject, body, sender)

    # Backward-compatible local SMTP path for development/self-hosted deployments.
    host = sender.get("smtp_host") or ""
    port = int(sender.get("smtp_port") or 587)
    username = sender.get("smtp_username") or ""
    password = sender.get("smtp_password") or ""
    from_email = sender.get("from_email") or username
    if not host or not username or not password or not from_email:
        return {"ok": False, "mocked": False, "provider": "smtp", "error": "SMTP sender configuration is incomplete"}

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return {"ok": True, "mocked": False, "provider": "smtp", "from_email": from_email, "message_id": msg.get("Message-ID")}
    except Exception as exc:
        return {"ok": False, "mocked": False, "provider": "smtp", "from_email": from_email, "error": str(exc)}
