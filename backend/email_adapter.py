from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

import requests

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def _html(body: str) -> str:
    return "<div style=\"font-family:Arial,sans-serif;white-space:pre-wrap\">" + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>") + "</div>"


def _send_brevo(to_email: str, subject: str, body: str, sender: dict[str, Any]) -> dict[str, Any]:
    api_key = (sender.get("brevo_api_key") or "").strip()
    from_email = (sender.get("from_email") or "").strip()
    from_name = (sender.get("from_name") or "ReviveAI").strip()
    if not api_key or not from_email:
        return {"ok": False, "mocked": False, "provider": "brevo", "error": "Brevo API key and verified sender email are required"}
    payload = {
        "sender": {"email": from_email, "name": from_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": _html(body),
        "textContent": body,
    }
    try:
        response = requests.post(BREVO_API_URL, json=payload, headers={"api-key": api_key, "Content-Type": "application/json", "accept": "application/json"}, timeout=20)
        try:
            data = response.json() if response.content else {}
        except ValueError:
            data = {}
        if not response.ok:
            message = data.get("message") or data.get("code") or f"Brevo API returned HTTP {response.status_code}"
            return {"ok": False, "mocked": False, "provider": "brevo", "from_email": from_email, "error": message, "status_code": response.status_code}
        return {"ok": True, "mocked": False, "provider": "brevo", "from_email": from_email, "message_id": data.get("messageId")}
    except requests.RequestException as exc:
        return {"ok": False, "mocked": False, "provider": "brevo", "from_email": from_email, "error": f"Brevo network error: {exc}"}


def send_email(to_email: str, subject: str, body: str, sender: dict[str, Any] | None = None) -> dict[str, Any]:
    sender = sender or {}
    provider = (sender.get("provider") or "").strip().lower()
    if bool(sender.get("mocked", False)) or provider == "demo":
        return {"ok": True, "mocked": True, "provider": "demo", "from_email": sender.get("from_email") or "demo@revive.local", "message_id": f"demo-email-{abs(hash((to_email, subject, body))) % 10_000_000}"}
    if provider == "brevo":
        return _send_brevo(to_email, subject, body, sender)

    # Optional SMTP fallback for self-hosted deployments.
    host = sender.get("smtp_host") or ""
    port = int(sender.get("smtp_port") or 587)
    username = sender.get("smtp_username") or ""
    password = sender.get("smtp_password") or ""
    from_email = sender.get("from_email") or username
    if not host or not username or not password or not from_email:
        return {"ok": False, "mocked": False, "provider": "smtp", "error": "SMTP sender configuration is incomplete"}
    msg = EmailMessage(); msg["From"] = from_email; msg["To"] = to_email; msg["Subject"] = subject; msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls(); server.login(username, password); server.send_message(msg)
        return {"ok": True, "mocked": False, "provider": "smtp", "from_email": from_email, "message_id": msg.get("Message-ID")}
    except Exception as exc:
        return {"ok": False, "mocked": False, "provider": "smtp", "from_email": from_email, "error": str(exc)}
