from __future__ import annotations
import smtplib
from email.message import EmailMessage
from typing import Any


def send_email(to_email: str, subject: str, body: str, sender: dict[str, Any] | None = None) -> dict[str, Any]:
    sender = sender or {}
    mocked = bool(sender.get('mocked', True))
    if mocked:
        return {
            'ok': True,
            'mocked': True,
            'provider': 'demo',
            'from_email': sender.get('from_email') or 'demo@revive.local',
            'message_id': f"demo-email-{abs(hash((to_email, subject, body))) % 10_000_000}",
        }

    host = sender.get('smtp_host') or ''
    port = int(sender.get('smtp_port') or 587)
    username = sender.get('smtp_username') or ''
    password = sender.get('smtp_password') or ''
    from_email = sender.get('from_email') or username
    if not host or not username or not password or not from_email:
        return {'ok': False, 'mocked': False, 'provider': 'smtp', 'error': 'SMTP sender configuration is incomplete'}

    msg = EmailMessage()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return {'ok': True, 'mocked': False, 'provider': 'smtp', 'from_email': from_email, 'message_id': msg.get('Message-ID')}
    except Exception as exc:
        return {'ok': False, 'mocked': False, 'provider': 'smtp', 'from_email': from_email, 'error': str(exc)}
