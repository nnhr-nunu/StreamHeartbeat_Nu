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
from stream_heartbeat.defib import (
    FAST_FIT_S,
    HOLD_S,
    JOLT_HOLD_AT,
    MIN_GAP_S,
    PATTERN_PAUSES,
    PATTERNS,
    RECOVER_S,
    TEXT_GAP_S,
    TEXT_MIN_STRENGTH,
    DefibRhythm,
)
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


def _shocked(seed: int = 3, at: float = 10.0, pattern: str | None = "scatter") -> DefibRhythm:
    rhythm = DefibRhythm(random.Random(seed))
    assert rhythm.shock(at, TARGET, pattern)
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
    pause = PATTERN_PAUSES["scatter"]
    assert 10.0 + pause[0] <= first <= 10.0 + pause[1]
    # びくり: ショックの直後に強く縮み、電流が流れている間は縮んだまま細かく震える
    assert max(rhythm.cycle(10.0 + k * 0.01).squeeze for k in range(10)) > 0.9  # type: ignore[union-attr]
    held = [rhythm.cycle(10.0 + JOLT_HOLD_AT + HOLD_S * u) for u in (0.1, 0.5, 0.9)]
    assert all(c is not None and c.squeeze > 0.8 for c in held)
    tremor = [rhythm.shake(10.0 + JOLT_HOLD_AT + 0.004 * k) for k in range(12)]
    assert max(tremor) > 0.2 and min(tremor) < -0.2
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


def _runs(flags: list[bool]) -> int:
    """続けて True が並んだ最長の数。"""
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def test_every_pattern_settles_to_the_current_rate() -> None:
    for pattern in PATTERNS:
        for seed in range(12):
            rhythm = _shocked(seed, pattern=pattern)
            beats = _recovery(rhythm)
            pause = PATTERN_PAUSES[pattern]
            assert 10.0 + pause[0] <= beats[0][0] <= 10.0 + pause[1], pattern
            assert all(gap > 0.05 for _t, gap, _s in beats), pattern
            settle = rhythm._settle_at
            # 不整脈は 20 秒ほどまで（ショックは 10 秒）
            assert 18.0 < settle < 33.0, (pattern, settle)
            # 最後の 2 秒は今の心拍数の間隔の、強い拍で打つ
            late = [(gap, s) for t, gap, s in beats if t > settle - 2.0]
            assert statistics.mean(g for g, _s in late) == pytest.approx(TARGET, rel=0.15), pattern
            assert min(s for _g, s in late) > 0.8, pattern


def test_patterns_have_their_own_shapes() -> None:
    for seed in range(12):

        def recovery(pattern: str, seed: int = seed) -> list[tuple[float, float, float]]:
            return _recovery(_shocked(seed, pattern=pattern))

        # ﾋﾞｸﾋﾞｸﾋﾞｸﾋﾞｸ: 速い拍が 6 つ以上続く（間隔は 5 つ以上）
        run = recovery("run")
        assert _runs([gap < 0.25 for _t, gap, _s in run]) >= 5
        # ビビビビクッ: 小さく速い拍が 3 つ以上続いたあとに、強い一打ちと長い休み
        salvo = recovery("salvo")
        for k in range(3, len(salvo)):
            if salvo[k][1] >= 0.15 and all(salvo[k - j][1] < 0.15 for j in (1, 2, 3)):
                assert salvo[k][2] == 1.0 and salvo[k][1] > TARGET * 1.4
                break
        else:
            raise AssertionError("期外収縮の連発が無い")
        # 細動: 弱く速い震えが 10 以上続く
        quiver = recovery("quiver")
        assert _runs([gap < 0.15 and s <= 0.3 for _t, gap, s in quiver]) >= 10
        # 二段脈: 短い・長いの間隔が交互に 4 組以上
        gaps = [gap for _t, gap, _s in recovery("bigeminy")]
        assert all(gaps[2 * i] < TARGET * 0.6 < TARGET * 1.4 < gaps[2 * i + 1] for i in range(4))
        # 長く止まってから、遅い拍で始まる
        slow = recovery("slow")
        assert slow[0][0] - 10.0 >= 2.8
        assert statistics.mean(gap for _t, gap, _s in slow[:3]) > TARGET * 1.6
        # 一拍抜ける: 間隔の倍ほどの休みが 3 回以上
        dropped = recovery("dropped")
        assert sum(1 for _t, gap, _s in dropped if TARGET * 1.7 < gap < TARGET * 2.2) >= 3


def test_each_shock_picks_another_pattern_and_pause() -> None:
    rhythm = DefibRhythm(random.Random(5))
    seen: list[str] = []
    pauses: list[float] = []
    t = 10.0
    for _ in range(60):
        assert rhythm.shock(t, TARGET)
        seen.append(rhythm.pattern)
        pauses.append(rhythm._beats[1][0] - t)
        t += 30.0
    # 続けて同じ型にはならず、どの型も出る
    assert all(a != b for a, b in zip(seen, seen[1:]))
    assert set(seen) == set(PATTERNS)
    # 止まっている長さもショックごとに大きく違う
    assert min(pauses) < 0.9 and max(pauses) > 3.0


def test_fast_beats_finish_before_the_next_one() -> None:
    rhythm = _shocked(pattern="run")
    fast = [(t, gap) for t, gap, _s in _recovery(rhythm) if gap < FAST_FIT_S]
    assert fast
    for t, gap in fast:
        # 速い拍でも 1 拍の動きを間隔の中で終える（次の拍で形が飛ばない）
        peak = max(rhythm.cycle(t + gap * k / 20).squeeze for k in range(20))  # type: ignore[union-attr]
        end = rhythm.cycle(t + gap * 0.995)
        assert peak > 0.3
        assert end is not None and end.squeeze < 0.02 and end.fill < 0.05


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


def test_tiny_twitches_do_not_flood_beat_texts() -> None:
    for seed in range(10):
        rhythm = _shocked(seed, pattern="quiver")
        texts = rhythm.beats_between(0.0, 100.0)
        weak = [t for t, _gap, s in _recovery(rhythm) if s < TEXT_MIN_STRENGTH]
        # 細動の小さな震えには文字を出さない。続けて出すときは間を空ける
        assert len(weak) >= 10
        assert not set(weak) & set(texts)
        assert texts and all(b - a >= TEXT_GAP_S for a, b in zip(texts, texts[1:]))


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
        1 for x in range(x0, x1, 3) for y in range(y0, y1, 3) if image.pixelColor(x, y).alpha() > 40
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


def test_shock_runs_current_over_the_heart(qapp: QApplication) -> None:
    del qapp
    calm = _paint(since=None)
    shock = _paint(since=0.05)
    later = _paint(since=1.0)
    assert _lit(calm, 170, 120, 230, 240) == 0
    assert _lit(shock, 170, 120, 230, 240) > 10
    assert _lit(later, 170, 120, 230, 240) == 0
    # 光は心臓のまわりだけ（窓の角は透明のまま）
    assert shock.pixelColor(2, 2).alpha() == 0


def test_sparks_fly_and_smoke_rises_only_when_allowed(qapp: QApplication) -> None:
    del qapp
    # 火花は板の外へ飛び散る
    calm = _paint(since=None)
    sparks = _paint(since=0.12, seed=4)
    assert _lit(sparks, 20, 80, 110, 260) > _lit(calm, 20, 80, 110, 260)
    # 煙は haze のときだけ（クロマキーの緑の上では出さない）
    plain = _paint(since=1.0)
    hazy = _paint(since=1.0, haze=True)
    assert plain != hazy
    assert _paint(since=1.0, haze=True, xray=True) == _paint(since=1.0, xray=True)


def test_paddles_look_like_polished_steel(qapp: QApplication) -> None:
    del qapp
    image = _paint(since=None)
    disc = [image.pixelColor(x, y) for x in range(90, 130) for y in range(150, 230)]
    brightness = [c.red() + c.green() + c.blue() for c in disc if c.alpha() == 255]
    # 磨いた金属: 明るい映り込みと暗い所がくっきり分かれる
    assert max(brightness) > 680 and min(brightness) < 210


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
    first = canvas._defib._text_times[0]
    canvas.set_now(first - 0.1)
    canvas.set_now(first + 0.02)
    assert len(canvas._defib_text._items) == 1
    assert canvas._defib_text.bursts_at(first + 0.1)
    # 拍の文字を切っていれば出さない
    session.profile.show_beat_text = False
    second = canvas._defib._text_times[1]
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
