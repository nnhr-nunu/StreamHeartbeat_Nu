"""OshiLog 補助 BPM。音は送らない。"""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen


def parse_aux_bpm(payload: str) -> int | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    raw = data.get("bpm")
    if raw is None:
        return None
    try:
        bpm = int(raw)
    except (TypeError, ValueError):
        return None
    if bpm <= 0:
        return None
    return bpm


def fetch_aux_bpm(url: str, *, opener=urlopen) -> int | None:
    if not url:
        return None
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with opener(req, timeout=2.0) as resp:
            body = resp.read().decode("utf-8")
    except (URLError, TimeoutError, OSError):
        return None
    return parse_aux_bpm(body)
