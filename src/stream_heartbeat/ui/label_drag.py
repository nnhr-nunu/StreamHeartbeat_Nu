"""配信用の窓で、拍の文字と心拍数をマウスでつまんで動かす。

操作画面のつまみ（左右・上下）と同じ値（窓の幅・高さに対する割合）を書き換える。
動かせる範囲は窓の中なので、どこまで動かせるかが見て分かる。
拍の文字は拍のときしか出ないので、出る辺り（ゆらぎの分も含む）をつまめる所にし、
つまんでいる間は文字をはっきり出して置き場所を見せる。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF

from stream_heartbeat.overlay import FloatBurst, burst_font_px, lean_angle_deg
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.ui.heart_paint import beat_word_box, bpm_box

BEAT = "beat"
BPM = "bpm"
# つまめる所を文字の外枠より広げる量（窓の短い辺に対する割合）
GRAB_MARGIN = 0.015


def label_at(rect: QRectF, profile: HeartProfile, pos: QPointF, bpm: int | str) -> str | None:
    """pos にある文字（BPM / BEAT）。手前に描く心拍数を先に見る。"""
    if profile.show_bpm and _grow(_bpm_rect(rect, profile, bpm), rect).contains(pos):
        return BPM
    if beat_shown(profile) and _grow(_beat_rect(rect, profile), rect).contains(pos):
        return BEAT
    return None


def beat_shown(profile: HeartProfile) -> bool:
    return profile.show_beat_text and bool(profile.beat_text.strip())


def beat_preview(profile: HeartProfile) -> FloatBurst:
    """つまんでいる間に出す拍の文字（ゆらぎ無しの置き場所に、はっきり）。"""
    pos = (profile.beat_text_x, profile.beat_text_y)
    angle = lean_angle_deg(pos, profile.beat_text_tilt)
    return FloatBurst(text=profile.beat_text.strip(), pos=pos, alpha=1.0, angle=angle)


def _bpm_rect(rect: QRectF, profile: HeartProfile, bpm: int | str) -> QRectF:
    return bpm_box(rect, bpm, scale=profile.bpm_scale, pos=(profile.bpm_x, profile.bpm_y))


def _beat_rect(rect: QRectF, profile: HeartProfile) -> QRectF:
    """拍の文字が出る辺り。置き場所の文字の外枠を、ゆらぎの分だけ広げる。"""
    word = beat_preview(profile)
    font_px = burst_font_px(min(rect.width(), rect.height()), profile.beat_text_scale)
    point = QPointF(
        rect.left() + word.pos[0] * rect.width(), rect.top() + word.pos[1] * rect.height()
    )
    box = beat_word_box(point, word.text, font_px=font_px, angle=word.angle)
    spread = max(0.0, profile.beat_text_jitter)
    return box.adjusted(
        -spread * rect.width(),
        -spread * rect.height(),
        spread * rect.width(),
        spread * rect.height(),
    )


def _grow(box: QRectF, rect: QRectF) -> QRectF:
    m = GRAB_MARGIN * min(rect.width(), rect.height())
    return box.adjusted(-m, -m, m, m)


class LabelDrag:
    """つまんでいる文字と、つまんだ所から文字の置き場所までのずれ。"""

    def __init__(self) -> None:
        self.target: str | None = None
        self._offset = (0.0, 0.0)

    @property
    def dragging(self) -> bool:
        return self.target is not None

    def press(self, rect: QRectF, profile: HeartProfile, pos: QPointF, bpm: int | str) -> bool:
        """文字の上で押したらつまむ。つまんだら True。"""
        target = label_at(rect, profile, pos, bpm)
        if target is None:
            return False
        self.target = target
        x, y = _fraction(rect, pos)
        px, py = _place(profile, target)
        self._offset = (px - x, py - y)
        return True

    def move(self, rect: QRectF, profile: HeartProfile, pos: QPointF) -> None:
        """つまんだ文字を pos へ（窓の外へは出さない。操作画面のつまみと同じ 1% 刻み）。"""
        if self.target is None:
            return
        x, y = _fraction(rect, pos)
        nx = round(max(0.0, min(1.0, x + self._offset[0])), 2)
        ny = round(max(0.0, min(1.0, y + self._offset[1])), 2)
        if self.target == BPM:
            profile.bpm_x, profile.bpm_y = nx, ny
        else:
            profile.beat_text_x, profile.beat_text_y = nx, ny

    def release(self) -> bool:
        """放した。つまんでいたら True。"""
        held = self.target is not None
        self.target = None
        return held


def _fraction(rect: QRectF, pos: QPointF) -> tuple[float, float]:
    w = max(1.0, rect.width())
    h = max(1.0, rect.height())
    return (pos.x() - rect.left()) / w, (pos.y() - rect.top()) / h


def _place(profile: HeartProfile, target: str) -> tuple[float, float]:
    if target == BPM:
        return profile.bpm_x, profile.bpm_y
    return profile.beat_text_x, profile.beat_text_y
