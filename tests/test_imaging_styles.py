from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QComboBox

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.config import CHROMA_HEX
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.heart_cute import CUTE_BASE, CUTE_DEEP
from stream_heartbeat.ui.heart_echo import ECHO_BRIGHT, ECHO_MYO
from stream_heartbeat.ui.heart_imaging import (
    MRI_BLOOD,
    MRI_TISSUE,
    XRAY_BONE,
    XRAY_HEART,
)
from stream_heartbeat.ui.heart_paint import (
    GL_STYLES,
    paint_backdrop,
    paint_heart,
    paint_overlay,
)
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


def test_palettes_avoid_chroma_green() -> None:
    for color in (
        ECHO_BRIGHT,
        ECHO_MYO,
        MRI_BLOOD,
        MRI_TISSUE,
        XRAY_BONE,
        XRAY_HEART,
        CUTE_BASE,
        CUTE_DEEP,
    ):
        _assert_not_chroma(color)


def test_operator_lists_all_styles(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del qapp
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )
    keys = [key for key, _label in STYLES]
    assert keys == ["realistic", "echo", "mri", "xray", "cute", "mech", "ecg"]
    assert GL_STYLES == {"realistic", "mech", "xray", "mri"}
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


def _render_2d(style: str) -> QImage:
    image = QImage(240, 240, QImage.Format.Format_RGB32)
    image.fill(CHROMA)
    painter = QPainter(image)
    rect = QRectF(0, 0, 240, 240)
    clock = BeatClock()
    clock.feed_beat(0.0)
    clock.feed_beat(0.8)
    paint_backdrop(painter, rect, style=style, scale=1.0, opacity=1.0)
    paint_heart(
        painter,
        rect,
        style=style,
        scale=1.0,
        opacity=1.0,
        cycle=_cycle(),
        clock=clock,
        now=1.0,
    )
    paint_overlay(painter, rect, style=style, opacity=1.0, cycle=_cycle())
    painter.end()
    return image


def _paints_over_chroma(style: str, qapp: QApplication) -> None:
    del qapp
    image = _render_2d(style)
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


def test_mri_panel_not_chroma(qapp: QApplication) -> None:
    _paints_over_chroma("mri", qapp)


def test_xray_panel_not_chroma(qapp: QApplication) -> None:
    _paints_over_chroma("xray", qapp)


def test_cute_and_ecg_paint_over_chroma(qapp: QApplication) -> None:
    _paints_over_chroma("cute", qapp)
    _paints_over_chroma("ecg", qapp)


def test_imaging_panels_are_dark_not_green(qapp: QApplication) -> None:
    del qapp
    for style in ("xray", "mri"):
        image = _render_2d(style)
        center = image.pixelColor(120, 120)
        assert center.green() < 200, style
        corner = image.pixelColor(2, 2)
        assert corner == CHROMA, style
