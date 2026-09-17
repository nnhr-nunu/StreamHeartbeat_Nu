"""アプリアイコン PNG / ICO を生成する。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication


def _heart(cx: float, cy: float, s: float) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(cx, cy + 0.36 * s)
    path.cubicTo(cx + 0.95 * s, cy - 0.1 * s, cx + 0.5 * s, cy - 0.88 * s, cx, cy - 0.28 * s)
    path.cubicTo(cx - 0.5 * s, cy - 0.88 * s, cx - 0.95 * s, cy - 0.1 * s, cx, cy + 0.36 * s)
    path.closeSubpath()
    return path


def main() -> int:
    app = QApplication(sys.argv)
    del app
    out = Path(__file__).resolve().parents[1] / "src" / "stream_heartbeat" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    img = QImage(256, 256, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(168, 28, 36))
    painter.setPen(QPen(QColor(72, 8, 14), 8))
    painter.drawPath(_heart(128, 132, 96))
    painter.setBrush(QColor(255, 180, 160, 120))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QPointF(104, 108), 18, 12)
    painter.end()
    png = out / "app_icon.png"
    ico = out / "app_icon.ico"
    img.save(str(png))
    img.save(str(ico))
    print(png)
    print(ico)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
