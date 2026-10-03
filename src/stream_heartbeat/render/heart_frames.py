"""1 拍ぶんの心臓を、背景の透けたコマ画像（PNG）にする。VTube Studio のアイテム用。

コマは拍の瞬間（0 コマ目）から収縮・充満を経て、休んでいる形（最後のコマ）まで。
拍と拍のあいだは最後のコマで止めておき、次の拍でまた 0 コマ目から流す。

演出（心臓わしづかみの手・聴診器・はじけるハート）もコマに描き込む。クリックで強く握る・
聴診器がマウスについてくるといった操作は配信用の窓だけのもので、コマは手を添えたまま・
配信用の窓で置いた所に聴診器を当てたままの姿になる。
"""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.grip_pose import grip_pose, grip_squash, held_grip
from stream_heartbeat.render.heart_shaders import STYLE_LOOKS, Look, realistic_look
from stream_heartbeat.ui.effect_burst import paint_beat_pops
from stream_heartbeat.ui.effect_grip import paint_grip_hand
from stream_heartbeat.ui.effect_stetho import paint_stethoscope, stetho_radius
from stream_heartbeat.ui.effects import (
    BEAT_POP_KEEP_S,
    EFFECT_BURST,
    EFFECT_GRIP,
    EFFECT_STETHO,
    STETHO_EFFECTS,
    HeartFrame,
    active_effect,
    flat_heart_frame,
    gl_heart_frame,
    point_from_heart,
)
from stream_heartbeat.ui.heart_paint import CUTE_REIWA, heart_lift, paint_heart

FRAME_FPS = 30.0
# 収縮から充満の終わりまで。これより後は休んでいる形と変わらない
FRAME_SECONDS = 0.66
FRAME_SIZE = 512
# コマを作るときの心拍数と、その収縮の長さ（再生の速さを拍の速さに合わせる基準）
FRAME_BPM = 72.0
FRAME_PREFIX = "StreamHeartbeat_"
# アイテムにできるスタイル。胸やパネルの絵があるもの・心電図・窓いっぱいの絵は
# 体に重ねる形にならない
ITEM_STYLES = frozenset({"realistic", "mech", "xray_heart", "cute", "chic", "poly"})
# 2D で描くアイテム（向きが無い）
FLAT_ITEM_STYLES = frozenset({"cute", "chic"})
# コマに描き込む演出（ほかの演出はアイテムにできないスタイルのもの）
ITEM_EFFECTS = frozenset({EFFECT_GRIP, EFFECT_BURST, *STETHO_EFFECTS})
# アイテムの絵は窓より少し大きく描く（余白を減らす）。かわいい1 は元の絵が小さいので大きめ。
# まわりに飾りのある絵（かわいい2・オシャレ1）は飾りが切れない大きさ
ITEM_SCALE = 0.82
CUTE_ITEM_SCALE = 1.4
DECORATED_ITEM_SCALE = 1.0
# 聴診器を当てる所の遠さの上限（心臓の半径を 1 とする）。遠くに置いてあっても絵からはみ出さない
STETHO_REACH = 1.1
# 演出の絵を薄くし始める高さと、消えきる高さ（コマの高さに対する割合）
FADE_FROM = 0.78
FADE_TO = 0.98


def item_effect(profile: HeartProfile) -> str:
    """コマに描き込む演出（無ければ空）。"""
    effect = active_effect(profile.style, profile.effect)
    return effect if effect in ITEM_EFFECTS else ""


def beat_cycles(seconds: float = FRAME_SECONDS) -> list[CardiacCycle]:
    """1 拍ぶんの形を FRAME_FPS で並べる。最後は休んでいる形。"""
    clock = BeatClock()
    interval = 60.0 / FRAME_BPM
    for i in range(8):
        clock.feed_beat(i * interval)
    last = 7 * interval
    count = int(seconds * FRAME_FPS)
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


def render_frames(
    profile: HeartProfile, size: int = FRAME_SIZE, stetho: tuple[float, float] = (0.0, 0.0)
) -> list[QImage]:
    """プロファイルのスタイル・向き・演出で 1 拍ぶんのコマを描く。アイテムにできなければ空。

    stetho は聴診器を当てる所の、心臓の真ん中からのずれ（心臓の半径を 1 とする）。
    """
    if profile.style not in ITEM_STYLES:
        return []
    effect = item_effect(profile)
    # はじけるハートは消えきるまでコマにする
    seconds = max(FRAME_SECONDS, BEAT_POP_KEEP_S) if effect == EFFECT_BURST else FRAME_SECONDS
    cycles = beat_cycles(seconds)
    rest = len(cycles) - 1
    # 各コマの拍からの秒（最後は休んでいる形）
    ages = [k / FRAME_FPS for k in range(rest)] + [60.0 / FRAME_BPM * 0.9]
    rect = QRectF(0, 0, size, size)
    frames: list[QImage] = []
    if profile.style in FLAT_ITEM_STYLES:
        plain_cute = profile.style == "cute" and profile.realistic_look != CUTE_REIWA
        scale = CUTE_ITEM_SCALE if plain_cute else DECORATED_ITEM_SCALE
        # 配信用の窓の心臓は少し上へ寄せてあるが、コマは真ん中に描く（寄せた分を打ち消す）
        centered = rect.translated(0.0, heart_lift(profile.style) * size)
        frame = flat_heart_frame(centered, profile.style, scale, profile.realistic_look)
        for k, cycle in enumerate(cycles):
            image = _clear_image(size)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            paint_heart(
                painter,
                rect,
                style=profile.style,
                scale=scale,
                opacity=1.0,
                cycle=cycle,
                now=ages[k],
                look=profile.realistic_look,
            )
            painter.end()
            if effect:
                layer = _effect_layer(size, frame, effect, cycle, ages[k], k == rest, stetho)
                _overlay(image, layer)
            frames.append(image)
        return frames

    from stream_heartbeat.paths import cache_dir
    from stream_heartbeat.render.heart_gl import BASE_SCALE, OffscreenHeart
    from stream_heartbeat.render.mesh_cache import shared_heart_mesh

    # 配信用の窓と同じ形を使い回す（作り直すと 1.5 秒ほど止まる）
    heart = OffscreenHeart(shared_heart_mesh(cache_dir()))
    look = _look(profile)
    frame = gl_heart_frame(rect, ITEM_SCALE, look)
    grip = effect == EFFECT_GRIP
    # 手で掴んでいる間は、配信用の窓と同じく正面から見る（手の絵に合わせる）
    yaw = 0.0 if grip else profile.heart_yaw_deg
    pitch = 0.0 if grip else profile.heart_pitch_deg
    for k, cycle in enumerate(cycles):
        # 手を添えている間も、鼓動に合わせて握り直す強さで心臓が潰れる（配信用の窓と同じ）
        squash_x, squash_y = grip_squash(held_grip(0.0, cycle)) if grip else (1.0, 1.0)
        pose = None
        if grip:
            pose = grip_pose(
                shift=(look.shift_x, look.shift_y),
                size=BASE_SCALE * ITEM_SCALE * look.size_factor,
                cycle=cycle,
                grip=0.0,
                time_s=ages[k],
            )
        image = heart.render(
            width=size,
            height=size,
            cycle=cycle,
            look=look,
            yaw_deg=yaw,
            pitch_deg=pitch,
            scale=ITEM_SCALE,
            opacity=1.0,
            time_s=ages[k],
            background=QColor(0, 0, 0, 0),
            squash_x=squash_x,
            squash_y=squash_y,
            hand=pose,
        )
        layer = None
        if pose is not None:
            # GL の手を描けなければ、平らな手を重ねる
            layer = heart.render_hand(
                width=size,
                height=size,
                pose=pose,
                opacity=1.0,
                see_through=look.additive or look.cutout,
            )
        if layer is None and effect:
            layer = _effect_layer(size, frame, effect, cycle, ages[k], k == rest, stetho)
        if layer is not None:
            _overlay(image, layer)
        frames.append(image)
    return frames


def _clear_image(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    return image


def _overlay(image: QImage, layer: QImage) -> None:
    """演出の絵を心臓の上に重ねる。手首や聴診器の管がコマの下端で切れて見えないよう、
    演出の絵だけ下端へ向けて薄くしてから重ねる（配信用の窓では窓の下から来ている）。"""
    h = layer.height()
    painter = QPainter(layer)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    fade = QLinearGradient(0.0, h * FADE_FROM, 0.0, h * FADE_TO)
    fade.setColorAt(0.0, QColor(0, 0, 0, 255))
    fade.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(layer.rect(), fade)
    painter.end()
    painter = QPainter(image)
    painter.drawImage(0, 0, layer)
    painter.end()


def _effect_layer(
    size: int,
    frame: HeartFrame,
    effect: str,
    cycle: CardiacCycle,
    age: float,
    resting: bool,
    stetho: tuple[float, float],
) -> QImage:
    """心臓の上に重ねる演出（平らな手・聴診器・はじけるハート）を、背景の透けた絵にする。"""
    layer = _clear_image(size)
    rect = QRectF(0, 0, size, size)
    painter = QPainter(layer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if effect == EFFECT_GRIP:
        paint_grip_hand(painter, rect, frame, cycle, grip=0.0, time_s=age, opacity=1.0)
    elif effect in STETHO_EFFECTS:
        pos = point_from_heart(frame, stetho, STETHO_REACH)
        # チェストピースは薄くする所より上に当てる（下に置いてあっても消えかけない）
        pos.setY(min(pos.y(), size * FADE_FROM - stetho_radius(frame) * 1.2))
        paint_stethoscope(
            painter,
            rect,
            pos,
            frame,
            cycle,
            time_s=age,
            opacity=1.0,
            back_view=effect == EFFECT_STETHO,
        )
    elif effect == EFFECT_BURST and not resting:
        paint_beat_pops(painter, frame.center, frame.radius, [(age, 0.0)])
    painter.end()
    return layer


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
