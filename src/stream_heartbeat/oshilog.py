"""OshiLog 補助 BPM。音は送らない。"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen


def parse_aux_bpm(payload: str) -> int | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
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
    except (URLError, TimeoutError, OSError, ValueError):
        # ValueError: https:// の付け忘れなどの書式違い・文字化け
        return None
    return parse_aux_bpm(body)


class AuxBpmPoller:
    """補助 BPM を裏で取りに行く。通信待ちで配信用の窓の動きを止めない。"""

    def __init__(self, fetch: Callable[[str], int | None] = fetch_aux_bpm) -> None:
        self._fetch = fetch
        self._url = ""
        self._thread: threading.Thread | None = None
        self.bpm: int | None = None

    def poll(self, url: str) -> int | None:
        """前回取れた値を返し、終わっていれば次を取りに行く。"""
        if url != self._url:
            self._url = url
            self.bpm = None
        if url and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, args=(url,), daemon=True)
            self._thread.start()
        return self.bpm

    def _run(self, url: str) -> None:
        try:
            bpm = self._fetch(url)
        except Exception:
            bpm = None
        if url == self._url:
            self.bpm = bpm
