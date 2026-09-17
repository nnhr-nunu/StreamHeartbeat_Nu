"""名前つきプロファイル。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from stream_heartbeat.config import DEFAULT_BEAT_TEXT
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
    show_bpm: bool = True
    oshilog_public_id: str = ""
    oshilog_bpm_url: str = ""
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


def load_last_profile_name(data_dir: Path | None = None) -> str:
    root = data_dir if data_dir is not None else resolve_data_dir()
    state = root / STATE_FILENAME
    if not state.is_file():
        return "default"
    raw = json.loads(state.read_text(encoding="utf-8"))
    return str(raw.get("last_profile", "default"))


def save_last_profile_name(name: str, data_dir: Path | None = None) -> None:
    root = data_dir if data_dir is not None else resolve_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / STATE_FILENAME).write_text(
        json.dumps({"last_profile": name}, ensure_ascii=False),
        encoding="utf-8",
    )
