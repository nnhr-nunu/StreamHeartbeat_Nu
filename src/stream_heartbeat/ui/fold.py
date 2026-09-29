"""見出しを押すと中身を開け閉めできる欄（操作画面の各所で使う）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


def make_fold(
    title: str, inner: QWidget, *, expanded: bool = False
) -> tuple[QWidget, QToolButton]:
    toggle = QToolButton()
    toggle.setObjectName("fold")
    toggle.setCheckable(True)
    toggle.setChecked(expanded)
    toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    toggle.setArrowType(Qt.ArrowType.NoArrow)
    inner.setVisible(expanded)

    def _sync(on: bool) -> None:
        inner.setVisible(on)
        toggle.setText(f"{'▼' if on else '▶'} {title}")

    toggle.toggled.connect(_sync)
    _sync(expanded)
    wrap = QWidget()
    layout = QVBoxLayout(wrap)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(toggle)
    layout.addWidget(inner)
    return wrap, toggle
