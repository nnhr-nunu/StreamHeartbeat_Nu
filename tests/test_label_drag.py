from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication

from stream_heartbeat.overlay import FloatBurst
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.ui.label_drag import BEAT, BPM, LabelDrag, beat_preview, label_at

RECT = QRectF(0, 0, 720, 720)


def _at(x: float, y: float) -> QPointF:
    return QPointF(x * RECT.width(), y * RECT.height())


def _word(x: float, y: float, alpha: float = 1.0) -> FloatBurst:
    return FloatBurst(text="❤", pos=(x, y), alpha=alpha)


def test_only_shown_text_can_be_grabbed(qapp: QApplication) -> None:
    del qapp
    profile = HeartProfile()
    # 心拍数はいつも出ているので、置き場所（文字の真ん中）をつまめる
    assert label_at(RECT, profile, _at(profile.bpm_x, profile.bpm_y), 72, []) == BPM
    # 拍の文字は出ている文字（拍ごとにゆらいだ所。置き場所は文字の左下）だけをつまめる
    shown = [_word(0.58, 0.26)]
    assert label_at(RECT, profile, _at(0.60, 0.24), 72, shown) == BEAT
    # 拍の合間（文字が出ていない・消えかけ）は、置き場所の辺りでも演出の操作のまま
    assert label_at(RECT, profile, _at(0.60, 0.24), 72, []) is None
    assert label_at(RECT, profile, _at(0.60, 0.24), 72, [_word(0.58, 0.26, alpha=0.1)]) is None
    # ゆらぎの範囲全体ではなく、出ている文字の所だけ（心臓の上を押しても演出が効く）
    assert label_at(RECT, profile, _at(0.47, 0.30), 72, shown) is None
    assert label_at(RECT, profile, _at(0.5, 0.5), 72, shown) is None
    # 透明度を低くしていても、出ている文字はつまめる
    profile.beat_text_opacity = 0.1
    assert label_at(RECT, profile, _at(0.60, 0.24), 72, shown) == BEAT
    # 出していない文字はつまめない
    profile.show_bpm = False
    profile.show_beat_text = False
    assert label_at(RECT, profile, _at(0.5, 0.88), 72, shown) is None
    assert label_at(RECT, profile, _at(0.60, 0.24), 72, shown) is None


def test_dragging_keeps_the_grab_offset_and_stays_inside_the_window(qapp: QApplication) -> None:
    del qapp
    profile = HeartProfile()
    drag = LabelDrag()
    # 文字の真ん中から少し右をつまんで動かしても、文字はつまんだ所との位置関係のまま動く
    start = _at(profile.bpm_x + 0.01, profile.bpm_y)
    assert drag.press(RECT, profile, start, 72, []) and drag.target == BPM
    drag.move(RECT, profile, _at(0.31, 0.40))
    assert (profile.bpm_x, profile.bpm_y) == (0.30, 0.40)
    # 窓の外へは出ない
    drag.move(RECT, profile, QPointF(-200.0, 2000.0))
    assert (profile.bpm_x, profile.bpm_y) == (0.0, 1.0)
    assert drag.release() and not drag.dragging
    assert not drag.release()
    # 拍の文字は、つまんだ文字（ゆらいだ所）がマウスについてくる。心拍数の値は変えない
    profile.bpm_x, profile.bpm_y = 0.5, 0.9
    word = _word(0.58, 0.26)
    base = (profile.beat_text_x, profile.beat_text_y)
    assert drag.press(RECT, profile, _at(0.60, 0.25), 72, [word]) and drag.target == BEAT
    # 押しただけでは置き場所を変えず、つまんだ文字の所にはっきり出す
    # （元の置き場所に濃い文字を出さない）
    assert (profile.beat_text_x, profile.beat_text_y) == base and drag.held == (0.58, 0.26)
    assert beat_preview(profile, drag.held).pos == (0.58, 0.26)
    drag.move(RECT, profile, _at(0.70, 0.45))
    assert (profile.beat_text_x, profile.beat_text_y) == (0.68, 0.46) == drag.held
    assert (profile.bpm_x, profile.bpm_y) == (0.5, 0.9)
    # 何も無い所では押してもつままない
    drag.release()
    assert drag.held is None
    assert not drag.press(RECT, profile, _at(0.1, 0.5), 72, [word]) and not drag.dragging


def test_beat_preview_sits_at_the_place_without_jitter() -> None:
    profile = HeartProfile(beat_text=" ドクン ", beat_text_x=0.3, beat_text_y=0.2)
    word = beat_preview(profile)
    assert word.text == "ドクン" and word.pos == (0.3, 0.2) and word.alpha == 1.0
