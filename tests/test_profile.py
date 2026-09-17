from __future__ import annotations

from pathlib import Path

from stream_heartbeat.profile import HeartProfile, load_profile, save_profile


def test_profile_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "雑談.json"
    original = HeartProfile(name="雑談", beat_text="トクン", show_bpm=False, show_arrhythmia=False)
    save_profile(path, original)
    loaded = load_profile(path)
    assert loaded.name == "雑談"
    assert loaded.beat_text == "トクン"
    assert loaded.show_bpm is False
    assert loaded.show_arrhythmia is False


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text('{"name": "a", "future": 1}', encoding="utf-8")
    loaded = load_profile(path)
    assert loaded.name == "a"
