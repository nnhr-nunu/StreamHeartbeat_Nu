"""新しい版が出ているかを GitHub のリリースで確かめる。送るのは版を聞く要求だけ。"""

from __future__ import annotations

import json
import re
import ssl
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from stream_heartbeat import __version__

REPO = "nnhr-nunu/StreamHeartbeat_Nu"
# CI が main へ push されるたびに上書きするリリース。題名に版（v0.2.0 など）が入っている
LATEST_RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/tags/latest"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/latest"
_TITLE_VERSION = re.compile(r"\bv(\d+(?:\.\d+)+)\b")
# Mac の配布物の Python は証明書の置き場所を知らないので、OS の証明書の束を足す
_MAC_CERTS = Path("/etc/ssl/cert.pem")


def version_in_title(payload: str) -> str | None:
    """リリースの JSON の題名から版（"0.2.0" など）を取り出す。"""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("name")
    if not isinstance(name, str):
        return None
    m = _TITLE_VERSION.search(name)
    return m.group(1) if m else None


def _parts(version: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+(?:\.\d+)*", version):
        return None
    return tuple(int(p) for p in version.split("."))


def is_newer(latest: str, current: str) -> bool:
    """`latest` が `current` より新しいか。読めない版は新しくないとみなす。"""
    a, b = _parts(latest), _parts(current)
    if a is None or b is None:
        return False
    # 0.2 と 0.2.0 を同じに扱う
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if sys.platform == "darwin" and _MAC_CERTS.is_file():
        ctx.load_verify_locations(cafile=str(_MAC_CERTS))
    return ctx


def fetch_newer_version(current: str = __version__, *, opener=urlopen) -> str | None:
    """新しい版が出ていればその版を返す。同じ版・古い版・通信できないときは None。"""
    try:
        req = Request(
            LATEST_RELEASE_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"StreamHeartbeat/{current}",
            },
        )
        with opener(req, timeout=5.0, context=_ssl_context()) as resp:
            body = resp.read().decode("utf-8")
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    latest = version_in_title(body)
    if latest is None or not is_newer(latest, current):
        return None
    return latest


class UpdateChecker:
    """新しい版が出ているかを裏で 1 回だけ確かめる。通信待ちで画面を止めない。"""

    def __init__(self, fetch: Callable[[], str | None] | None = None) -> None:
        self._fetch = fetch
        self._thread: threading.Thread | None = None
        self.newer: str | None = None

    @property
    def started(self) -> bool:
        return self._thread is not None

    @property
    def finished(self) -> bool:
        return self._thread is not None and not self._thread.is_alive()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self) -> None:
        # 既定の確かめ方はここで引く（テストで通信を止めるために差し替える）
        fetch = self._fetch or fetch_newer_version
        try:
            self.newer = fetch()
        except Exception:
            self.newer = None
