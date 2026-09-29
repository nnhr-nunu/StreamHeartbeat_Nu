"""評価に使う録音の一覧（リポジトリの外・非公開）と、デコード結果のキャッシュ先。

録音の場所は Git に載せない recordings.local.json に書く（名前 → ファイルのパス）。
    {"失神前後": "D:/.../失神心音.m4a", "緊張": "D:/.../緊張.mp3"}
cache/・labels/・results/ も手元だけに置く（.gitignore 済み）。
"""

from __future__ import annotations

import array
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
LOCAL_LIST = HERE / "recordings.local.json"


def _load_files() -> dict[str, str]:
    if not LOCAL_LIST.is_file():
        raise SystemExit(f"{LOCAL_LIST.name} がありません。名前 → 録音のパスの JSON を置いてください")
    raw = json.loads(LOCAL_LIST.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in raw.items()}


FILES: dict[str, str] = _load_files()
SR = 16000


def f32_path(name: str) -> Path:
    return CACHE / f"{name}.f32"


def load_cached(name: str) -> list[float]:
    """decode_cache.py が作った 16 kHz モノラルを読む（Qt 不要）。"""
    a = array.array("f")
    a.frombytes(f32_path(name).read_bytes())
    return a.tolist()
