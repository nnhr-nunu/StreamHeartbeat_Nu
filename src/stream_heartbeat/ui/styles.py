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
QPushButton:hover, QToolButton:hover {
  background: #3a3a3a;
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
  padding-right: 26px;
}
QComboBox::drop-down {
  subcontrol-origin: border;
  subcontrol-position: center right;
  width: 22px;
  border: none;
  background: transparent;
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
"""
