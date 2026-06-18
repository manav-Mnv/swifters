from __future__ import annotations

from datetime import datetime, timedelta

from flask import session

from .config import Config


FAILED_LOGINS: dict[str, dict[str, datetime | int]] = {}


def get_client_key(ip_address: str) -> str:
    return ip_address or "unknown"


def is_locked_out(ip_address: str) -> bool:
    entry = FAILED_LOGINS.get(get_client_key(ip_address))
    if not entry:
        return False
    locked_until = entry.get("locked_until")
    if locked_until and isinstance(locked_until, datetime):
        if locked_until > datetime.utcnow():
            return True
        FAILED_LOGINS.pop(get_client_key(ip_address), None)
    return False


def record_failed_login(ip_address: str) -> None:
    key = get_client_key(ip_address)
    entry = FAILED_LOGINS.setdefault(key, {"count": 0})
    entry["count"] = int(entry.get("count", 0)) + 1
    if entry["count"] >= Config.MAX_LOGIN_ATTEMPTS:
        entry["locked_until"] = datetime.utcnow() + timedelta(minutes=Config.LOCKOUT_MINUTES)


def clear_failed_login(ip_address: str) -> None:
    FAILED_LOGINS.pop(get_client_key(ip_address), None)


def admin_logged_in() -> bool:
    return bool(session.get("is_admin"))

