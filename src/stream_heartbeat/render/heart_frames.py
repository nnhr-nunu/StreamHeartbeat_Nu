"""1 拍ぶんの心臓を、背景の透けたコマ画像（PNG）にする。VTube Studio のアイテム用。

コマは拍の瞬間（0 コマ目）から収縮・充満を経て、休んでいる形（最後のコマ）まで。
拍と拍のあいだは最後のコマで止めておき、次の拍でまた 0 コマ目から流す。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.heart_shaders import STYLE_LOOKS, Look, realistic_look

FRAME_FPS = 30.0
# 収縮から充満の終わりまで。これより後は休んでいる形と変わらない
FRAME_SECONDS = 0.66
FRAME_SIZE = 512
# コマを作るときの心拍数と、その収縮の長さ（再生の速さを拍の速さに合わせる基準）
FRAME_BPM = 72.0
FRAME_PREFIX = "StreamHeartbeat_"
# アイテムにできるスタイル。胸やパネルの絵があるもの・心電図は体に重ねる形にならない
ITEM_STYLES = frozenset({"realistic", "mech", "xray_heart", "cute"})
# アイテムの絵は窓より少し大きく描く（余白を減らす）。かわいいは元の絵が小さいので大きめ
ITEM_SCALE = 0.82
CUTE_ITEM_SCALE = 1.4


def beat_cycles() -> list[CardiacCycle]:
    """1 拍ぶんの形を FRAME_FPS で並べる。最後は休んでいる形。"""
    clock = BeatClock()
    interval = 60.0 / FRAME_BPM
    for i in range(8):
        clock.feed_beat(i * interval)
    last = 7 * interval
    count = int(FRAME_SECONDS * FRAME_FPS)
    cycles = [clock.cycle(last + k / FRAME_FPS) for k in range(count)]
    cycles.append(clock.cycle(last + interval * 0.9))
    return cycles


def frame_systole() -> float:
    """コマを作った心拍数での収縮の長さ（clock.cycle と同じ決め方）。"""
    interval = 60.0 / FRAME_BPM
    return min(0.34, max(0.20, interval * 0.36))


def _look(profile: HeartProfile) -> Look:
    if profile.style == "realistic":
        return realistic_look(profile.realistic_look)
    return STYLE_LOOKS[profile.style]


def render_frames(profile: HeartProfile, size: int = FRAME_SIZE) -> list[QImage]:
    """プロファイルのスタイル・向きで 1 拍ぶんのコマを描く。アイテムにできなければ空。"""
    if profile.style not in ITEM_STYLES:
        return []
    cycles = beat_cycles()
    interval = 60.0 / FRAME_BPM
    if profile.style == "cute":
        from stream_heartbeat.ui.heart_cute import paint_cute

        frames: list[QImage] = []
        for cycle in cycles:
            image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(QColor(0, 0, 0, 0))
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            paint_cute(painter, QRectF(0, 0, size, size), CUTE_ITEM_SCALE, cycle)
            painter.end()
            frames.append(image)
        return frames

    from stream_heartbeat.render.heart_gl import OffscreenHeart

    heart = OffscreenHeart()
    look = _look(profile)
    frames = []
    for k, cycle in enumerate(cycles):
        frames.append(
            heart.render(
                width=size,
                height=size,
                cycle=cycle,
                look=look,
                yaw_deg=profile.heart_yaw_deg,
                pitch_deg=profile.heart_pitch_deg,
                scale=ITEM_SCALE,
                opacity=1.0,
                time_s=k / FRAME_FPS if k < len(cycles) - 1 else interval * 0.9,
                background=QColor(0, 0, 0, 0),
            )
        )
    return frames


def write_frames(frames: list[QImage], folder: Path, tag: str | None = None) -> int:
    """コマを folder に書く（前のコマは消す）。書けたコマの数。

    VTube Studio は一度読んだ絵をファイル名で覚えていて、同じ名前で書き直しても
    （アイテムを出し直しても）前の絵を出し続ける。書くたびに名前へ tag を入れて変える。
    """
    if tag is None:
        tag = f"{time.time_ns() // 1_000_000:x}"
    folder.mkdir(parents=True, exist_ok=True)
    # このフォルダはアイテム専用。PNG が残っていると VTube Studio がコマとして混ぜるので全部消す
    for old in folder.glob("*.png"):
        old.unlink()
    for index, frame in enumerate(frames):
        # VTube Studio は名前の末尾の番号の順に並べる。桁をそろえて並びを崩さない
        if not frame.save(str(folder / f"{FRAME_PREFIX}{tag}_{index + 1:03d}.png")):
            raise OSError(f"コマを書けません: {folder}")
    return len(frames)


def count_frames(folder: Path) -> int:
    """folder に書いてあるコマの数（無ければ 0）。"""
    return sum(1 for _ in folder.glob("*.png")) if folder.is_dir() else 0
