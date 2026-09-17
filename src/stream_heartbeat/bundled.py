"""同梱の心音サンプル。ユーザー追加分は assets/heart_samples/ へ。"""

from __future__ import annotations

from pathlib import Path

from stream_heartbeat.detect import load_wav_mono
from stream_heartbeat.samples import AUDIO_SUFFIXES, load_audio_mono


def heart_samples_dir() -> Path:
    return Path(__file__).resolve().parent / "assets" / "heart_samples"


def bundled_heart_sessions() -> list[list[float]]:
    folder = heart_samples_dir()
    if not folder.is_dir():
        return []
    sessions: list[list[float]] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        try:
            if path.suffix.lower() == ".wav":
                sessions.append(load_wav_mono(path))
            else:
                sessions.append(load_audio_mono(path))
        except (OSError, ValueError):
            continue
    return sessions
