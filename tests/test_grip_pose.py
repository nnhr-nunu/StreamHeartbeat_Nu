"""心臓わしづかみの手の形（心臓の胴へ巻き付ける・鼓動で一緒に動く・指で心臓が凹む）。"""

from __future__ import annotations

import math

import pytest
from PySide6.QtGui import QColor, QMatrix4x4, QVector3D, QVector4D
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.render.grip_pose import (
    BODY_CENTER,
    BODY_DEPTH,
    FINGERS,
    HandPose,
    arc_angle,
    arc_length,
    arc_radius,
    grip_pose,
    held_grip,
    rim_at,
    skin,
    unwrap,
    wrap,
    wrap_weight,
)
from stream_heartbeat.render.hand_morph import CLAW_PAIRS, MORPH_LIMIT_V, claw_point
from stream_heartbeat.render.heart_gl import ANATOMY_YAW_DEG
from stream_heartbeat.render.heart_mesh import (
    ANATOMY_ROLL_DEG,
    FLOATS_PER_VERTEX,
    build_heart_mesh,
)
from stream_heartbeat.render.heart_shaders import STYLE_LOOKS

LOOK = STYLE_LOOKS["xray_heart"]
SIZE = 0.7


def _pose(cycle: CardiacCycle, grip: float = 0.0) -> HandPose:
    return grip_pose(
        shift=(LOOK.shift_x, LOOK.shift_y), size=SIZE, cycle=cycle, grip=grip, time_s=0.0
    )


def _rest() -> CardiacCycle:
    return BeatClock().cycle(0.7)


def test_body_outline_matches_mesh() -> None:
    """手を巻き付ける胴の輪郭と奥行きが、立体の心臓の形と合っている。"""
    mesh = build_heart_mesh(rows=36, cols=56)
    model = QMatrix4x4()
    model.rotate(ANATOMY_YAW_DEG, 0.0, 1.0, 0.0)
    model.rotate(ANATOMY_ROLL_DEG, 0.0, 0.0, 1.0)
    bins = 36
    reach = [0.0] * bins
    front = -9.0
    back = 9.0
    data = mesh.data
    for i in range(0, mesh.tube_start, 2):
        at = i * FLOATS_PER_VERTEX
        p = model.map(QVector3D(data[at], data[at + 1], data[at + 2]))
        dx = p.x() - BODY_CENTER[0]
        dy = p.y() - BODY_CENTER[1]
        r = math.hypot(dx, dy)
        k = int((math.atan2(dy, dx) + math.pi) / (2.0 * math.pi) * bins) % bins
        reach[k] = max(reach[k], r)
        if r < 0.15:
            front = max(front, p.z())
            back = min(back, p.z())
    for k in range(bins):
        phi = -math.pi + (k + 0.5) * 2.0 * math.pi / bins
        assert abs(rim_at(phi) - reach[k]) < 0.09, math.degrees(phi)
    assert abs((front - back) / 2.0 - BODY_DEPTH) < 0.06


def test_wrap_and_unwrap_are_inverse_and_keep_true_size_in_front() -> None:
    for fx, fy in ((0.0, 0.0), (0.3, -0.5), (-0.9, 0.4), (0.2, 1.4), (-1.3, -0.2)):
        x, y, z, _facing = wrap(fx, fy)
        back = unwrap(x, y, z)
        assert abs(back[0] - fx) < 1e-6 and abs(back[1] - fy) < 1e-6
    # 正面のてっぺんは胴の手前の面、輪郭までの表面の長さを進むと真横（向き 0）
    assert wrap(0.0, 0.0)[2:] == pytest.approx((BODY_DEPTH, 1.0))
    for phi in (0.3, 1.6, 2.8, -1.0):
        r = rim_at(phi)
        rim = arc_radius(r) * math.pi / 2.0
        x, y, _z, facing = wrap(rim * math.cos(phi), rim * math.sin(phi))
        assert abs(facing) < 1e-6
        assert math.hypot(x, y) == pytest.approx(r)
        assert arc_angle(arc_length(1.1, r), r) == pytest.approx(1.1)
    # 正面に貼った手は大きく写らない（表面の長さ = 画面の上の長さ）
    assert wrap(0.05, 0.0)[0] == pytest.approx(0.05, rel=0.01)


def test_fingertips_stay_in_front_and_grip_turns_into_the_claw() -> None:
    rest = _pose(_rest())
    held = _pose(_rest(), grip=1.0)
    for i in range(1, 5):
        # 指の付け根は心臓の正面に載り、指先は丸みに沿って縁の方へ這う
        assert rest.finger_facing(i, 0.0) > 0.5, i
        assert rest.finger_facing(i, 1.0) < 0.6, i
    # 長い人差し指・中指は縁の近くまで届く
    assert rest.finger_facing(1, 1.0) < 0.3 and rest.finger_facing(2, 1.0) < 0.35
    # 親指は左の縁の近くまで届く
    tip = rest.sheet_point(*rest.finger_tip(0))
    assert tip[0] < -0.6 and rest.finger_facing(0, 1.0) < 0.7
    # 指先は縁を越えて奥へ回らない（心臓に隠れて指先が切れたように見えない）。
    # 開いた手・握る途中・握り切った手のどれでも、拍のどの時点でも
    clock = BeatClock()
    for grip in (0.0, 0.5, 1.0):
        for k in range(24):
            pose = _pose(clock.cycle(k * clock.interval() / 24), grip=grip)
            for i in range(5):
                assert pose.finger_facing(i, 1.0) > 0.12, (grip, k, i)
    # 握り切ると握った手の絵で描く。巻き付けは少しだけ弱め、指は心臓の丸みに載ったまま
    assert held.morph == 1.0 and held.blend == pytest.approx(1.0) and 0.0 < held.flatten < 0.5
    for i in range(1, 5):
        assert 0.3 < held.finger_facing(i, 1.0) < 0.9, i
    # 握ると手が心臓に食い込みながら少し上へ滑る
    assert held.anchor[1] > rest.anchor[1]
    # 鼓動の握り直し程度では絵は替わらない（開いた手のまま指が少し曲がる）
    systole = _pose(BeatClock().cycle(0.05))
    assert 0.2 < systole.morph < 0.4 and systole.blend == 0.0


def test_claw_morph_follows_the_outline_pairs() -> None:
    """開いた手の対応点は握った手の対応点へ動き、袖は動かない。"""
    for (u, v), (cu, cv) in CLAW_PAIRS:
        mu, mv = claw_point(u, v)
        assert math.hypot(mu - cu, mv - cv) < 4.0, (u, v)
    assert claw_point(500.0, MORPH_LIMIT_V + 10.0) == (500.0, MORPH_LIMIT_V + 10.0)
    # 指先は握った手の指の上の端（付け根より上）へ寄る
    for (kx, ky), (tx, ty), _half in FINGERS[1:]:
        assert claw_point(tx, ty)[1] > ty + 40.0
        assert claw_point(tx, ty)[1] < claw_point(kx, ky)[1] - 120.0


def test_hand_follows_the_heart_beat() -> None:
    clock = BeatClock()
    rest = _pose(clock.cycle(0.7))
    squeeze = clock.cycle(0.05)
    fill = clock.cycle(0.38)
    systole = _pose(squeeze)
    diastole = _pose(fill)
    # ドッ: 心臓が縮みながら左へ寄るので、手も一緒に寄り、握りが締まる
    assert systole.center[0] < rest.center[0] - 0.02
    assert systole.body[0] < rest.body[0]
    assert held_grip(0.0, squeeze) > 0.25 and systole.grip > rest.grip
    assert systole.anchor[1] > rest.anchor[1]
    # 充満: 心臓に押し返されて指が開く
    assert abs(diastole.fan[0]) > abs(rest.fan[0])
    assert abs(diastole.fan[4]) > abs(rest.fan[4])
    # 指の所が凹み、指の間が盛り上がる値も鼓動で変わる
    assert diastole.bulge > rest.bulge
    names = set(rest.dent_uniforms())
    assert {f"uHandSeg[{i}]" for i in range(5)} <= names and "uHandDent" in names


def test_skin_ties_each_finger_and_leaves_the_back_of_the_hand() -> None:
    weights, along, _knuckle, main = skin(400.0, 250.0)
    assert main == 2 and weights[2] > 0.95 and 0.3 < along < 0.7
    weights, _along, _knuckle, main = skin(226.0, 400.0)
    assert main == 0 and weights[0] > 0.9
    weights, along, _knuckle, main = skin(420.0, 620.0)
    assert main == -1 and sum(weights) == 0.0 and along == 0.0
    for u, v in ((330.0, 200.0), (540.0, 330.0), (270.0, 480.0)):
        assert sum(skin(u, v)[0]) <= 1.0 + 1e-9
    # 手の甲より上は表面に沿い、手首から下（袖）は平らなまま
    assert wrap_weight(400.0) == 1.0 and wrap_weight(900.0) == 0.0


def _gl_context():  # noqa: ANN202
    from PySide6.QtGui import QOffscreenSurface, QOpenGLContext

    ctx = QOpenGLContext()
    if not ctx.create():
        return None
    surface = QOffscreenSurface()
    surface.create()
    if not ctx.makeCurrent(surface):
        return None
    return ctx, surface


def _skin_like(color: QColor) -> bool:
    return color.red() > 150 and 90 < color.green() < 225 and color.blue() < color.red() - 25


def test_gl_hand_wraps_the_heart(qapp: QApplication) -> None:
    del qapp
    made = _gl_context()
    if made is None:
        pytest.skip("OpenGL なし")
    ctx, _surface = made
    from PySide6.QtOpenGL import QOpenGLFramebufferObject

    from stream_heartbeat.render.hand_gl import HandRenderer
    from stream_heartbeat.render.heart_gl import HeartRenderer, camera_matrices
    from stream_heartbeat.ui.effect_grip import grip_image, hand_image

    size = 260
    gl = ctx.functions()
    heart = HeartRenderer(gl, build_heart_mesh(rows=36, cols=56))
    hand = HandRenderer(gl, hand_image(), grip_image())
    fbo = QOpenGLFramebufferObject(
        size, size, QOpenGLFramebufferObject.Attachment.CombinedDepthStencil
    )
    fbo.bind()
    gl.glViewport(0, 0, size, size)
    gl.glClearColor(0.0, 1.0, 0.0, 1.0)
    gl.glClear(0x4000 | 0x0100)
    cycle = _rest()
    pose = _pose(cycle)
    heart.draw(
        width=size,
        height=size,
        cycle=cycle,
        look=LOOK,
        yaw_deg=0.0,
        pitch_deg=0.0,
        scale=SIZE,
        opacity=1.0,
        time_s=0.0,
        hand=pose,
    )
    hand.draw(width=size, height=size, pose=pose, lift=0.0, opacity=1.0)
    image = fbo.toImage()
    fbo.release()
    view, proj, _cam = camera_matrices(size, size)

    def screen(fx: float, fy: float, on_body: bool = True) -> tuple[int, int]:
        if on_body:
            b = wrap(fx, fy, pose.lift)
            w = [pose.center[i] + b[i] * pose.body[i] for i in range(3)]
        else:
            w = [pose.center[0] + fx * pose.size, pose.center[1] + fy * pose.size, pose.center[2]]
        v = proj.map(view.map(QVector4D(w[0], w[1], w[2], 1.0)))
        return int((v.x() / v.w() * 0.5 + 0.5) * size), int((0.5 - v.y() / v.w() * 0.5) * size)

    # 手の甲は心臓に載り、袖は窓の下まで届き、窓の上の端には何も無い
    assert _skin_like(image.pixelColor(*screen(*pose.anchor)))
    assert any(image.pixelColor(x, size - 2) != QColor(0, 255, 0) for x in range(0, size, 2))
    assert all(image.pixelColor(x, 1) == QColor(0, 255, 0) for x in range(0, size, 4))
    # 中指は心臓の正面に載り、平らに伸ばしたときの指先の所（心臓の上の外）には届かない
    bx, by, ex, ey, _half = pose.segments()[2]
    mid = screen(bx + (ex - bx) * 0.3, by + (ey - by) * 0.3)
    assert _skin_like(image.pixelColor(*mid))
    flat_tip = screen(ex, ey, on_body=False)
    assert not _skin_like(image.pixelColor(*flat_tip))
