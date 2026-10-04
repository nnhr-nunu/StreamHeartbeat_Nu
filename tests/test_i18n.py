"""日本語 / English 切り替えの核（tr・言語の決め方・画面の付け替え）。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import OPERATOR_WINDOW_TITLE, OUTPUT_WINDOW_TITLE, i18n
from stream_heartbeat.i18n import (
    FOLD_TITLE_PROP,
    LANG_EN,
    LANG_JA,
    SKIP_PROP,
    detect_language,
    init_language,
    language,
    other_language_label,
    set_language,
    tr,
    translate_tree,
)
from stream_heartbeat.profile import STATE_FILENAME, load_app_state
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.fold import fold_toggle
from stream_heartbeat.ui.operator_window import OperatorWindow, obs_hint
from stream_heartbeat.ui.output_window import OutputWindow


@pytest.fixture
def small_table(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """核のテスト用に、小さな英訳の表へ差し替える（本物の表の中身に左右されない）。"""
    table = {
        "保存": "Save",
        "設定": "Settings",
        "小": "Small",
        "小さく": "Small",
        "大": "Large",
        "{n} 件": "{n} items",
        "心拍の補正": "Calibration",
        "ヒント": "Hint",
        "入力欄": "Input",
    }
    monkeypatch.setattr(i18n, "EN", table)
    monkeypatch.setattr(i18n, "_REVERSE", i18n._build_reverse(table))
    return table


def test_tr_returns_japanese_by_default(small_table: dict[str, str]) -> None:
    del small_table
    assert language() == LANG_JA
    assert tr("保存") == "保存"


def test_tr_translates_in_english(small_table: dict[str, str]) -> None:
    del small_table
    set_language(LANG_EN)
    assert tr("保存") == "Save"


def test_tr_falls_back_to_japanese_when_missing(small_table: dict[str, str]) -> None:
    del small_table
    set_language(LANG_EN)
    assert tr("表に無い文") == "表に無い文"


def test_tr_formats_only_the_template(small_table: dict[str, str]) -> None:
    del small_table
    set_language(LANG_EN)
    assert tr("{n} 件", n="{0}x}") == "{0}x} items"
    set_language(LANG_JA)
    assert tr("{n} 件", n="{0}x}") == "{0}x} 件"


def test_tr_without_fmt_keeps_braces(small_table: dict[str, str]) -> None:
    del small_table
    assert tr("{そのまま}") == "{そのまま}"


def test_set_language_ignores_unknown() -> None:
    set_language(LANG_EN)
    set_language("fr")
    assert language() == LANG_JA


@pytest.mark.parametrize(
    ("saved", "locale_name", "expected"),
    [
        ("en", "ja_JP", "en"),
        ("ja", "en_US", "ja"),
        (None, "ja_JP", "ja"),
        (None, "en_US", "en"),
        ("fr", "ja_JP", "ja"),
        (123, "en_US", "en"),
        ("", "de_DE", "en"),
    ],
)
def test_detect_language(saved: object, locale_name: str, expected: str) -> None:
    assert detect_language(saved, locale_name) == expected


def test_init_language_reads_saved_state(tmp_path: Path) -> None:
    (tmp_path / STATE_FILENAME).write_text(json.dumps({"language": "en"}), encoding="utf-8")
    assert init_language(tmp_path) == LANG_EN
    assert language() == LANG_EN


def test_init_language_survives_broken_state(tmp_path: Path) -> None:
    (tmp_path / STATE_FILENAME).write_text("{壊れた", encoding="utf-8")
    assert init_language(tmp_path) in (LANG_JA, LANG_EN)


def test_other_language_label() -> None:
    assert other_language_label() == "English"
    set_language(LANG_EN)
    assert other_language_label() == "日本語"


def _build_tree() -> QWidget:
    root = QWidget()
    col = QVBoxLayout(root)
    label = QLabel("保存")
    label.setToolTip("ヒント")
    check = QCheckBox("設定")
    button = QPushButton("保存")
    group = QGroupBox("設定")
    edit = QLineEdit()
    edit.setPlaceholderText("入力欄")
    combo = QComboBox()
    combo.addItem("小", ("a", 1))
    combo.addItem("大", ("b", 2))
    inner = QWidget()
    fold = fold_toggle("心拍の補正", inner, expanded=True)
    for widget in (label, check, button, group, edit, combo, fold, inner):
        col.addWidget(widget)
    root.label = label  # type: ignore[attr-defined]
    root.check = check  # type: ignore[attr-defined]
    root.button = button  # type: ignore[attr-defined]
    root.group = group  # type: ignore[attr-defined]
    root.edit = edit  # type: ignore[attr-defined]
    root.combo = combo  # type: ignore[attr-defined]
    root.fold = fold  # type: ignore[attr-defined]
    return root


def test_translate_tree_round_trip(qapp: QApplication, small_table: dict[str, str]) -> None:
    del qapp, small_table
    root = _build_tree()
    set_language(LANG_EN)
    translate_tree(root)
    assert root.label.text() == "Save"  # type: ignore[attr-defined]
    assert root.label.toolTip() == "Hint"  # type: ignore[attr-defined]
    assert root.check.text() == "Settings"  # type: ignore[attr-defined]
    assert root.button.text() == "Save"  # type: ignore[attr-defined]
    assert root.group.title() == "Settings"  # type: ignore[attr-defined]
    assert root.edit.placeholderText() == "Input"  # type: ignore[attr-defined]
    assert [root.combo.itemText(i) for i in range(2)] == ["Small", "Large"]  # type: ignore[attr-defined]
    assert [root.combo.itemData(i) for i in range(2)] == [("a", 1), ("b", 2)]  # type: ignore[attr-defined]
    assert root.fold.text() == "▼ Calibration"  # type: ignore[attr-defined]
    set_language(LANG_JA)
    translate_tree(root)
    assert root.label.text() == "保存"  # type: ignore[attr-defined]
    assert root.label.toolTip() == "ヒント"  # type: ignore[attr-defined]
    assert root.group.title() == "設定"  # type: ignore[attr-defined]
    assert root.edit.placeholderText() == "入力欄"  # type: ignore[attr-defined]
    assert [root.combo.itemText(i) for i in range(2)] == ["小", "大"]  # type: ignore[attr-defined]
    assert root.fold.text() == "▼ 心拍の補正"  # type: ignore[attr-defined]


def test_translate_tree_fold_follows_open_state(
    qapp: QApplication, small_table: dict[str, str]
) -> None:
    del qapp, small_table
    root = _build_tree()
    fold = root.fold  # type: ignore[attr-defined]
    fold.setChecked(False)
    set_language(LANG_EN)
    translate_tree(root)
    assert fold.text() == "▶ Calibration"
    fold.setChecked(True)
    assert fold.text() == "▼ Calibration"


def test_translate_tree_keeps_duplicate_english_apart(
    qapp: QApplication, small_table: dict[str, str]
) -> None:
    """「小」と「小さく」は英語が同じ。往復で取り違えない。"""
    del small_table
    del qapp
    root = QWidget()
    col = QVBoxLayout(root)
    a = QLabel("小")
    b = QLabel("小さく")
    col.addWidget(a)
    col.addWidget(b)
    set_language(LANG_EN)
    translate_tree(root)
    assert (a.text(), b.text()) == ("Small", "Small")
    set_language(LANG_JA)
    translate_tree(root)
    assert (a.text(), b.text()) == ("小", "小さく")


def test_translate_tree_skips_unknown_text(
    qapp: QApplication, small_table: dict[str, str]
) -> None:
    del qapp, small_table
    root = QWidget()
    col = QVBoxLayout(root)
    dynamic = QLabel("心拍 72 BPM")
    number = QLabel("72")
    col.addWidget(dynamic)
    col.addWidget(number)
    set_language(LANG_EN)
    translate_tree(root)
    assert dynamic.text() == "心拍 72 BPM"
    assert number.text() == "72"


def test_translate_tree_follows_text_changed_after_first_walk(
    qapp: QApplication, small_table: dict[str, str]
) -> None:
    del qapp, small_table
    root = QWidget()
    col = QVBoxLayout(root)
    button = QPushButton("保存")
    col.addWidget(button)
    set_language(LANG_EN)
    translate_tree(root)
    assert button.text() == "Save"
    button.setText("設定")
    translate_tree(root)
    assert button.text() == "Settings"
    set_language(LANG_JA)
    translate_tree(root)
    assert button.text() == "設定"


def test_translate_tree_is_idempotent(qapp: QApplication, small_table: dict[str, str]) -> None:
    del qapp, small_table
    root = _build_tree()
    set_language(LANG_EN)
    translate_tree(root)
    translate_tree(root)
    assert root.button.text() == "Save"  # type: ignore[attr-defined]
    assert root.combo.itemText(0) == "Small"  # type: ignore[attr-defined]


# ---------------------------------------------------------------- 操作用ウィンドウ

JAPANESE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
CAL_TITLE = "心拍の補正（数字が合わないときだけ）"


@pytest.fixture(scope="module")
def shared_windows(
    qapp: QApplication, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[OperatorWindow, OutputWindow]]:
    """窓は 1 組だけ作って使い回す。

    操作用ウィンドウは作るたびにマイクと音の部品を開くので、数を増やすと全体の実行が
    Windows で不意に落ちる（テストごとに作ると増えすぎる）。
    """
    del qapp
    data = tmp_path_factory.mktemp("i18n_data")
    patch = pytest.MonkeyPatch()
    patch.setattr("stream_heartbeat.ui.operator_window.resolve_data_dir", lambda: data)
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    yield operator, output
    operator.close()
    output.close()
    patch.undo()


@pytest.fixture
def windows(
    shared_windows: tuple[OperatorWindow, OutputWindow],
) -> Iterator[tuple[OperatorWindow, OutputWindow]]:
    operator, output = shared_windows
    # 別のテストが英語のまま動かしたタイマーで、状態の帯が英語になっていることがある
    operator._set_detect_status()
    yield operator, output
    # 次のテストは日本語の画面から始める
    if language() != LANG_JA:
        operator._set_language(LANG_JA)


def _snapshot(window: QWidget) -> list[tuple]:
    """全部品の見える文字（ラベル・ボタン・枠・ツールチップ・コンボの項目）。"""
    rows: list[tuple] = []
    for widget in window.findChildren(QWidget):
        row: list[object] = [type(widget).__name__, widget.toolTip()]
        if isinstance(widget, (QLabel, QAbstractButton)):
            row.append(widget.text())
        if isinstance(widget, QGroupBox):
            row.append(widget.title())
        if isinstance(widget, QLineEdit):
            row.append(widget.placeholderText())
        if isinstance(widget, QComboBox) and not widget.property(SKIP_PROP):
            row.append([widget.itemText(i) for i in range(widget.count())])
        rows.append(tuple(row))
    return rows


def _profile_values(operator: OperatorWindow) -> dict:
    return asdict(operator._session.profile)


def test_language_button_text(windows: tuple[OperatorWindow, OutputWindow]) -> None:
    operator, _output = windows
    assert operator._lang_btn.text() == "English"


def test_language_button_text_when_starting_in_english(
    qapp: QApplication, tmp_path: Path
) -> None:
    del qapp, tmp_path
    set_language(LANG_EN)
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    try:
        assert operator._lang_btn.text() == "日本語"
        titles = [g.title() for g in operator.findChildren(QGroupBox)]
        assert "① Microphone" in titles
    finally:
        operator.close()
        output.close()


def test_language_button_is_right_of_calibration_fold(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    fold = next(
        b
        for b in operator.findChildren(QToolButton)
        if b.property(FOLD_TITLE_PROP) == CAL_TITLE
    )
    lang = operator._lang_btn
    assert lang.parentWidget() is fold.parentWidget()
    column = fold.parentWidget().layout()
    head = next(
        item.layout() for item in map(column.itemAt, range(column.count())) if item.layout()
    )
    assert head.indexOf(fold) == 0
    assert head.indexOf(lang) == 1


def test_switch_to_english_and_back_restores_everything(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    before = _snapshot(operator)
    values = _profile_values(operator)
    operator._lang_btn.click()
    assert language() == LANG_EN
    titles = [g.title() for g in operator.findChildren(QGroupBox)]
    assert titles[:2] == ["① Microphone", "② Style"]
    assert operator._lang_btn.text() == "日本語"
    assert _profile_values(operator) == values
    operator._lang_btn.click()
    assert language() == LANG_JA
    assert _snapshot(operator) == before
    assert _profile_values(operator) == values


def test_switch_saves_language(windows: tuple[OperatorWindow, OutputWindow]) -> None:
    operator, _output = windows
    operator._lang_btn.click()
    assert load_app_state(operator._data_dir)["language"] == "en"
    operator._lang_btn.click()
    assert load_app_state(operator._data_dir)["language"] == "ja"


def test_titles_stay_japanese_in_english(windows: tuple[OperatorWindow, OutputWindow]) -> None:
    operator, output = windows
    operator._lang_btn.click()
    assert operator.windowTitle() == OPERATOR_WINDOW_TITLE
    assert output.windowTitle() == OUTPUT_WINDOW_TITLE


def test_switch_during_calibration_keeps_tap_count(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    session = operator._session
    operator._begin_cal()
    for t in (1.0, 1.5, 2.0):
        assert session.tap(t)
    operator._tap_btn.setText(operator._tap_text())
    assert operator._tap_btn.text() == "拍  3"
    operator._lang_btn.click()
    assert operator._tap_btn.text() == "Beat  3"
    assert operator._cal_btn.text() == "Save calibration"
    operator._lang_btn.click()
    assert operator._tap_btn.text() == "拍  3"
    assert operator._cal_btn.text() == "補正を保存"


def test_profile_name_with_braces_is_safe(
    windows: tuple[OperatorWindow, OutputWindow], monkeypatch: pytest.MonkeyPatch
) -> None:
    operator, _output = windows
    operator._lang_btn.click()
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.QInputDialog.getText",
        lambda *args, **kwargs: ("{0}x}", True),
    )
    operator._save_as()
    assert operator._notice.text() == 'Saved as "{0}x}"'


def test_saved_color_not_in_list_survives_round_trip(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    profile = operator._session.profile
    original = profile.bpm_color
    profile.bpm_color = "#123456"
    operator._load_into_controls(profile)
    combo = operator._bpm_color
    try:
        assert combo.currentText() == "保存値 #123456"
        operator._lang_btn.click()
        assert combo.currentText() == "Saved value #123456"
        assert combo.currentData() == "#123456"
        operator._lang_btn.click()
        assert combo.currentText() == "保存値 #123456"
        assert combo.currentData() == "#123456"
    finally:
        profile.bpm_color = original
        operator._load_into_controls(profile)


def test_user_named_profile_is_not_translated(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    operator._profiles.addItem("背景")
    operator._lang_btn.click()
    names = [operator._profiles.itemText(i) for i in range(operator._profiles.count())]
    assert "背景" in names


def test_obs_hint_in_english_keeps_obs_title() -> None:
    set_language(LANG_EN)
    hint = obs_hint("green")
    assert OUTPUT_WINDOW_TITLE in hint
    assert "Chroma Key" in hint
    # OBS が探す題名のほかに、日本語は残らない
    assert not JAPANESE.search(hint.replace(OUTPUT_WINDOW_TITLE, ""))


def _items(combo: QComboBox) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())]


def test_style_combo_in_english(windows: tuple[OperatorWindow, OutputWindow]) -> None:
    operator, _output = windows
    data = [operator._style.itemData(i) for i in range(operator._style.count())]
    operator._lang_btn.click()
    items = _items(operator._style)
    assert not any(JAPANESE.search(text) for text in items)
    assert items[:3] == ["Realistic 1", "Realistic 2", "Realistic 3"]
    assert [operator._style.itemData(i) for i in range(operator._style.count())] == data


def test_effect_combo_is_rebuilt_in_current_language(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    original = operator._style.currentIndex()
    echo = next(
        i for i in range(operator._style.count()) if operator._style.itemData(i) == ("echo", "")
    )
    try:
        operator._lang_btn.click()
        operator._style.setCurrentIndex(echo)
        assert _items(operator._effect) == ["None", "Color Doppler", "Popping hearts"]
        operator._effect.setCurrentIndex(1)
        assert operator._effect_hint.text().startswith("Overlays blood flow")
        operator._lang_btn.click()
        assert _items(operator._effect) == ["なし", "カラードプラ", "はじけるハート"]
        assert operator._effect_hint.text().startswith("血の流れを色で重ねます")
    finally:
        operator._style.setCurrentIndex(original)
        operator._effect.setCurrentIndex(0)


def test_color_and_backdrop_combos_in_english(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    operator, _output = windows
    operator._lang_btn.click()
    for combo in (operator._beat_color, operator._beat_outline, operator._bpm_color):
        assert not any(JAPANESE.search(text) for text in _items(combo))
    assert _items(operator._backdrop) == ["Green (chroma key)", "White", "Black", "Transparent"]


def test_tap_label_in_english() -> None:
    set_language(LANG_EN)
    session = HeartSession()
    session.begin_calibration(0.0)
    assert session.tap_label() == "No beats yet (aim for 4 or more)"
    session.tap(1.0)
    assert session.tap_label() == "Beats 1 / 4"
    for t in (2.0, 3.0, 4.0):
        session.tap(t)
    assert session.tap_label() == "4 beats  about 60 BPM (OK to save)"
    set_language(LANG_JA)
    assert session.tap_label() == "拍 4 回  約 60 BPM（保存してOK）"


def test_splash_text_in_english() -> None:
    from stream_heartbeat.ui.splash import WAIT_TEXT

    set_language(LANG_EN)
    assert tr(WAIT_TEXT) == "Starting up. Please wait…"


# ---------------------------------------------------------------- VTube Studio 連携の欄


def _all_texts(root: QWidget) -> list[str]:
    """隠れている部品を含め、画面に出る文字をすべて集める。"""
    out: list[str] = []
    for widget in [root, *root.findChildren(QWidget)]:
        if widget.property(SKIP_PROP):
            continue
        out.append(widget.toolTip())
        if isinstance(widget, (QLabel, QAbstractButton)):
            out.append(widget.text())
        if isinstance(widget, QGroupBox):
            out.append(widget.title())
        if isinstance(widget, QLineEdit):
            out.append(widget.placeholderText())
        if isinstance(widget, QComboBox):
            out.extend(widget.itemText(i) for i in range(widget.count()))
    return out


def _japanese_left(root: QWidget) -> list[str]:
    return [text for text in _all_texts(root) if JAPANESE.search(text)]


def test_vts_panel_has_no_japanese_in_english(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    from stream_heartbeat.vts import (
        CONNECTING,
        DENIED,
        NO_VTS,
        OFF,
        READY,
        WAITING_USER,
    )

    operator, _output = windows
    panel = operator._vts
    profile = operator._session.profile
    style = profile.style
    operator._lang_btn.click()
    try:
        for state in (OFF, CONNECTING, WAITING_USER, NO_VTS, DENIED, READY):
            panel._client._state = state
            panel._on_state(state)
            assert _japanese_left(panel) == [], state
        panel._client._state = READY
        profile.style = "realistic"
        panel._heart.instance_id = None
        panel._refresh()
        assert _japanese_left(panel) == []  # 出していない
        panel._heart.instance_id = "inst1"
        panel._made_key = None
        panel._failed_key = None
        panel._refresh()
        assert _japanese_left(panel) == []  # 見た目が古い
        panel._failed_key = panel._look_key()
        panel._refresh()
        assert _japanese_left(panel) == []  # 古くて作り直せなかった
        panel._made_key = panel._look_key()
        panel._refresh()
        assert _japanese_left(panel) == []  # 出したが留めていない
        panel._heart.model_id = "m1"
        panel._heart.pins = {"m1": {}}
        panel._refresh()
        assert _japanese_left(panel) == []  # 留めた
        panel._heart._pick_done = lambda _pin: None
        panel._refresh()
        assert _japanese_left(panel) == []  # 留め待ち
        panel._heart._pick_done = None
        profile.style = "echo"
        panel._refresh()
        assert _japanese_left(panel) == []  # 出せないスタイル
    finally:
        panel._client._state = OFF
        panel._heart.instance_id = None
        panel._heart._pick_done = None
        panel._heart.model_id = ""
        panel._heart.pins = {}
        profile.style = style
        panel._on_state(OFF)


def test_style_names_in_english() -> None:
    from stream_heartbeat.render.heart_frames import ITEM_STYLES
    from stream_heartbeat.ui.vts_panel import style_names

    set_language(LANG_EN)
    assert style_names(ITEM_STYLES) == "Realistic 1–3, X-ray 3, Cute 1 & 2, Chic 1 & 2, Mechanical"
    assert style_names(ITEM_STYLES, translated=False).startswith("リアル1〜3")
    set_language(LANG_JA)
    assert style_names(ITEM_STYLES) == "リアル1〜3、レントゲン3、かわいい1・2、オシャレ1・2、機械"


def test_vts_panel_switch_updates_note_and_folder(
    windows: tuple[OperatorWindow, OutputWindow],
) -> None:
    from stream_heartbeat.vts import OFF, READY

    operator, _output = windows
    panel = operator._vts
    try:
        panel._client._state = READY
        panel._refresh()
        ja_note = panel._note.text()
        ja_folder = panel._folder.text()
        assert ja_note and ja_folder.startswith("書き出し先")
        operator._lang_btn.click()
        assert panel._note.text() != ja_note and not JAPANESE.search(panel._note.text())
        assert panel._folder.text().startswith("Export folder")
        assert panel._how_to.text().startswith("[Setup (first time only)]")
        assert panel._trouble.text().startswith('- "Cannot connect to VTube Studio"')
        operator._lang_btn.click()
        assert panel._note.text() == ja_note
        assert panel._folder.text() == ja_folder
        assert panel._how_to.text().startswith("【準備（はじめの 1 回だけ）】")
    finally:
        panel._client._state = OFF
        panel._refresh()
