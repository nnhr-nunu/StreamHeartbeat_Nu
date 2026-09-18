from __future__ import annotations

from pathlib import Path

_COMBO_ARROW_URL = (
    "file:///"
    + (Path(__file__).resolve().parent.parent / "assets" / "combo_down.svg").as_posix()
)

DARK_QSS = """
QMainWindow, QDialog {
  background: #121212;
  color: #e8e8e8;
  font-size: 14px;
}
QMainWindow > QWidget, QDialog > QWidget {
  background: #121212;
  color: #e8e8e8;
}
QWidget {
  color: #e8e8e8;
  font-size: 14px;
}
QLabel, QCheckBox, QGroupBox, QFormLayout {
  background: transparent;
}
QToolButton, QPushButton {
  background: #2a2a2a;
  border: none;
  border-radius: 10px;
  padding: 6px 10px;
  min-height: 32px;
  color: #f0f0f0;
}
QToolButton#fold {
  text-align: left;
  padding-left: 10px;
  min-height: 36px;
}
QPushButton:hover, QToolButton:hover {
  background: #3a3a3a;
}
QPushButton#tap {
  background: #5a3d7a;
  min-height: 44px;
  font-size: 16px;
  font-weight: 600;
}
QPushButton#tap:hover {
  background: #6b4c8c;
}
QPushButton#tap:disabled {
  background: #2a2a2a;
  color: #777;
}
QSlider::groove:horizontal {
  height: 6px;
  background: #333;
  border-radius: 3px;
}
QSlider::handle:horizontal {
  width: 16px;
  margin: -6px 0;
  background: #c9a0ff;
  border-radius: 8px;
}
QCheckBox { spacing: 6px; padding: 2px 6px 2px 2px; }
QComboBox, QLineEdit {
  background: #1b1b1b;
  color: #e8e8e8;
  border: 1px solid #555;
  border-radius: 8px;
  padding: 6px 10px;
  min-height: 28px;
}
QComboBox {
  padding-right: 28px;
}
QComboBox::drop-down {
  subcontrol-origin: border;
  subcontrol-position: center right;
  width: 24px;
  border: none;
  background: transparent;
}
QComboBox::down-arrow {
  image: url("__COMBO_ARROW__");
  width: 10px;
  height: 6px;
}
QComboBox QAbstractItemView {
  background: #1b1b1b;
  color: #e8e8e8;
  selection-background-color: #3d2a4f;
  border: 1px solid #555;
}
QGroupBox {
  border: 1px solid #333;
  border-radius: 10px;
  margin-top: 12px;
  padding: 8px 8px 6px 8px;
  color: #e8e8e8;
  background: transparent;
}
QGroupBox::title {
  subcontrol-origin: margin;
  left: 12px;
  padding: 0 6px;
  color: #c9a0ff;
  background: transparent;
}
QLabel#status {
  color: #e8e8e8;
  font-size: 15px;
}
QLabel#live {
  color: #8ee0a8;
  font-size: 16px;
  font-weight: 600;
}
QLabel#preview {
  color: #e0c07a;
  font-size: 15px;
}
QLabel#warn {
  color: #e8a070;
}
QLabel#disclaimer {
  color: #bdbdbd;
  font-size: 12px;
}
QLabel#meta {
  color: #9a9a9a;
  font-size: 12px;
}
""".replace("__COMBO_ARROW__", _COMBO_ARROW_URL)
