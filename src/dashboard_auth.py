import base64
import hashlib
import hmac
import json
from typing import Optional

from fastapi import Request

from src.utils.logging import get_logger
from src.utils.settings import get_settings


logger = get_logger('dashboard_auth')
APP_SETTINGS = get_settings()
SESSION_SECRET = APP_SETTINGS.session_secret or 'dashboard-dev-session-secret'
if not APP_SETTINGS.session_secret:
    logger.warning('SESSION_SECRET missing; using local development fallback secret for demo auth.')

DASHBOARD_SESSION_COOKIE = 'dashboard_session'


def sign_dashboard_session(payload: dict) -> str:
    raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    encoded = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    signature = hmac.new(SESSION_SECRET.encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).hexdigest()
    return f'{encoded}.{signature}'


def read_dashboard_session(raw_value: Optional[str]) -> Optional[dict]:
    if not raw_value or '.' not in raw_value:
        return None
    encoded, signature = raw_value.rsplit('.', 1)
    expected = hmac.new(SESSION_SECRET.encode('utf-8'), encoded.encode('ascii'), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    padded = encoded
    while len(padded) & 3:
        padded += '='
    try:
        decoded = base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8')
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(payload, dict) and payload.get('dashboard_authenticated'):
        return payload
    return None


def is_authenticated(request: Request) -> bool:
    return read_dashboard_session(request.cookies.get(DASHBOARD_SESSION_COOKIE)) is not None
