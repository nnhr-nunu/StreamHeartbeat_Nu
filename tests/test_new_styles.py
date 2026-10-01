"""かわいい2・オシャレ1・2・パーティクル・心電図2 と、モニター画面・はじけるハートの描画。"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.config import CHROMA_HEX
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.heart_frames import render_frames
from stream_heartbeat.render.heart_mesh import FLOATS_PER_VERTEX, REGION_ARTERY
from stream_heartbeat.render.poly_mesh import build_poly_mesh
from stream_heartbeat.ui.effect_burst import POP_COLORS, POP_LIFE_S, paint_heart_pops
from stream_heartbeat.ui.effect_monitor import (
    MONITOR_BG,
    monitor_screen,
    paint_monitor_back,
)
from stream_heartbeat.ui.effects import POP_KEEP_S
from stream_heartbeat.ui.heart_chic import CHIC_COBALT, CHIC_PINK, CHIC_SUN, CHIC_VIOLET
from stream_heartbeat.ui.heart_cute_reiwa import REIWA_LAVENDER, REIWA_MINT, REIWA_PINK
from stream_heartbeat.ui.heart_paint import paint_heart
from stream_heartbeat.ui.heart_particles import PARTICLE_PALETTE, beat_origins

CHROMA = QColor(CHROMA_HEX)
SIZE = 240


def _clock() -> BeatClock:
    clock = BeatClock()
    for k in range(6):
        clock.feed_beat(k * 0.8)
    return clock


def _render(style: str, look: str = "", now: float = 4.3) -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGB32)
    image.fill(CHROMA)
    painter = QPainter(image)
    clock = _clock()
    paint_heart(
        painter,
        QRectF(0, 0, SIZE, SIZE),
        style=style,
        scale=0.7,
        opacity=1.0,
        cycle=clock.cycle(now),
        clock=clock,
        now=now,
        look=look,
    )
    painter.end()
    return image


def _not_chroma_like(color: QColor) -> bool:
    """絵そのものの色が緑でない（縁で背景の緑と混ざった色は除いて調べる）。"""
    return not (color.green() > 200 and color.red() < 80 and color.blue() < 80)


def _painted(image: QImage) -> list[tuple[int, int]]:
    """背景の緑から十分に離れた画素（絵の中身）の位置。"""
    spots = []
    for y in range(0, SIZE, 4):
        for x in range(0, SIZE, 4):
            pixel = image.pixelColor(x, y)
            far = abs(pixel.red() - CHROMA.red()) + abs(pixel.green() - CHROMA.green())
            far += abs(pixel.blue() - CHROMA.blue())
            if far > 200:
                spots.append((x, y))
    return spots


def test_palettes_avoid_chroma_green() -> None:
    colors = (
        REIWA_PINK,
        REIWA_LAVENDER,
        REIWA_MINT,
        CHIC_PINK,
        CHIC_COBALT,
        CHIC_SUN,
        CHIC_VIOLET,
        MONITOR_BG,
        *PARTICLE_PALETTE,
        *POP_COLORS,
    )
    for color in colors:
        assert color != CHROMA and _not_chroma_like(color), color.name()


def test_new_2d_styles_paint_over_chroma(qapp: QApplication) -> None:
    del qapp
    for style, look in (("cute", "reiwa"), ("chic", ""), ("particles", ""), ("ecg", "outline")):
        assert len(_painted(_render(style, look))) > 20, (style, look)


def test_new_heart_styles_sit_in_the_middle(qapp: QApplication) -> None:
    del qapp
    for style, look in (("cute", "reiwa"), ("chic", "")):
        spots = _painted(_render(style, look))
        xs = [x for x, _y in spots]
        ys = [y for _x, y in spots]
        assert abs(sum(xs) / len(xs) - SIZE / 2) < SIZE * 0.12, style
        assert abs(sum(ys) / len(ys) - SIZE / 2) < SIZE * 0.15, style


def test_particles_rise_and_are_same_for_same_moment(qapp: QApplication) -> None:
    del qapp
    first = _render("particles", now=4.3)
    again = _render("particles", now=4.3)
    assert first == again

    def mean_y(image: QImage) -> float:
        ys = [y for _x, y in _painted(image)]
        return sum(ys) / len(ys)

    # 新しい拍が来ない間に時刻だけ進めると、ハートは上へ昇る
    clock = BeatClock()
    clock.feed_beat(0.0)
    origins = beat_origins(clock, 0.6, 5.0)
    assert origins and origins[0] == 0.0

    def single(now: float) -> QImage:
        image = QImage(SIZE, SIZE, QImage.Format.Format_RGB32)
        image.fill(CHROMA)
        painter = QPainter(image)
        rect = QRectF(0, 0, SIZE, SIZE)
        from stream_heartbeat.ui.heart_particles import paint_particles

        lone = BeatClock()
        lone.feed_beat(0.0)
        # 拍は 1 回だけ（次の拍が来ないので、出たハートが昇っていくだけ）
        paint_particles(painter, rect, 0.7, lone, now)
        painter.end()
        return image

    # 1 拍ぶんが出そろったあと（0.6 秒より後）で比べる
    assert mean_y(single(1.4)) < mean_y(single(1.0)) - 10.0


def test_beat_origins_go_back_in_time() -> None:
    clock = _clock()
    origins = beat_origins(clock, 4.3, 2.0)
    assert origins == sorted(origins, reverse=True)
    assert all(4.3 - 2.0 <= t <= 4.3 for t in origins)
    assert 4.0 in origins


def test_monitor_screen_is_dark_and_inside(qapp: QApplication) -> None:
    del qapp
    rect = QRectF(0, 0, SIZE, SIZE)
    screen = monitor_screen(rect)
    assert rect.contains(screen) and screen.width() > SIZE * 0.8
    image = QImage(SIZE, SIZE, QImage.Format.Format_RGB32)
    image.fill(CHROMA)
    painter = QPainter(image)
    paint_monitor_back(painter, rect)
    painter.end()
    center = image.pixelColor(SIZE // 2, SIZE // 2)
    assert center.lightness() < 60 and _not_chroma_like(center)
    assert image.pixelColor(1, 1) == CHROMA


def test_heart_pops_paint_near_click_and_vanish(qapp: QApplication) -> None:
    del qapp
    assert POP_KEEP_S == POP_LIFE_S
    rect = QRectF(0, 0, SIZE, SIZE)

    def shot(age: float) -> QImage:
        image = QImage(SIZE, SIZE, QImage.Format.Format_RGB32)
        image.fill(CHROMA)
        painter = QPainter(image)
        paint_heart_pops(painter, rect, [(age, 0.25, 0.75, 3.0)])
        painter.end()
        return image

    spots = _painted(shot(0.3))
    assert spots
    assert all(
        abs(x - SIZE * 0.25) < SIZE * 0.3 and abs(y - SIZE * 0.75) < SIZE * 0.3 for x, y in spots
    )
    assert not _painted(shot(POP_LIFE_S + 0.01))


def test_poly_mesh_is_coarse_with_marked_corners() -> None:
    mesh = build_poly_mesh()
    assert mesh.vertex_count % 3 == 0
    assert mesh.vertex_count < 12000
    corners = {(1.0, 0.0), (0.0, 1.0), (0.0, 0.0)}
    regions = set()
    data = mesh.data
    for start in range(0, len(data), FLOATS_PER_VERTEX * 3):
        seen = {
            (data[start + k * FLOATS_PER_VERTEX + 9], data[start + k * FLOATS_PER_VERTEX + 10])
            for k in range(3)
        }
        assert seen == corners
        regions.add(data[start + 6])
    assert REGION_ARTERY in regions


def test_decorated_items_fit_inside_frame(qapp: QApplication) -> None:
    del qapp
    for look, style in (("reiwa", "cute"), ("", "chic")):
        frames = render_frames(HeartProfile(style=style, realistic_look=look), size=128)
        assert frames
        image = frames[0]
        # 飾りが端で切れない（いちばん外の 1 画素の列と行は透明）
        for k in range(128):
            for x, y in ((k, 0), (k, 127), (0, k), (127, k)):
                assert image.pixelColor(x, y).alpha() == 0, (style, x, y)
