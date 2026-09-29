"""名前つきプロファイル。"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from stream_heartbeat.config import (
    BEAT_TEXT_JITTER,
    DEFAULT_BACKDROP,
    DEFAULT_BEAT_TEXT,
    DEFAULT_BEAT_TEXT_COLOR,
    DEFAULT_BEAT_TEXT_OUTLINE,
    DEFAULT_BEAT_TEXT_SCALE,
    DEFAULT_BEAT_TEXT_TILT,
    DEFAULT_BEAT_TEXT_X,
    DEFAULT_BEAT_TEXT_Y,
    DEFAULT_BPM_COLOR,
    DEFAULT_BPM_OUTLINE,
    DEFAULT_BPM_X,
    DEFAULT_BPM_Y,
)
from stream_heartbeat.paths import resolve_data_dir

STATE_FILENAME = "app_state.json"


@dataclass
class HeartProfile:
    name: str = "default"
    mic_id: str = ""
    style: str = "realistic"
    scale: float = 0.7
    opacity: float = 1.0
    beat_text: str = DEFAULT_BEAT_TEXT
    show_beat_text: bool = True
    beat_text_scale: float = DEFAULT_BEAT_TEXT_SCALE
    beat_text_opacity: float = 1.0
    beat_text_x: float = DEFAULT_BEAT_TEXT_X
    beat_text_y: float = DEFAULT_BEAT_TEXT_Y
    beat_text_jitter: float = BEAT_TEXT_JITTER
    beat_text_tilt: float = DEFAULT_BEAT_TEXT_TILT
    beat_text_color: str = DEFAULT_BEAT_TEXT_COLOR
    beat_text_outline: str = DEFAULT_BEAT_TEXT_OUTLINE
    show_bpm: bool = True
    bpm_scale: float = 1.0
    bpm_x: float = DEFAULT_BPM_X
    bpm_y: float = DEFAULT_BPM_Y
    bpm_color: str = DEFAULT_BPM_COLOR
    bpm_outline: str = DEFAULT_BPM_OUTLINE
    show_arrhythmia: bool = False
    oshilog_public_id: str = ""
    oshilog_bpm_url: str = ""
    tap_interval: float = 0.0
    realistic_look: str = "surgical"
    heart_yaw_deg: float = -18.0
    heart_pitch_deg: float = 12.0
    backdrop: str = DEFAULT_BACKDROP
    calibration: list[list[float]] = field(default_factory=list)


def profiles_dir(data_dir: Path | None = None) -> Path:
    root = data_dir if data_dir is not None else resolve_data_dir()
    path = root / "profiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_atomic(path: Path, text: str) -> None:
    """書き込みの途中で落ちても、前のファイルを壊さない。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save_profile(path: Path, profile: HeartProfile) -> None:
    """設定は 1 項目 1 行で読みやすく、補正の音は丸めて 1 行に詰める（ファイルを小さく保つ）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    calibration = payload.pop("calibration")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    packed = json.dumps(
        [[round(x, 5) for x in take] for take in calibration], separators=(",", ":")
    )
    text = text[: text.rindex("}")].rstrip() + f',\n  "calibration": {packed}\n}}'
    _write_atomic(path, text)


def _set_aside(path: Path) -> None:
    """読めないファイルは上書きで消さないよう、名前を変えて残す。"""
    try:
        os.replace(path, path.with_name(path.name + ".broken"))
    except OSError:
        pass


def _same_kind(default: object, value: object) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, float):
        # NaN や無限大は画面の部品に入れると落ちるので受け付けない
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and abs(value) < 1e6
        )
    if isinstance(default, str):
        return isinstance(value, str)
    return True


def _clean_calibration(value: object) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    out: list[list[float]] = []
    for session in value:
        if isinstance(session, list) and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            for x in session
        ):
            out.append(session)
    return out


def load_profile(path: Path) -> HeartProfile:
    """壊れた・手で書き換えた項目は既定値にする。読めないファイルでも起動は止めない。"""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return HeartProfile(name=path.stem)
    except (json.JSONDecodeError, UnicodeDecodeError):
        _set_aside(path)
        return HeartProfile(name=path.stem)
    if not isinstance(raw, dict):
        _set_aside(path)
        return HeartProfile(name=path.stem)
    defaults = HeartProfile()
    filtered: dict[str, object] = {}
    for item in fields(HeartProfile):
        if item.name not in raw:
            continue
        value = raw[item.name]
        if item.name == "calibration":
            filtered[item.name] = _clean_calibration(value)
            continue
        default = getattr(defaults, item.name)
        if _same_kind(default, value):
            filtered[item.name] = float(value) if isinstance(default, float) else value
    return HeartProfile(**filtered)


def list_profiles(data_dir: Path | None = None) -> list[Path]:
    folder = profiles_dir(data_dir)
    return sorted(folder.glob("*.json"))


def load_app_state(data_dir: Path | None = None) -> dict:
    root = data_dir if data_dir is not None else resolve_data_dir()
    state = root / STATE_FILENAME
    if not state.is_file():
        return {}
    try:
        raw = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_app_state(data_dir: Path | None = None, **updates: object) -> None:
    root = data_dir if data_dir is not None else resolve_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    state = load_app_state(root)
    for key, value in updates.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    _write_atomic(root / STATE_FILENAME, json.dumps(state, ensure_ascii=False, indent=2))


def load_last_profile_name(data_dir: Path | None = None) -> str:
    return str(load_app_state(data_dir).get("last_profile", "default") or "default")


def save_last_profile_name(name: str, data_dir: Path | None = None) -> None:
    save_app_state(data_dir, last_profile=name)
