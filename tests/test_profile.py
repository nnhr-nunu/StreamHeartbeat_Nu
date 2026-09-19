from __future__ import annotations

from pathlib import Path

from stream_heartbeat.config import DEFAULT_BEAT_TEXT
from stream_heartbeat.profile import (
    HeartProfile,
    load_app_state,
    load_last_profile_name,
    load_profile,
    save_app_state,
    save_last_profile_name,
    save_profile,
)


def test_profile_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "雑談.json"
    original = HeartProfile(
        name="雑談",
        beat_text="トクン",
        show_bpm=False,
        show_arrhythmia=False,
        show_beat_text=False,
        beat_text_scale=1.4,
        beat_text_opacity=0.6,
        tap_interval=0.8,
    )
    save_profile(path, original)
    loaded = load_profile(path)
    assert loaded.name == "雑談"
    assert loaded.beat_text == "トクン"
    assert loaded.show_bpm is False
    assert loaded.show_arrhythmia is False
    assert loaded.show_beat_text is False
    assert loaded.beat_text_scale == 1.4
    assert loaded.beat_text_opacity == 0.6
    assert loaded.tap_interval == 0.8


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text('{"name": "a", "future": 1}', encoding="utf-8")
    loaded = load_profile(path)
    assert loaded.name == "a"


def test_new_profile_uses_heart_default_text() -> None:
    assert HeartProfile().beat_text == "❤"
    assert DEFAULT_BEAT_TEXT == "❤"


def test_app_state_keeps_last_profile_when_saving_geometry(tmp_path: Path) -> None:
    save_last_profile_name("雑談", tmp_path)
    save_app_state(tmp_path, operator_geom={"x": 10, "y": 20, "w": 500, "h": 700})
    assert load_last_profile_name(tmp_path) == "雑談"
    state = load_app_state(tmp_path)
    assert state["operator_geom"]["x"] == 10
    save_last_profile_name("default", tmp_path)
    assert load_app_state(tmp_path)["operator_geom"]["x"] == 10
