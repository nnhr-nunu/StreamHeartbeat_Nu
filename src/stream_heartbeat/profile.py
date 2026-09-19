"""名前つきプロファイル。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from stream_heartbeat.config import (
    BEAT_TEXT_JITTER,
    DEFAULT_BACKDROP,
    DEFAULT_BEAT_TEXT,
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
    beat_text_scale: float = 1.0
    beat_text_opacity: float = 1.0
    beat_text_x: float = DEFAULT_BEAT_TEXT_X
    beat_text_y: float = DEFAULT_BEAT_TEXT_Y
    beat_text_jitter: float = BEAT_TEXT_JITTER
    beat_text_tilt: float = DEFAULT_BEAT_TEXT_TILT
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


def save_profile(path: Path, profile: HeartProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_profile(path: Path) -> HeartProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = {f.name for f in fields(HeartProfile)}
    filtered = {k: v for k, v in raw.items() if k in allowed}
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
    (root / STATE_FILENAME).write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_last_profile_name(data_dir: Path | None = None) -> str:
    return str(load_app_state(data_dir).get("last_profile", "default") or "default")


def save_last_profile_name(name: str, data_dir: Path | None = None) -> None:
    save_app_state(data_dir, last_profile=name)
