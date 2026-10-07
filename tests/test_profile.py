from __future__ import annotations

from pathlib import Path

import pytest

from stream_heartbeat.config import DEFAULT_BACKDROP, DEFAULT_BEAT_TEXT, DEFAULT_BEAT_TEXT_Y
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


def test_retired_grip_big_opens_as_grip(tmp_path: Path) -> None:
    # 心臓わしづかみ2（大きい手）はなくしたので、選んで保存していた設定は 1 の手で開く
    path = tmp_path / "p.json"
    path.write_text('{"name": "a", "effect": "grip_big"}', encoding="utf-8")
    assert load_profile(path).effect == "grip"


def test_new_profile_uses_heart_default_text() -> None:
    assert HeartProfile().beat_text == "❤"
    assert DEFAULT_BEAT_TEXT == "❤"
    assert HeartProfile().beat_text_y == DEFAULT_BEAT_TEXT_Y
    assert HeartProfile().beat_text_y < 0.4
    assert HeartProfile().beat_text_jitter == pytest.approx(0.12)
    assert HeartProfile().beat_text_tilt == pytest.approx(0.7)
    assert HeartProfile().beat_text_color == "#FF4D4D"
    assert HeartProfile().beat_text_scale == pytest.approx(1.4)
    assert HeartProfile().show_arrhythmia is False
    assert HeartProfile().backdrop == DEFAULT_BACKDROP
    assert HeartProfile().bpm_outline == "#000000"


def test_app_state_keeps_last_profile_when_saving_geometry(tmp_path: Path) -> None:
    save_last_profile_name("雑談", tmp_path)
    save_app_state(tmp_path, operator_geom={"x": 10, "y": 20, "w": 500, "h": 700})
    assert load_last_profile_name(tmp_path) == "雑談"
    state = load_app_state(tmp_path)
    assert state["operator_geom"]["x"] == 10
    save_last_profile_name("default", tmp_path)
    assert load_app_state(tmp_path)["operator_geom"]["x"] == 10


def test_broken_profile_does_not_stop_startup(tmp_path: Path) -> None:
    path = tmp_path / "雑談.json"
    path.write_text('{"name": "雑談", ', encoding="utf-8")
    profile = load_profile(path)
    assert profile.name == "雑談"
    assert not path.exists()
    assert (tmp_path / "雑談.json.broken").is_file()


def test_wrong_types_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(
        '{"name": "p", "scale": "big", "show_bpm": 1, "opacity": 1, '
        '"calibration": [[0.1, 0.2], "x", [0.3, "y"]]}',
        encoding="utf-8",
    )
    profile = load_profile(path)
    assert profile.scale == HeartProfile().scale
    assert profile.show_bpm is True
    assert profile.opacity == 1.0 and isinstance(profile.opacity, float)
    assert profile.calibration == [[0.1, 0.2]]


def test_save_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    save_profile(path, HeartProfile(name="p"))
    save_app_state(tmp_path, last_profile="p")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app_state.json", "p.json"]


def test_non_finite_numbers_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(
        '{"name": "p", "scale": NaN, "opacity": 1e30, "beat_text_x": Infinity, '
        '"heart_yaw_deg": -Infinity, "calibration": [[0.1, NaN], [0.2]]}',
        encoding="utf-8",
    )
    profile = load_profile(path)
    blank = HeartProfile()
    assert profile.scale == blank.scale
    assert profile.opacity == blank.opacity
    assert profile.beat_text_x == blank.beat_text_x
    assert profile.heart_yaw_deg == blank.heart_yaw_deg
    assert profile.calibration == [[0.2]]


def test_calibration_is_saved_compactly_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    take = [0.123456789 * (i % 7) for i in range(16000)]
    save_profile(path, HeartProfile(name="p", calibration=[take]))
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) < 60
    assert len(text) < 16000 * 9
    loaded = load_profile(path)
    assert loaded.name == "p"
    assert loaded.calibration[0][1] == pytest.approx(0.12346)
