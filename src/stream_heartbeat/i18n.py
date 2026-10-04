"""日本語 / English の切り替え。

画面の文字は日本語の原文のままコードに書き、英語のときだけ `EN`（原文 → 英訳）で引く。
- `tr(原文, **値)`: 実行中に作る文字（通知・状態・ダイアログ）に使う。
- `translate_tree(窓)`: 作ってある部品（ラベル・ボタン・枠・ツールチップ・コンボの項目）を
  今の言語に付け替える。言語を変えたときと、窓を作った直後に呼ぶ。

英訳が無い文字は日本語のまま出す（落ちない）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from stream_heartbeat.i18n_en import EN_GENERAL
from stream_heartbeat.i18n_en_vts import EN_VTS

LANG_JA = "ja"
LANG_EN = "en"
_LANGUAGES = (LANG_JA, LANG_EN)

# 原文（日本語） → 英訳
EN: dict[str, str] = {**EN_GENERAL, **EN_VTS}

# 部品ごとに「作ったときの日本語」を覚えておく名前（英語から日本語へ戻すため）
_TEXT_PROP = "i18n_text"
_TIP_PROP = "i18n_tip"
_HINT_PROP = "i18n_hint"
# 利用者のデータ（プロファイル名・マイク名）を入れた部品は、原文と偶然同じでも付け替えない
SKIP_PROP = "i18n_skip"
# 折りたたみ見出しは「▶/▼ + 題名」と組むので、題名の原文を別に持つ
FOLD_TITLE_PROP = "fold_title"
_ITEM_SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 100

_lang = LANG_JA


def _build_reverse(table: dict[str, str]) -> dict[str, str]:
    """英訳 → 原文。英訳が同じ原文が複数あるときは先のもの（部品が覚えた原文が優先される）。"""
    reverse: dict[str, str] = {}
    for source, english in table.items():
        reverse.setdefault(english, source)
    return reverse


_REVERSE = _build_reverse(EN)


def language() -> str:
    return _lang


def set_language(lang: str) -> None:
    """知らない値は日本語にする。"""
    global _lang
    _lang = lang if lang in _LANGUAGES else LANG_JA


def detect_language(saved: object, locale_name: str) -> str:
    """保存した言語があればそれ、無ければ OS の言語（日本語なら日本語、それ以外は英語）。"""
    if saved in _LANGUAGES:
        return str(saved)
    return LANG_JA if locale_name.lower().startswith("ja") else LANG_EN


def init_language(data_dir: Path | None = None) -> str:
    """起動時に言語を決めて使い始める。壊れた保存でも落ちない。"""
    from stream_heartbeat.profile import load_app_state

    saved = load_app_state(data_dir).get("language")
    lang = detect_language(saved, QLocale.system().name())
    set_language(lang)
    return lang


def other_language_label() -> str:
    """言語ボタンの文字。押した先の言語の名前（翻訳しない）。"""
    return "English" if _lang == LANG_JA else "日本語"


def tr(text: str, **fmt: object) -> str:
    """原文を今の言語の文字にする。`fmt` があれば、訳したあとのひな形だけを `format` する。"""
    out = EN.get(text, text) if _lang == LANG_EN else text
    return out.format(**fmt) if fmt else out


def _source_of(current: str, stored: object) -> str | None:
    """いまの文字の原文。実行中に作られた文（表に無い文字）は None で、触らない。"""
    if isinstance(stored, str) and stored and current in (stored, EN.get(stored)):
        return stored
    if current in EN:
        return current
    return _REVERSE.get(current)


def _retext(widget: QWidget, prop: str, current: str, apply: object) -> None:
    source = _source_of(current, widget.property(prop))
    if source is None:
        return
    widget.setProperty(prop, source)
    new = tr(source)
    if new != current:
        apply(new)  # type: ignore[operator]


def _fold_text(button: QToolButton, title: str) -> str:
    return f"{'▼' if button.isChecked() else '▶'} {tr(title)}"


def translate_tree(root: QWidget) -> None:
    """`root` 以下の部品の文字を、今の言語に付け替える。何度呼んでもよい。"""
    for widget in [root, *root.findChildren(QWidget)]:
        if widget.property(SKIP_PROP):
            continue
        if widget.toolTip():
            _retext(widget, _TIP_PROP, widget.toolTip(), widget.setToolTip)
        fold_title = widget.property(FOLD_TITLE_PROP)
        if isinstance(widget, QToolButton) and isinstance(fold_title, str):
            widget.setText(_fold_text(widget, fold_title))
        elif isinstance(widget, (QLabel, QAbstractButton)):
            if widget.text():
                _retext(widget, _TEXT_PROP, widget.text(), widget.setText)
        elif isinstance(widget, QGroupBox):
            if widget.title():
                _retext(widget, _TEXT_PROP, widget.title(), widget.setTitle)
        elif isinstance(widget, QLineEdit):
            if widget.placeholderText():
                _retext(widget, _HINT_PROP, widget.placeholderText(), widget.setPlaceholderText)
        elif isinstance(widget, QComboBox):
            _retranslate_combo(widget)


def _retranslate_combo(combo: QComboBox) -> None:
    for i in range(combo.count()):
        current = combo.itemText(i)
        source = _source_of(current, combo.itemData(i, _ITEM_SOURCE_ROLE))
        if source is None:
            continue
        combo.setItemData(i, source, _ITEM_SOURCE_ROLE)
        new = tr(source)
        if new != current:
            combo.setItemText(i, new)
