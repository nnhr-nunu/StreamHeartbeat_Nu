"""操作画面の保存・切り替え・マイク選択まわりの不具合の再発防止。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QInputDialog, QLabel, QMessageBox, QWidget

from stream_heartbeat.profile import (
    HeartProfile,
    clean_profile_name,
    load_profile,
    save_profile,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.operator_window import OperatorWindow, obs_hint
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.placement import apply_window_geom


@pytest.fixture(autouse=True)
def _isolate_operator_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )


def _open(profile: HeartProfile | None = None) -> tuple[OperatorWindow, OutputWindow]:
    session = HeartSession(profile)
    output = OutputWindow(session)
    return OperatorWindow(session, output), output


def _notices(operator: OperatorWindow) -> str:
    return " ".join(label.text() for label in operator.findChildren(QLabel))


def test_save_as_writes_new_profile_and_keeps_original(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    operator, output = _open()
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("streamA", True))
    operator._save_as()
    folder = operator._data_dir / "profiles"
    assert (folder / "streamA.json").is_file()
    assert operator._profiles.currentText() == "streamA"
    assert load_profile(folder / "streamA.json").name == "streamA"
    operator._scale.setValue(55)
    operator._save_current()
    assert load_profile(folder / "streamA.json").scale == pytest.approx(0.55)
    assert not (folder / "default.json").is_file() or (
        load_profile(folder / "default.json").scale != pytest.approx(0.55)
    )
    operator.close()
    output.close()


def test_slider_values_do_not_drift_on_reload(qapp: QApplication) -> None:
    del qapp
    operator, output = _open(HeartProfile(scale=1.16, opacity=0.57, beat_text_scale=0.58))
    for _ in range(3):
        operator._load_into_controls(operator._session.profile)
    profile = operator._session.profile
    assert profile.scale == pytest.approx(1.16)
    assert profile.opacity == pytest.approx(0.57)
    assert profile.beat_text_scale == pytest.approx(0.58)
    operator.close()
    output.close()


def test_color_outside_choices_is_kept(qapp: QApplication) -> None:
    del qapp
    operator, output = _open(HeartProfile(bpm_color="#12AB34", beat_text_color="#ABCDEF"))
    operator._scale.setValue(80)
    profile = operator._session.profile
    assert profile.bpm_color == "#12AB34"
    assert profile.beat_text_color == "#ABCDEF"
    operator.close()
    output.close()


def test_missing_mic_is_not_overwritten(qapp: QApplication) -> None:
    del qapp
    operator, output = _open(HeartProfile(mic_id="unplugged-usb-mic"))
    operator._scale.setValue(80)
    operator._save_current(notice=None)
    assert operator._session.profile.mic_id == "unplugged-usb-mic"
    operator.close()
    output.close()


def test_switching_profile_saves_edits_and_drops_recording(qapp: QApplication) -> None:
    del qapp
    operator, output = _open()
    folder = operator._data_dir / "profiles"
    save_profile(folder / "other.json", HeartProfile(name="other"))
    operator._fill_profiles()
    operator._scale.setValue(44)
    operator._session.begin_calibration(0.0)
    operator._profiles.setCurrentText("other")
    assert operator._session.profile.name == "other"
    assert not operator._session.recording
    assert load_profile(folder / "default.json").scale == pytest.approx(0.44)
    operator.close()
    output.close()


def test_save_failure_on_close_still_shuts_everything(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    operator, output = _open()
    output.show()

    def locked(*_a: object, **_k: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr("stream_heartbeat.ui.operator_window.save_profile", locked)
    monkeypatch.setattr("stream_heartbeat.ui.operator_window.save_app_state", locked)
    operator.close()
    assert not output.isVisible()
    assert not operator._timer.isActive()


def test_calibration_without_sound_is_not_reported_as_saved(qapp: QApplication) -> None:
    del qapp
    operator, output = _open()
    operator._begin_cal()
    operator._session.tick(0.5, [0.0] * 800)
    operator._commit_cal()
    assert not operator._session.profile.calibration
    assert "保存しませんでした" in _notices(operator)
    operator.close()
    output.close()


def test_transparent_backdrop_rebuilds_shown_output(qapp: QApplication) -> None:
    del qapp
    operator, output = _open()
    output.show()
    index = operator._backdrop.findData("transparent")
    operator._backdrop.setCurrentIndex(index)
    rebuilt = operator._output
    assert rebuilt is not output
    assert not output.isVisible()
    assert rebuilt.isVisible()
    # 作り直した窓は透過で作られているので、緑に戻しても作り直さない
    operator._backdrop.setCurrentIndex(operator._backdrop.findData("green"))
    assert operator._output is rebuilt
    operator.close()
    assert not rebuilt.isVisible()


def test_window_restores_on_second_monitor(qapp: QApplication) -> None:
    del qapp
    primary = QRect(0, 0, 1920, 1040)
    second = QRect(1920, 0, 2560, 1400)
    widget = QWidget()
    saved = {"x": 2400, "y": 200, "w": 600, "h": 500}
    assert apply_window_geom(widget, saved, primary, [primary, second])
    assert widget.pos().x() == 2400
    widget.close()


def test_profile_name_drops_characters_windows_cannot_save() -> None:
    assert clean_profile_name("配信/雑談") == "配信_雑談"
    assert clean_profile_name(' a:b*c?"<>| ') == "a_b_c_____"
    assert clean_profile_name("歌枠. ") == "歌枠"
    assert clean_profile_name("con") == "con_"
    assert clean_profile_name("  ") == ""


def test_save_as_cleans_name_and_asks_before_replacing(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    operator, output = _open()
    folder = operator._data_dir / "profiles"
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("配信/雑談", True))
    operator._save_as()
    assert (folder / "配信_雑談.json").is_file()
    # 別のプロファイルの名前を選んだら、置き換えてよいか聞く（いいえなら書かない）
    save_profile(folder / "other.json", HeartProfile(name="other", scale=0.3))
    monkeypatch.setattr(QInputDialog, "getText", lambda *_a, **_k: ("other", True))
    asked: list[str] = []

    def _no(*args: object, **_k: object) -> QMessageBox.StandardButton:
        asked.append(str(args[2]))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", _no)
    operator._save_as()
    assert asked and "other" in asked[0]
    assert load_profile(folder / "other.json").scale == pytest.approx(0.3)
    assert operator._profiles.currentText() == "配信_雑談"
    operator.close()
    output.close()


def test_obs_hint_follows_backdrop() -> None:
    assert "クロマキーで緑" in obs_hint("green")
    assert "カラーキーで白" in obs_hint("white")
    assert "キー" not in obs_hint("transparent")
