"""配信用の窓で、拍の文字と心拍数をマウスでつまんで動かす。

操作画面のつまみ（左右・上下）と同じ値（窓の幅・高さに対する割合）を書き換える。
動かせる範囲は窓の中なので、どこまで動かせるかが見て分かる。
窓のクリックは演出（握る・聴診器など）が主なので、つまめるのは見えている文字だけ。
拍の文字は拍のたびに少しずれた所へ出るので、出ている文字をつまむと、つまんだ文字が
マウスについてくる（置き場所はゆらぎの真ん中）。つまんでいる間は文字をはっきり出しておく。
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
# 出始め・消えかけ（この濃さまで）の拍の文字はつまめない。透明度の設定は掛けない
# （透明度を低くしていても、出ている文字はつまめる）
GRAB_ALPHA = 0.25


def label_at(
    rect: QRectF,
    profile: HeartProfile,
    pos: QPointF,
    bpm: int | str,
    bursts: list[FloatBurst],
) -> str | None:
    """pos にある文字（BPM / BEAT）。手前に描く心拍数を先に見る。bursts は今出ている拍の文字。"""
    if _bpm_hit(rect, profile, pos, bpm):
        return BPM
    if _beat_hit(rect, profile, pos, bursts) is not None:
        return BEAT
    return None


def beat_preview(profile: HeartProfile, pos: tuple[float, float] | None = None) -> FloatBurst:
    """つまんでいる間に出す拍の文字（はっきり）。pos はつまんでいる文字の今の所
    （省くとゆらぎ無しの置き場所）。"""
    if pos is None:
        pos = (profile.beat_text_x, profile.beat_text_y)
    angle = lean_angle_deg(pos, profile.beat_text_tilt)
    return FloatBurst(text=profile.beat_text.strip(), pos=pos, alpha=1.0, angle=angle)


def _bpm_hit(rect: QRectF, profile: HeartProfile, pos: QPointF, bpm: int | str) -> bool:
    if not profile.show_bpm:
        return False
    box = bpm_box(rect, bpm, scale=profile.bpm_scale, pos=(profile.bpm_x, profile.bpm_y))
    return _grow(box, rect).contains(pos)


def _beat_hit(
    rect: QRectF, profile: HeartProfile, pos: QPointF, bursts: list[FloatBurst]
) -> FloatBurst | None:
    """pos にある、今はっきり出ている拍の文字（描いたとおりの外枠で見る）。新しいものを先に見る。"""
    if not profile.show_beat_text:
        return None
    font_px = burst_font_px(min(rect.width(), rect.height()), profile.beat_text_scale)
    for burst in reversed(bursts):
        if burst.alpha < GRAB_ALPHA or not burst.text:
            continue
        point = QPointF(
            rect.left() + burst.pos[0] * rect.width(), rect.top() + burst.pos[1] * rect.height()
        )
        box = beat_word_box(point, burst.text, font_px=font_px, angle=burst.angle)
        if _grow(box, rect).contains(pos):
            return burst
    return None


def _grow(box: QRectF, rect: QRectF) -> QRectF:
    m = GRAB_MARGIN * min(rect.width(), rect.height())
    return box.adjusted(-m, -m, m, m)


class LabelDrag:
    """つまんでいる文字と、つまんだ所から文字の置き場所までのずれ。"""

    def __init__(self) -> None:
        self.target: str | None = None
        self._offset = (0.0, 0.0)
        # つまんでいる拍の文字の今の所（押しただけでは置き場所を書き換えないので、ここに出す）
        self.held: tuple[float, float] | None = None

    @property
    def dragging(self) -> bool:
        return self.target is not None

    def press(
        self,
        rect: QRectF,
        profile: HeartProfile,
        pos: QPointF,
        bpm: int | str,
        bursts: list[FloatBurst],
    ) -> bool:
        """文字の上で押したらつまむ。つまんだら True。"""
        x, y = _fraction(rect, pos)
        if _bpm_hit(rect, profile, pos, bpm):
            self.target = BPM
            self._offset = (profile.bpm_x - x, profile.bpm_y - y)
            return True
        burst = _beat_hit(rect, profile, pos, bursts)
        if burst is None:
            return False
        # つまんだ文字（ゆらぎでずれた所）がマウスについてくるよう、その文字からのずれを持つ
        self.target = BEAT
        self._offset = (burst.pos[0] - x, burst.pos[1] - y)
        self.held = burst.pos
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
            self.held = (nx, ny)

    def release(self) -> bool:
        """放した。つまんでいたら True。"""
        held = self.target is not None
        self.target = None
        self.held = None
        return held


def _fraction(rect: QRectF, pos: QPointF) -> tuple[float, float]:
    w = max(1.0, rect.width())
    h = max(1.0, rect.height())
    return (pos.x() - rect.left()) / w, (pos.y() - rect.top()) / h
