"""心拍数の数字を、心拍数ごとに 1 コマの絵（背景の透けた PNG）にする。VTube Studio のアイテム用。

コマの番号が「心拍数 − BPM_FRAME_MIN」になるよう、MIN_BPM〜MAX_BPM を順に並べる。
VTube Studio ではコマを流さず、心拍数が変わったらそのコマを出す。
数字の色・縁取り・大きさは配信用の窓の心拍数（「④ 心拍数」の設定）と同じ。
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from stream_heartbeat.config import MAX_BPM, MIN_BPM
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.ui.heart_paint import paint_bpm

BPM_FRAME_MIN = MIN_BPM
BPM_FRAME_MAX = MAX_BPM
# 大きさ 1 の数字の高さ（画素）。心臓のコマ（heart_frames.FRAME_SIZE 角）と同じ VTube Studio の
# 大きさで出すと、配信用の窓の心臓と数字の大きさの比と同じくらいになる
FONT_PX = 48
# 3 桁の数字と縁取りが収まる絵の幅・高さ（文字の高さに対する割合）
WIDTH_RATIO = 2.2
HEIGHT_RATIO = 1.4


def bpm_frame_index(bpm: float) -> int:
    """心拍数 bpm を出すコマの番号。"""
    return int(round(max(BPM_FRAME_MIN, min(BPM_FRAME_MAX, bpm)))) - BPM_FRAME_MIN


def bpm_font_px(profile: HeartProfile) -> int:
    return max(12, round(FONT_PX * max(0.4, min(3.0, profile.bpm_scale))))


def render_bpm_frames(profile: HeartProfile) -> list[QImage]:
    """MIN_BPM〜MAX_BPM の数字を 1 コマずつ描く（どのコマも同じ大きさ）。"""
    font_px = bpm_font_px(profile)
    width = max(64, round(font_px * WIDTH_RATIO))
    height = max(64, round(font_px * HEIGHT_RATIO))
    rect = QRectF(0, 0, width, height)
    frames: list[QImage] = []
    for bpm in range(BPM_FRAME_MIN, BPM_FRAME_MAX + 1):
        image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        paint_bpm(
            painter,
            rect,
            bpm,
            pos=(0.5, 0.5),
            color=profile.bpm_color,
            outline=profile.bpm_outline,
            font_px=font_px,
        )
        painter.end()
        frames.append(image)
    return frames
