"""VTube Studio 連携の下回り: アイテムのフォルダ探しと、受け取った・保存した値の確かめ。"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

# モデル上の場所（ArtMesh の三角形と、その中の重み）。ItemPinRequest の pinInfo に使う
PIN_KEYS = (
    "modelID",
    "artMeshID",
    "vertexID1",
    "vertexID2",
    "vertexID3",
    "vertexWeight1",
    "vertexWeight2",
    "vertexWeight3",
)
# アイテムを置ける位置の範囲（ItemLoadRequest。画面の端は ±1）
POSITION_LIMIT = 1000.0


def _steam_roots() -> list[Path]:
    """Steam 本体の場所の候補。"""
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / "Steam"]
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                value, _kind = winreg.QueryValueEx(key, "SteamPath")
                roots.append(Path(str(value)))
        except OSError:
            pass
    roots += [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    return roots


def _steam_libraries() -> list[Path]:
    libraries: list[Path] = []
    for root in _steam_roots():
        libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(raw.replace("\\\\", "\\")))
    return libraries


def find_items_dir() -> Path | None:
    """VTube Studio のアイテムのフォルダ（Steam 版）。見つからなければ None。

    Windows 版は VTube Studio_Data の中、Mac 版はアプリ（.app）の中にある。
    """
    items = Path("StreamingAssets/Items")
    for library in _steam_libraries():
        game = library / "steamapps/common/VTube Studio"
        candidates = [game / "VTube Studio_Data" / items]
        bundles = sorted(game.glob("*.app"))
        candidates += [app / "Contents/Resources/Data" / items for app in bundles]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
    return None


def item_framerate(frames_per_second: float, systole: float, reference_systole: float) -> float:
    """拍が速いほど収縮が短いので、そのぶんコマ送りも速める（0.1〜120 に収める）。"""
    rate = frames_per_second * reference_systole / max(0.05, systole)
    return max(0.1, min(120.0, rate))


def clean_pin(raw: object) -> dict | None:
    """保存・受信したピンの場所を確かめる。形が崩れていれば None。"""
    if not isinstance(raw, dict):
        return None
    pin = {key: raw.get(key) for key in PIN_KEYS}
    if not all(isinstance(pin[key], str) and pin[key] for key in PIN_KEYS[:2]):
        return None
    for key in PIN_KEYS[2:5]:
        if not isinstance(pin[key], int) or isinstance(pin[key], bool):
            return None
    for key in PIN_KEYS[5:]:
        if not isinstance(pin[key], (int, float)) or isinstance(pin[key], bool):
            return None
        pin[key] = float(pin[key])
    return pin


def clicked_pin(event: dict) -> dict | None:
    """ModelClickedEvent から、いちばん手前の ArtMesh 上の場所を取り出す（左クリックだけ）。"""
    if event.get("modelWasClicked") is not True or event.get("mouseButtonID") != 0:
        return None
    return hit_pin(event.get("artMeshHits"))


def hit_pin(raw: object) -> dict | None:
    """ArtMesh に当たった所の一覧（artMeshHits）から、いちばん手前の場所を取り出す。"""
    hits = [h for h in raw if isinstance(h, dict)] if isinstance(raw, list) else []
    hits.sort(key=lambda h: o if isinstance(o := h.get("artMeshOrder"), int) else 999)
    for hit in hits:
        pin = clean_pin(hit.get("hitInfo"))
        if pin is not None:
            return pin
    return None


def clean_place(raw: object) -> tuple[float, float] | None:
    """保存・受信した画面の位置（x, y）を確かめる。形が崩れていれば None。"""
    if isinstance(raw, dict):
        raw = (raw.get("x"), raw.get("y"))
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    if not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in raw
    ):
        return None
    x, y = (max(-POSITION_LIMIT, min(POSITION_LIMIT, float(v))) for v in raw)
    return x, y
