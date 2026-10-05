"""演出「除細動器」: 電気ショックのあとのリズム・パドルの絵・配信用の窓の操作。"""

from __future__ import annotations

import random
import statistics
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication

from stream_heartbeat.clock import BeatClock, cycle_at
from stream_heartbeat.defib import MIN_GAP_S, PAUSE_S, RECOVER_S, DefibRhythm
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.model_mesh import beat_weights, load_model_anim
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.effect_defib import paint_defibrillator
from stream_heartbeat.ui.effects import (
    EFFECT_DEFIB,
    EFFECT_HINTS,
    EFFECT_LABELS,
    HeartFrame,
    active_effect,
)
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow

TARGET = 0.8


@pytest.fixture(autouse=True)
def _isolate_operator_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "stream_heartbeat.ui.operator_window.resolve_data_dir",
        lambda: tmp_path,
    )


def _shocked(seed: int = 3, at: float = 10.0) -> DefibRhythm:
    rhythm = DefibRhythm(random.Random(seed))
    assert rhythm.shock(at, TARGET)
    return rhythm


def _recovery(rhythm: DefibRhythm) -> list[tuple[float, float, float]]:
    """ショックのびくりを除いた拍: (時刻, 次の拍までの秒, 強さ)。"""
    return rhythm._beats[1:]


def test_defib_is_offered_only_for_real_hearts() -> None:
    for style in ("realistic", "xray", "xray_heart"):
        assert active_effect(style, EFFECT_DEFIB) == EFFECT_DEFIB
    for style in ("cute", "chic", "poly", "mech", "echo", "mri", "ecg", "particles"):
        assert active_effect(style, EFFECT_DEFIB) == ""
    assert EFFECT_LABELS[EFFECT_DEFIB] == "除細動器"
    assert "--" in EFFECT_HINTS[EFFECT_DEFIB]


def test_shock_jolts_then_stops_the_heart() -> None:
    rhythm = _shocked()
    first = _recovery(rhythm)[0][0]
    assert 10.0 + PAUSE_S[0] <= first <= 10.0 + PAUSE_S[1]
    # びくり: ショックの直後に強く縮む
    assert max(rhythm.cycle(10.0 + k * 0.01).squeeze for k in range(10)) > 0.9  # type: ignore[union-attr]
    assert rhythm.shake(10.03) != 0.0
    assert rhythm.squash(10.03) != (1.0, 1.0)
    assert rhythm.jump(10.05) > 0.0
    # 止まっている間は、心室も心房も動かない
    t = 10.9
    while t < first:
        cycle = rhythm.cycle(t)
        assert cycle is not None
        assert cycle.squeeze == 0.0 and cycle.fill == 0.0 and cycle.eject == 0.0
        assert cycle.atria_r == 0.0 and cycle.atria_l == 0.0
        t += 0.05
    assert rhythm.shake(10.9) == 0.0 and rhythm.squash(10.9) == (1.0, 1.0)


def test_rhythm_is_irregular_then_settles_to_the_current_rate() -> None:
    early_spread: list[float] = []
    late_spread: list[float] = []
    for seed in range(20):
        beats = _recovery(_shocked(seed))
        start = beats[0][0]
        early = [gap for t, gap, _s in beats if t - start < RECOVER_S * 0.4]
        late = [gap for t, gap, _s in beats if t - start > RECOVER_S * 0.85]
        assert early and late
        early_spread.append(max(early) / min(early))
        late_spread.append(max(late) / min(late))
        # 終わりは今の心拍数の間隔にほぼ戻る
        assert statistics.mean(late) == pytest.approx(TARGET, rel=0.12)
        # 戻り始めは遅い
        assert statistics.mean(early) > TARGET * 1.1
        # 弱い拍が混ざる（最後は強さが戻る）
        assert min(s for _t, _gap, s in beats) < 0.8
        assert beats[-1][2] > 0.85
    # 戻り始めの方が間隔がばらつく（早すぎる拍と長い休み）
    assert statistics.mean(early_spread) > statistics.mean(late_spread) * 1.5
    assert max(early_spread) > 2.0


def test_hands_over_to_the_real_beat() -> None:
    rhythm = _shocked()
    settle = rhythm._settle_at
    # 打ち終える前は本物の拍が来ても引き渡さない
    rhythm.step(settle - 0.5, settle - 0.6)
    assert rhythm.active(settle - 0.4)
    # 打ち終えたあと、最初の本物の拍の頭で引き渡す
    rhythm.step(settle + 0.1, settle - 0.3)
    assert rhythm.active(settle + 0.1)
    real = settle + 0.35
    rhythm.step(real + 0.01, real)
    assert not rhythm.active(real + 0.01)
    assert rhythm.cycle(real + 0.01) is None
    assert rhythm.since_shock(real + 0.01) is None
    # 本物の拍の文字は、ショックから引き渡すまでだけ隠す
    assert rhythm.mutes(10.5) and rhythm.mutes(real - 0.01)
    assert not rhythm.mutes(9.9) and not rhythm.mutes(real)


def test_hands_over_even_without_real_beats() -> None:
    rhythm = _shocked()
    settle = rhythm._settle_at
    rhythm.step(settle + TARGET, 0.0)
    assert rhythm.active(settle + TARGET)
    rhythm.step(settle + TARGET * 3.0, 0.0)
    assert not rhythm.active(settle + TARGET * 3.0)


def test_rapid_clicks_do_not_restart_the_shock() -> None:
    rhythm = _shocked()
    assert not rhythm.shock(10.0 + MIN_GAP_S * 0.5, TARGET)
    assert rhythm.since_shock(10.3) == pytest.approx(0.3)
    # 少し間を置けば、途中でも最初からやり直す
    assert rhythm.shock(13.0, TARGET)
    assert rhythm.since_shock(13.2) == pytest.approx(0.2)


def test_beat_texts_follow_the_irregular_beats() -> None:
    rhythm = _shocked()
    beats = [t for t, _gap, _s in _recovery(rhythm)]
    # びくりは「ドクン」にしない
    assert rhythm.beats_between(9.0, beats[0] - 0.01) == []
    assert rhythm.beats_between(beats[0] - 0.01, beats[1]) == beats[:2]


def test_weak_beats_move_the_heart_less() -> None:
    full = cycle_at(0.06, TARGET)
    weak = cycle_at(0.06, TARGET, 0.5)
    assert weak.squeeze == pytest.approx(full.squeeze * 0.5)
    assert weak.strength == 0.5
    # ふつうの拍時計の動きは強さ 1 のまま
    clock = BeatClock()
    clock.feed_beat(1.0)
    assert clock.cycle(1.06) == cycle_at(1.06 - 1.0, clock.interval())
    anim = load_model_anim()
    if anim is None:
        pytest.skip("Blender の心臓の形が無い")
    rest = beat_weights(anim, 5.0, 1.0)
    peak = beat_weights(anim, 0.25, 1.0)
    half = beat_weights(anim, 0.25, 1.0, 0.5)
    assert beat_weights(anim, 0.25, 1.0, 0.0) == pytest.approx(rest)
    assert half == pytest.approx([r + (p - r) * 0.5 for r, p in zip(rest, peak)])


def _paint(**kwargs: object) -> QImage:
    image = QImage(400, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    frame = HeartFrame(center=QPointF(200, 180), half_w=90, half_h=95)
    paint_defibrillator(painter, QRectF(0, 0, 400, 400), frame, cycle_at(2.0, TARGET), **kwargs)  # type: ignore[arg-type]
    painter.end()
    return image


def _lit(image: QImage, x0: int, y0: int, x1: int, y1: int) -> int:
    return sum(
        1
        for x in range(x0, x1, 3)
        for y in range(y0, y1, 3)
        if image.pixelColor(x, y).alpha() > 40
    )


def test_paddles_hold_the_heart_and_handles_leave_through_the_bottom(qapp: QApplication) -> None:
    del qapp
    image = _paint(since=None)
    # 板は心臓の左右の縁、握りは窓の下の左右へ抜ける
    assert _lit(image, 90, 150, 130, 230) > 0
    assert _lit(image, 270, 150, 310, 230) > 0
    assert _lit(image, 0, 380, 120, 400) > 0
    assert _lit(image, 280, 380, 400, 400) > 0
    # 心臓の真ん中と上は空けておく
    assert _lit(image, 170, 60, 230, 200) == 0


def test_shock_draws_arcs_across_the_heart(qapp: QApplication) -> None:
    del qapp
    calm = _paint(since=None)
    shock = _paint(since=0.05)
    later = _paint(since=1.0)
    assert _lit(calm, 170, 120, 230, 240) == 0
    assert _lit(shock, 170, 120, 230, 240) > 10
    assert _lit(later, 170, 120, 230, 240) == 0
    # 光は心臓のまわりだけ（窓の角は透明のまま）
    assert shock.pixelColor(2, 2).alpha() == 0


def test_xray_paddles_are_white_and_stay_in_the_film(qapp: QApplication) -> None:
    del qapp
    film = QPainterPath()
    film.addRect(QRectF(20, 20, 360, 360))
    image = _paint(since=None, xray=True, clip=film)
    disc = max(
        (image.pixelColor(x, y) for x in range(90, 130) for y in range(150, 230)),
        key=lambda c: c.red() + c.green() + c.blue(),
    )
    assert disc.red() > 200 and disc.green() > 200 and disc.blue() > 200
    # 写真の外（窓の下の端）には描かない
    assert _lit(image, 0, 385, 400, 400) == 0


def _open(profile: HeartProfile) -> tuple[OperatorWindow, OutputWindow, HeartSession]:
    session = HeartSession(profile)
    output = OutputWindow(session)
    return OperatorWindow(session, output), output, session


def test_click_shocks_and_locks_the_angle(qapp: QApplication, qtbot) -> None:  # noqa: ANN001
    del qapp
    profile = HeartProfile(style="realistic", realistic_look="surgical", effect=EFFECT_DEFIB)
    operator, output, session = _open(profile)
    canvas = output.canvas
    canvas.resize(300, 300)
    # パドルではさんでいる間は正面に固定する（向きの操作も隠す）
    assert not canvas._can_rotate()
    assert operator._angle_wrap.isHidden()
    canvas.set_now(5.0)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=canvas.rect().center())
    assert canvas._defib.active(5.0)
    assert canvas._defib.since_shock(5.1) == pytest.approx(0.1)
    # 不整脈の拍で文字が出る（本物の拍の文字の代わり）
    first = canvas._defib._beats[1][0]
    canvas.set_now(first - 0.1)
    canvas.set_now(first + 0.02)
    assert len(canvas._defib_text._items) == 1
    assert canvas._defib_text.bursts_at(first + 0.1)
    # 拍の文字を切っていれば出さない
    session.profile.show_beat_text = False
    second = canvas._defib._beats[2][0]
    canvas.set_now(second - 0.1)
    canvas.set_now(second + 0.02)
    assert len(canvas._defib_text._items) == 1
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=canvas.rect().center())
    operator.close()


def test_bpm_shows_dashes_until_handed_over(qapp: QApplication) -> None:
    del qapp
    profile = HeartProfile(style="xray_heart", effect=EFFECT_DEFIB)
    operator, output, session = _open(profile)
    canvas = output.canvas
    canvas.set_now(5.0)
    assert canvas.bpm_label(5.0) == session.clock.bpm
    canvas.shock()
    assert canvas.bpm_label(5.2) == "--"
    # 演出を変えれば、すぐ数に戻る
    profile.effect = ""
    assert canvas.bpm_label(5.2) == session.clock.bpm
    operator.close()
