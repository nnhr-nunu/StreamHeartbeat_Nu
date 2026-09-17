from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QComboBox

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.config import CHROMA_HEX
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.heart_imaging import (
    ECHO_BRIGHT,
    MRI_BLOOD,
    MRI_TISSUE,
    XRAY_BONE,
    XRAY_HEART,
)
from stream_heartbeat.ui.heart_paint import paint_heart
from stream_heartbeat.ui.operator_window import STYLES, OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow

CHROMA = QColor(CHROMA_HEX)


def _cycle() -> CardiacCycle:
    return CardiacCycle(
        squeeze=0.55,
        eject=0.4,
        fill=0.2,
        apex=0.82,
        waist=1.06,
        sheen=0.5,
        age=0.08,
    )


def _assert_not_chroma(color: QColor) -> None:
    assert color.name().lower() != CHROMA_HEX.lower()
    assert not (color.red() == 0 and color.green() == 255 and color.blue() == 0)


def test_imaging_palette_avoids_chroma_green() -> None:
    for color in (ECHO_BRIGHT, MRI_BLOOD, MRI_TISSUE, XRAY_BONE, XRAY_HEART):
        _assert_not_chroma(color)


def test_operator_lists_echo_mri_xray(qapp: QApplication) -> None:
    del qapp
    keys = [key for key, _label in STYLES]
    assert keys == ["realistic", "echo", "mri", "xray", "cute", "mech", "ecg"]
    session = HeartSession()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    style = next(
        box
        for box in operator.findChildren(QComboBox)
        if any(box.itemText(i) == "心エコー" for i in range(box.count()))
    )
    labels = [style.itemText(i) for i in range(style.count())]
    assert "心エコー" in labels
    assert "MRI" in labels
    assert "レントゲン" in labels
    operator.close()
    output.close()


def _paints_over_chroma(style: str, qapp: QApplication) -> None:
    del qapp
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    image.fill(CHROMA)
    painter = QPainter(image)
    paint_heart(
        painter,
        QRectF(0, 0, 240, 240),
        style=style,
        scale=1.0,
        opacity=1.0,
        cycle=_cycle(),
        ecg_phase=0.0,
    )
    painter.end()
    found = False
    for y in range(24, 216, 6):
        for x in range(24, 216, 6):
            pixel = image.pixelColor(x, y)
            if pixel != CHROMA:
                found = True
                _assert_not_chroma(pixel)
    assert found, f"{style} が緑のまま"


def test_echo_paints_sector_not_chroma(qapp: QApplication) -> None:
    _paints_over_chroma("echo", qapp)


def test_mri_paints_torso_not_chroma(qapp: QApplication) -> None:
    _paints_over_chroma("mri", qapp)


def test_xray_paints_chest_not_chroma(qapp: QApplication) -> None:
    _paints_over_chroma("xray", qapp)
