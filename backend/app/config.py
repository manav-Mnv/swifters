from __future__ import annotations

import os
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


class Config:
    BASE_DIR = Path(__file__).resolve().parents[1]
    DATA_DIR = BASE_DIR / "data"
    DATABASE_PATH = DATA_DIR / "attendance.db"
    FACES_DIR = DATA_DIR / "registered_faces"
    ADMIN_PASSWORD = "change-me"
    SESSION_SECRET = "dev-secret"
    ALLOWED_ORIGIN = "*"
    BACKEND_URL = "http://127.0.0.1:5000"
    DEFAULT_RADIUS_METRES = 100
    LOCKOUT_MINUTES = 10
    MAX_LOGIN_ATTEMPTS = 3
    IST_OFFSET_MINUTES = 330
    SESSION_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True

    @classmethod
    def refresh(cls) -> None:
        cls.DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", cls.DATA_DIR / "attendance.db"))
        cls.FACES_DIR = Path(os.environ.get("FACES_DIR", cls.DATA_DIR / "registered_faces"))
        cls.ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
        cls.SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret")
        cls.ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
        cls.BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:5000")
        cls.DEFAULT_RADIUS_METRES = int(os.environ.get("DEFAULT_RADIUS_METRES", "100"))
