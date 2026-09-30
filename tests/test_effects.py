"""心臓わしづかみ・聴診器 1・2 の演出（選べるスタイル・動き・描く場所・操作）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMatrix4x4, QPainter, QVector3D
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.heart_gl import ANATOMY_YAW_DEG
from stream_heartbeat.render.heart_mesh import (
    ANATOMY_ROLL_DEG,
    FLOATS_PER_VERTEX,
    build_heart_mesh,
)
from stream_heartbeat.render.heart_shaders import STYLE_LOOKS
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.effect_grip import hand_image, paint_grip_hand
from stream_heartbeat.ui.effect_stetho import paint_stethoscope
from stream_heartbeat.ui.effects import (
    BODY_CENTER,
    BODY_HALF,
    EFFECT_GRIP,
    EFFECT_NONE,
    EFFECT_STETHO,
    EFFECT_STETHO_FLIP,
    GRIP_MIN_HOLD_S,
    EffectMotion,
    active_effect,
    effect_choices,
    gl_heart_frame,
    grip_squash,
)
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


@pytest.fixture(autouse=True)
def _isolate_operator_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )


def test_grip_only_for_xray_and_stetho_for_heart_styles() -> None:
    for style in ("xray", "xray_heart"):
        keys = [key for key, _label in effect_choices(style)]
        assert keys == [EFFECT_NONE, EFFECT_GRIP, EFFECT_STETHO, EFFECT_STETHO_FLIP]
    for style in ("realistic", "mech", "cute"):
        keys = [key for key, _label in effect_choices(style)]
        assert keys == [EFFECT_NONE, EFFECT_STETHO, EFFECT_STETHO_FLIP]
    labels = [label for _key, label in effect_choices("realistic")]
    assert labels[1:] == ["聴診器1", "聴診器2"]
    for style in ("echo", "mri", "ecg"):
        assert [key for key, _label in effect_choices(style)] == [EFFECT_NONE]
    # 対応しないスタイルでは描かないが、選んだ値は捨てない
    assert active_effect("realistic", EFFECT_GRIP) == EFFECT_NONE
    assert active_effect("xray_heart", EFFECT_GRIP) == EFFECT_GRIP


def test_click_squeezes_briefly_and_hold_keeps_squeezing() -> None:
    motion = EffectMotion()
    now = 10.0
    motion.step(now, (0.5, 0.5))
    motion.press(now)
    motion.release()
    for _ in range(10):
        now += 0.016
        motion.step(now, (0.5, 0.5))
    # 一瞬のクリックでも、しばらくはしっかり握る
    assert motion.grip > 0.8
    for _ in range(120):
        now += 0.016
        motion.step(now, (0.5, 0.5))
    assert motion.grip == 0.0
    motion.press(now)
    for _ in range(int(GRIP_MIN_HOLD_S / 0.016) + 40):
        now += 0.016
        motion.step(now, (0.5, 0.5))
    assert motion.grip > 0.99
    sx, sy = grip_squash(motion.grip)
    assert sx < 1.0 < sy


def test_stetho_follows_mouse_and_returns_to_rest() -> None:
    motion = EffectMotion()
    now = 0.0
    motion.step(now, (0.3, 0.3))
    assert motion.stetho == (0.3, 0.3)
    motion.hover((0.8, 0.7))
    for _ in range(30):
        now += 0.016
        motion.step(now, (0.3, 0.3))
    assert motion.stetho is not None
    assert abs(motion.stetho[0] - 0.8) < 0.01 and abs(motion.stetho[1] - 0.7) < 0.01
    motion.hover(None)
    for _ in range(150):
        now += 0.016
        motion.step(now, (0.3, 0.3))
    assert abs(motion.stetho[0] - 0.3) < 0.01 and abs(motion.stetho[1] - 0.3) < 0.01


def test_body_constants_match_mesh() -> None:
    """手と聴診器の置き場所に使う胴の中心と大きさが、立体の形と合っている。"""
    mesh = build_heart_mesh(rows=36, cols=56)
    model = QMatrix4x4()
    model.rotate(ANATOMY_YAW_DEG, 0.0, 1.0, 0.0)
    model.rotate(ANATOMY_ROLL_DEG, 0.0, 0.0, 1.0)
    xs: list[float] = []
    ys: list[float] = []
    data = mesh.data
    for i in range(0, mesh.tube_start, 3):
        at = i * FLOATS_PER_VERTEX
        p = model.map(QVector3D(data[at], data[at + 1], data[at + 2]))
        xs.append(p.x())
        ys.append(p.y())
    center = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)
    half = ((max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0)
    assert abs(center[0] - BODY_CENTER[0]) < 0.06
    assert abs(center[1] - BODY_CENTER[1]) < 0.06
    assert abs(half[0] - BODY_HALF[0]) < 0.08
    assert abs(half[1] - BODY_HALF[1]) < 0.08


def _skin_like(color: QColor) -> bool:
    return color.red() > 180 and 120 < color.green() < 230 and color.blue() < 200


def test_hand_and_stetho_paint_on_heart(qapp: QApplication) -> None:
    del qapp
    # 手の素材は配布物にも入る場所にある
    assert not hand_image().isNull()
    rect = QRectF(0, 0, 400, 400)
    green = QColor(0, 177, 64)
    cycle = BeatClock().cycle(0.5)
    image = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)
    for scale in (0.7, 0.25):
        frame = gl_heart_frame(rect, scale, STYLE_LOOKS["xray_heart"])
        for grip in (0.0, 1.0):
            image.fill(green)
            painter = QPainter(image)
            paint_grip_hand(painter, rect, frame, cycle, grip=grip, time_s=0.5, opacity=1.0)
            painter.end()
            # 手の甲は心臓の真ん中の少し下に当たり、袖は窓の下（視聴者の側）の端まで届く
            center = frame.center
            below = int(center.y() + frame.radius * 0.5)
            assert any(
                _skin_like(image.pixelColor(int(center.x()) + dx, below))
                for dx in range(-30, 31, 3)
            ), (scale, grip)
            assert any(image.pixelColor(x, 398) != green for x in range(0, 400, 2)), (scale, grip)
            assert all(image.pixelColor(x, 1) == green for x in range(0, 400, 8))

    frame = gl_heart_frame(rect, 0.7, STYLE_LOOKS["xray_heart"])
    for back_view in (True, False):
        image.fill(green)
        painter = QPainter(image)
        paint_stethoscope(
            painter,
            rect,
            QPointF(220, 240),
            frame,
            cycle,
            time_s=0.5,
            opacity=1.0,
            back_view=back_view,
        )
        painter.end()
        # チェストピースは当てた所に描かれ、管は窓の下（視聴者の側）へ抜ける
        assert image.pixelColor(220, 240) != green
        assert any(image.pixelColor(x, 398) != green for x in range(0, 400, 2))
        assert all(image.pixelColor(x, 1) == green for x in range(0, 400, 8))


def _open(profile: HeartProfile) -> tuple[OperatorWindow, OutputWindow]:
    session = HeartSession(profile)
    output = OutputWindow(session)
    return OperatorWindow(session, output), output


def _effect_keys(operator: OperatorWindow) -> list[str]:
    combo = operator._effect
    return [combo.itemData(i) for i in range(combo.count())]


def test_effect_combo_follows_style_and_keeps_choice(qapp: QApplication) -> None:
    del qapp
    profile = HeartProfile(style="xray_heart", effect=EFFECT_GRIP)
    operator, output = _open(profile)
    assert _effect_keys(operator) == [EFFECT_NONE, EFFECT_GRIP, EFFECT_STETHO, EFFECT_STETHO_FLIP]
    assert operator._effect.currentData() == EFFECT_GRIP
    # 掴んでいる間は正面に固定するので、向きの操作は隠す
    assert operator._angle_wrap.isHidden()
    # リアルにすると手は選べない。値は残り、レントゲンへ戻すとまた出る
    operator._select_style("realistic", "surgical")
    assert _effect_keys(operator) == [EFFECT_NONE, EFFECT_STETHO, EFFECT_STETHO_FLIP]
    assert operator._effect.currentData() == EFFECT_NONE
    assert profile.effect == EFFECT_GRIP
    assert output.canvas.effect == EFFECT_NONE
    operator._select_style("xray_heart", "")
    assert operator._effect.currentData() == EFFECT_GRIP
    assert output.canvas.effect == EFFECT_GRIP
    # 選び直すとプロファイルに入る
    operator._effect.setCurrentIndex(_effect_keys(operator).index(EFFECT_STETHO))
    assert profile.effect == EFFECT_STETHO
    assert not operator._angle_wrap.isHidden()
    operator.close()


def test_grip_click_squeezes_and_disables_rotation(qapp: QApplication, qtbot) -> None:  # noqa: ANN001
    del qapp
    profile = HeartProfile(style="xray_heart", effect=EFFECT_GRIP)
    operator, output = _open(profile)
    canvas = output.canvas
    canvas.resize(300, 300)
    assert not canvas._can_rotate()
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas.rect().center())
    assert canvas._motion.squeezing
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas.rect().center())
    assert not canvas._motion.squeezing
    operator.close()


def test_stetho_click_places_rest_position(qapp: QApplication, qtbot) -> None:  # noqa: ANN001
    del qapp
    profile = HeartProfile(style="cute", effect=EFFECT_STETHO_FLIP)
    operator, output = _open(profile)
    canvas = output.canvas
    canvas.resize(400, 400)
    spot = canvas.rect().topLeft() + canvas.rect().center() / 2
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=spot)
    assert abs(profile.stetho_x - spot.x() / 400) < 0.01
    assert abs(profile.stetho_y - spot.y() / 400) < 0.01
    operator.close()
