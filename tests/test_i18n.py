"""日本語 / English 切り替えの核（tr・言語の決め方・画面の付け替え）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat import i18n
from stream_heartbeat.i18n import (
    LANG_EN,
    LANG_JA,
    detect_language,
    init_language,
    language,
    other_language_label,
    set_language,
    tr,
    translate_tree,
)
from stream_heartbeat.profile import STATE_FILENAME
from stream_heartbeat.ui.fold import fold_toggle


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
