import hmac
import hashlib
import time
from urllib.parse import parse_qsl
from typing import Optional, Dict, Any


def _build_data_check_string(params: Dict[str, str]) -> str:
    # Exclude 'hash', sort keys, join as key=value with newlines
    items = [(k, v) for k, v in params.items() if k != 'hash']
    items.sort(key=lambda x: x[0])
    return '\n'.join([f"{k}={v}" for k, v in items])


def verify_webapp_init_data(init_data: str, bot_token: str, max_age: int = 300) -> Optional[Dict[str, Any]]:
    """Verify Telegram WebApp initData per docs.
    Returns parsed dict on success, else None.
    max_age: seconds since auth_date allowed.
    """
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.get('hash')
        if not received_hash:
            return None
        # Build secret key: HMAC_SHA256 of bot_token with key 'WebAppData'
        secret_key = hmac.new(key=b"WebAppData", msg=bot_token.encode('utf-8'), digestmod=hashlib.sha256).digest()
        data_check_string = _build_data_check_string(pairs)
        computed_hash = hmac.new(key=secret_key, msg=data_check_string.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()
        if computed_hash != received_hash:
            return None
        # Age check
        auth_date = int(pairs.get('auth_date', '0') or '0')
        if auth_date and (time.time() - auth_date) > max_age:
            return None
        # Parse user JSON if present
        import json
        user_raw = pairs.get('user')
        user = json.loads(user_raw) if user_raw else None
        return {
            'ok': True,
            'user': user,
            'query': pairs,
        }
    except (ValueError, RuntimeError):
        return None
