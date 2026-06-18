from __future__ import annotations

import base64
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config


def now_ist_iso() -> str:
    ist = timezone(timedelta(minutes=Config.IST_OFFSET_MINUTES))
    return datetime.now(ist).isoformat(timespec="seconds")


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def ensure_face_dir() -> Path:
    Config.FACES_DIR.mkdir(parents=True, exist_ok=True)
    return Config.FACES_DIR


def decode_data_url(data_url: str) -> bytes:
    if "," not in data_url:
        raise ValueError("Invalid image payload")
    _, payload = data_url.split(",", 1)
    return base64.b64decode(payload)
