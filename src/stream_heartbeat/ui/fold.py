"""見出しを押すと中身を開け閉めできる欄（操作画面の各所で使う）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget


def fold_toggle(title: str, inner: QWidget, *, expanded: bool = False) -> QToolButton:
    """押すと inner を出し入れする見出しボタン（置き場所は呼ぶ側が決める）。"""
    toggle = QToolButton()
    toggle.setObjectName("fold")
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    toggle.setArrowType(Qt.ArrowType.NoArrow)

    def _sync(on: bool) -> None:
        inner.setVisible(on)
        toggle.setText(f"{'▼' if on else '▶'} {title}")

    toggle.toggled.connect(_sync)
    _sync(expanded)
    return toggle


def make_fold(
    title: str, inner: QWidget, *, expanded: bool = False
) -> tuple[QWidget, QToolButton]:
    toggle = fold_toggle(title, inner, expanded=expanded)
    wrap = QWidget()
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(toggle)
    layout.addWidget(inner)
    return wrap, toggle


def make_fold_row(folds: list[tuple[str, QWidget]]) -> tuple[QWidget, list[QToolButton]]:
    """見出しボタンを横に並べ、中身はその下に出す。一度に開くのは 1 つだけ。"""
    toggles = [fold_toggle(title, inner) for title, inner in folds]
    for toggle in toggles:
        others = [t for t in toggles if t is not toggle]

        def _close_others(on: bool, others: list[QToolButton] = others) -> None:
            if on:
                for other in others:
                    other.setChecked(False)

        toggle.toggled.connect(_close_others)
    wrap = QWidget()
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    row = QHBoxLayout()
    for toggle in toggles:
        row.addWidget(toggle)
    row.addStretch(1)
    layout.addLayout(row)
    for _title, inner in folds:
        layout.addWidget(inner)
    return wrap, toggles
