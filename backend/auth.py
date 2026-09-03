from __future__ import annotations
import base64, hashlib, hmac, json, os, time, uuid
from typing import Any

SECRET = os.getenv('REVIVE_AUTH_SECRET', 'dev-only-change-me')
if SECRET == 'dev-only-change-me':
    # Fine for local demos; set REVIVE_AUTH_SECRET before deployment.
    pass
TOKEN_TTL = int(os.getenv('REVIVE_TOKEN_TTL', '86400'))

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 160_000)
    return base64.urlsafe_b64encode(salt).decode() + '$' + base64.urlsafe_b64encode(digest).decode()

def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_b64, digest_b64 = encoded.split('$', 1)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 160_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def issue_token(merchant_id: str) -> str:
    payload = {'sub': merchant_id, 'iat': int(time.time()), 'exp': int(time.time()) + TOKEN_TTL, 'jti': uuid.uuid4().hex}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')
    sig = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).digest()
    return raw + '.' + base64.urlsafe_b64encode(sig).decode().rstrip('=')

def verify_token(token: str) -> dict[str, Any] | None:
    try:
        raw, sig = token.split('.', 1)
        expected = hmac.new(SECRET.encode(), raw.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(sig + '=' * (-len(sig) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode())
        if int(payload.get('exp', 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None
