from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QLabel,
    QPushButton,
    QToolButton,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE
from stream_heartbeat.profile import load_app_state
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.operator_window import CAL_DISCARD, CAL_RESET, OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


@pytest.fixture(autouse=True)
def _isolate_operator_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )


def test_two_windows_have_obs_titles(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    assert operator.windowTitle() == OPERATOR_WINDOW_TITLE
    assert output.windowTitle() == OUTPUT_WINDOW_TITLE
    operator.close()
    output.close()


def test_only_style_material_and_effect_combos_change_on_wheel(qapp: QApplication) -> None:
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)

    def spin(combo: QComboBox) -> bool:
        combo.setCurrentIndex(0)
        event = QWheelEvent(
            QPointF(5, 5),
            QPointF(5, 5),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        combo.wheelEvent(event)
        return combo.currentIndex() != 0

    combos = [c for c in operator.findChildren(QComboBox) if c.count() > 1]
    wheeled = (operator._style, operator._material, operator._effect)
    assert spin(operator._style)
    assert spin(operator._material)
    # どのスタイルにも演出が 2 つ以上（なし＋はじけるハートなど）あるので、ホイールで変わる
    assert operator._effect.count() > 1 and spin(operator._effect)
    assert combos and not any(spin(c) for c in combos if c not in wheeled)
    operator.close()
    output.close()


def test_operator_labels_and_not_always_on_top(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    flag = Qt.WindowType.WindowStaysOnTopHint
    assert not (operator.windowFlags() & flag)
    assert not (output.windowFlags() & flag)
    titles = [box.title() for box in operator.findChildren(QGroupBox)]
    assert "② スタイル" in titles
    assert "③ 同期文字" in titles and "④ 心拍数" in titles
    # 背景と向きはスタイルの欄にまとめ、⑤ はよく使う VTube Studio 連携
    assert "⑤ VTube Studio 連携" in titles
    assert not any("背景と向き" in title for title in titles)
    style_box = next(b for b in operator.findChildren(QGroupBox) if b.title() == "② スタイル")
    style_labels = [lab.text() for lab in style_box.findChildren(QLabel)]
    assert "背景" in style_labels and any("OBS" in text for text in style_labels)
    assert any(box.text() == "角度を固定" for box in style_box.findChildren(QCheckBox))
    profiles = operator.findChildren(QComboBox)[0]
    assert not profiles.isEditable()
    fold_texts = [btn.text() for btn in operator.findChildren(QToolButton)]
    order = [
        next(i for i, text in enumerate(fold_texts) if key in text)
        for key in ("上手くいかない時", "心拍の補正")
    ]
    assert order == sorted(order)
    # 未実装の推しログ連携は出さない
    assert not any(
        "推しログ" in btn.text() and btn.isVisibleTo(operator)
        for btn in operator.findChildren(QToolButton)
    )
    assert not any(btn.isChecked() for btn in operator.findChildren(QToolButton))
    assert not any("試験的" in text for text in fold_texts)
    # 設定は自動で保存するので、上書き保存のボタンは無い
    assert not any(btn.text() == "上書き保存" for btn in operator.findChildren(QPushButton))
    tap = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "拍")
    assert not tap.isEnabled()
    primary = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "補正開始")
    discard = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == CAL_DISCARD)
    reset = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == CAL_RESET)
    assert not discard.isEnabled()
    assert not reset.isEnabled()
    primary.click()
    assert tap.isEnabled()
    assert primary.text() == "補正を保存"
    assert discard.isEnabled()
    guides = " ".join(label.text() for label in operator.findChildren(QLabel))
    assert "マイク" in guides
    assert "スペース" in guides
    assert "10回" in guides
    assert "拍" in guides
    assert "補正開始" in guides and "補正を保存" in guides
    assert "wav" not in guides
    buttons = operator.findChildren(QPushButton)
    assert not any(btn.text() == "心音ファイルを追加" and btn.isVisible() for btn in buttons)
    assert not any(
        "不整脈" in box.text() and box.isVisible() for box in operator.findChildren(QCheckBox)
    )
    assert any("左右" in lab.text() or "横" in lab.text() for lab in operator.findChildren(QLabel))
    assert any("上下" in lab.text() or "縦" in lab.text() for lab in operator.findChildren(QLabel))
    assert any("ゆらぎ" in lab.text() for lab in operator.findChildren(QLabel))
    assert any("傾き" in lab.text() for lab in operator.findChildren(QLabel))
    assert any(lab.text() == "透明" for lab in operator.findChildren(QLabel))
    assert any(lab.text() == "不透明" for lab in operator.findChildren(QLabel))
    assert sum(1 for lab in operator.findChildren(QLabel) if lab.text() == "文字色") >= 2
    reset_btns = [
        btn
        for box in operator.findChildren(QGroupBox)
        if box.title() in ("③ 同期文字", "④ 心拍数")
        for btn in box.findChildren(QPushButton)
        if btn.text() == "設定をリセット"
    ]
    assert len(reset_btns) == 2
    assert any(
        "緑" in box.itemText(i)
        for box in operator.findChildren(QComboBox)
        for i in range(box.count())
    )
    assert "録音停止" not in guides
    session.tick(session.now + 0.1, [0.2] * 80, sample_rate=1000.0)
    primary.click()
    assert not tap.isEnabled()
    assert primary.text() == "補正開始"
    assert not discard.isEnabled()
    assert reset.isEnabled()
    assert any("保存しました" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_save_notice_survives_tick(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._save_current()
    operator._on_tick()
    assert any("保存しました" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_changes_are_saved_automatically(qapp: QApplication) -> None:
    from stream_heartbeat.profile import load_profile

    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    path = operator._data_dir / "profiles" / "default.json"
    operator._scale.setValue(42)
    # 配信用の窓で変えた値（向き）も拾う
    session.profile.heart_yaw_deg = 33.0
    operator._autosave()
    saved = load_profile(path)
    assert saved.scale == pytest.approx(0.42)
    assert saved.heart_yaw_deg == pytest.approx(33.0)
    # 黙って保存する（知らせは出さない）。変わっていなければ書き直さない
    assert not operator._notice.isVisibleTo(operator)
    mtime = path.stat().st_mtime_ns
    operator._autosave()
    assert path.stat().st_mtime_ns == mtime
    operator.close()
    output.close()


def test_fold_and_combo_show_pulldown_mark(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    folds = operator.findChildren(QToolButton)
    texts = [btn.text() for btn in folds]
    assert any(text.startswith("▶") or text.startswith("▼") for text in texts)
    marks = [lab for lab in operator.findChildren(QLabel) if lab.objectName() == "comboMark"]
    assert len(marks) >= 3
    assert all(lab.text() == "▼" for lab in marks)
    assert len(operator.findChildren(QComboBox)) >= 4
    labels = " ".join(
        box.itemText(i)
        for box in operator.findChildren(QComboBox)
        for i in range(box.count())
    )
    assert "リアル1" in labels
    assert "リアル2" in labels
    assert "手術" not in labels
    assert "透明" in labels
    operator.close()
    output.close()


def test_detect_banner_stays_above_scroll(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    banner = operator.findChild(QFrame, "detectBanner")
    assert banner is not None
    shell = operator.centralWidget()
    assert shell is not None
    layout = shell.layout()
    assert layout is not None
    assert layout.itemAt(0).widget() is banner
    assert operator._status.parent() is banner
    operator.close()
    output.close()


def test_operator_marks_preview_and_live(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._on_tick()
    assert "プレビュー中（心音未認識）" in operator._status.text()
    session.clock.feed_beat(0.0)
    session.clock.feed_beat(0.5)
    operator._on_tick()
    assert "心拍同期表示中" in operator._status.text()
    session.clock.lost_if_silent(3.0)
    operator._on_tick()
    assert "プレビュー中（心音未認識）" in operator._status.text()
    operator.close()
    output.close()


def test_discard_aborts_current_correction(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    primary = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == "補正開始")
    discard = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == CAL_DISCARD)
    saved = [list(chunk) for chunk in session.profile.calibration]
    primary.click()
    session.tick(session.now + 0.1, [0.2] * 80, sample_rate=1000.0)
    discard.click()
    assert primary.text() == "補正開始"
    assert not discard.isEnabled()
    assert session.recording is False
    assert [list(chunk) for chunk in session.profile.calibration] == saved
    assert any("中止" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_reset_clears_saved_heart_sound(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._confirm_reset = lambda: True  # type: ignore[method-assign]
    session.profile.calibration.append([0.2] * 20)
    operator._sync_cal_ui()
    reset = next(btn for btn in operator.findChildren(QPushButton) if btn.text() == CAL_RESET)
    assert reset.isEnabled()
    reset.click()
    assert session.profile.calibration == []
    assert not reset.isEnabled()
    assert any("消しました" in label.text() for label in operator.findChildren(QLabel))
    operator.close()
    output.close()


def test_output_close_quits_operator_too(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    output.set_quit_handler(operator.close)
    operator.show()
    output.show()
    output.close()
    assert operator._closing is True


def test_close_saves_window_positions(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator.show()
    output.show()
    operator.move(120, 80)
    output.move(640, 90)
    operator.close()
    state = load_app_state(operator._data_dir)
    assert state["operator_geom"]["x"] == 120
    assert state["output_geom"]["x"] == 640


def _group_reset(operator: OperatorWindow, title: str) -> QPushButton:
    box = next(item for item in operator.findChildren(QGroupBox) if item.title() == title)
    return next(btn for btn in box.findChildren(QPushButton) if btn.text() == "設定をリセット")


def test_beat_and_bpm_reset_only_own_group(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._beat_x.setValue(8)
    operator._bpm_scale.setValue(180)
    _group_reset(operator, "③ 同期文字").click()
    assert operator._beat_x.value() == 50
    assert operator._bpm_scale.value() == 180
    _group_reset(operator, "④ 心拍数").click()
    assert operator._bpm_scale.value() == 100
    operator.close()
    output.close()


def test_output_redraws_hwnd_when_time_advances(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    called: list[int] = []
    monkeypatch.setattr(
        "stream_heartbeat.ui.output_window.redraw_hwnd",
        lambda hwnd: called.append(int(hwnd)) or True,
    )
    session = HeartSession()
    output = OutputWindow(session)
    output.canvas.set_now(1.25)
    assert called
    output.close()


def test_text_details_fold_when_unchecked(qapp: QApplication) -> None:
    del qapp
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator._show_bpm.setChecked(True)
    assert not operator._bpm_details.isHidden()
    operator._show_bpm.setChecked(False)
    assert operator._bpm_details.isHidden()
    session.profile.show_bpm = True
    operator._load_into_controls(session.profile)
    assert not operator._bpm_details.isHidden()
    operator.close()
    output.close()


def test_startup_splash_shows_steps_and_closes(qapp: QApplication) -> None:
    from stream_heartbeat.ui.splash import StartupSplash

    splash = StartupSplash()
    splash.show_now()
    splash.step("心臓の形を作っています（初回だけ少しかかります）")
    assert splash.step_text.startswith("心臓の形")
    image = splash.grab()
    assert not image.isNull()
    splash.finish(QWidget())
    qapp.processEvents()
    assert not splash.isVisible()


def test_closed_windows_do_not_reopen_mic_on_device_change(qapp: QApplication) -> None:
    """閉じた窓が、マイクの抜き差しの知らせでマイクを開き直さない。

    テストの窓は閉じても残る。残った窓が知らせのたびにマイクを開き直すと、窓の数だけ
    音声の裏スレッドが同時に走り、pytest-qt の Qt ログ捕捉と重なって全体が native で落ちた。
    """
    windows = []
    for _ in range(30):
        session = HeartSession()
        output = OutputWindow(session)
        operator = OperatorWindow(session, output)
        operator.close()
        output.close()
        windows.append(operator)
    for operator in windows:
        operator._devices.audioInputsChanged.emit()
    qapp.processEvents()
    assert all(operator._mic._source is None for operator in windows)
