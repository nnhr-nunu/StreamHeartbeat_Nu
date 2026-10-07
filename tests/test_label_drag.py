from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication

from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.ui.label_drag import BEAT, BPM, LabelDrag, beat_preview, label_at

RECT = QRectF(0, 0, 720, 720)


def _at(x: float, y: float) -> QPointF:
    return QPointF(x * RECT.width(), y * RECT.height())


def test_bpm_and_beat_text_can_be_grabbed_where_they_are(qapp: QApplication) -> None:
    del qapp
    profile = HeartProfile()
    # 心拍数は置き場所が文字の真ん中
    assert label_at(RECT, profile, _at(profile.bpm_x, profile.bpm_y), 72) == BPM
    # 拍の文字は置き場所が文字の左下。ゆらぎの範囲もつまめる
    assert (
        label_at(RECT, profile, _at(profile.beat_text_x + 0.02, profile.beat_text_y - 0.02), 72)
        == BEAT
    )
    jitter = profile.beat_text_jitter
    assert (
        label_at(RECT, profile, _at(profile.beat_text_x - jitter * 0.9, profile.beat_text_y), 72)
        == BEAT
    )
    # 心臓の真ん中はどちらでもない（演出の操作のまま）
    assert label_at(RECT, profile, _at(0.5, 0.5), 72) is None
    # 出していない文字はつまめない
    profile.show_bpm = False
    profile.show_beat_text = False
    assert label_at(RECT, profile, _at(0.5, 0.88), 72) is None
    assert label_at(RECT, profile, _at(profile.beat_text_x, profile.beat_text_y), 72) is None


def test_dragging_keeps_the_grab_offset_and_stays_inside_the_window(qapp: QApplication) -> None:
    del qapp
    profile = HeartProfile()
    drag = LabelDrag()
    # 文字の真ん中から少し右をつまんで動かしても、文字はつまんだ所との位置関係のまま動く
    start = _at(profile.bpm_x + 0.01, profile.bpm_y)
    assert drag.press(RECT, profile, start, 72) and drag.target == BPM
    drag.move(RECT, profile, _at(0.31, 0.40))
    assert (profile.bpm_x, profile.bpm_y) == (0.30, 0.40)
    # 窓の外へは出ない
    drag.move(RECT, profile, QPointF(-200.0, 2000.0))
    assert (profile.bpm_x, profile.bpm_y) == (0.0, 1.0)
    assert drag.release() and not drag.dragging
    assert not drag.release()
    # 拍の文字も同じように動かせる。心拍数の値は変えない
    profile.bpm_x, profile.bpm_y = 0.5, 0.9
    x, y = profile.beat_text_x, profile.beat_text_y
    assert drag.press(RECT, profile, _at(x + 0.02, y - 0.01), 72) and drag.target == BEAT
    drag.move(RECT, profile, _at(x + 0.12, y + 0.29))
    assert (profile.beat_text_x, profile.beat_text_y) == (round(x + 0.1, 2), round(y + 0.3, 2))
    assert (profile.bpm_x, profile.bpm_y) == (0.5, 0.9)
    # 何も無い所では押してもつままない
    drag.release()
    assert not drag.press(RECT, profile, _at(0.1, 0.5), 72) and not drag.dragging


def test_beat_preview_sits_at_the_place_without_jitter() -> None:
    profile = HeartProfile(beat_text=" ドクン ", beat_text_x=0.3, beat_text_y=0.2)
    word = beat_preview(profile)
    assert word.text == "ドクン" and word.pos == (0.3, 0.2) and word.alpha == 1.0
