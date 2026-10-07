"""1 拍ぶんの心臓を、背景の透けたコマ画像（PNG）にする。VTube Studio のアイテム用。

コマは拍の瞬間（0 コマ目）から収縮・充満を経て、休んでいる形（最後のコマ）まで。
拍と拍のあいだは最後のコマで止めておき、次の拍でまた 0 コマ目から流す。

演出（心臓わしづかみの手・聴診器・はじけるハート）もコマに描き込む。聴診器がマウスについてくる
といった操作は配信用の窓だけのもので、コマは配信用の窓で置いた所に聴診器を当てたままの姿になる。
心臓わしづかみは、休んでいる形のあとに「ぎゅっ」と握って緩めるコマも足せる（squeeze）。
VTube Studio で心臓をクリックしたときに、そこだけを流す。

拍の文字（❤ やドクンなど）も、配信用の窓で心臓に対して置いてある所・大きさのまま描き込める。
コマは毎回同じ絵なので、窓のような拍ごとの位置・傾きの揺れは無い。
肋骨（レントゲン4）や遠くの文字が切れないよう、コマは心臓のまわりを広げて描くことがある
（item_zoom 倍）。心臓の画素の大きさは変えずに絵の一辺を広げる。VTube Studio は絵の画素数で
大きさを決めるので、渡す大きさ（size）はそのままで心臓の見かけの大きさは変わらない（実機で確認）。
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QLinearGradient, QPainter

from stream_heartbeat.clock import BeatClock, CardiacCycle
from stream_heartbeat.config import BURST_FADE_IN_S, BURST_FADE_OUT_S, BURST_HOLD_S
from stream_heartbeat.overlay import burst_font_px, lean_angle_deg
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.grip_pose import grip_pose, grip_squash, held_grip
from stream_heartbeat.render.heart_looks import Look, style_look
from stream_heartbeat.render.model_body import follow_scale, grip_for_look
from stream_heartbeat.ui.effect_burst import paint_beat_pops
from stream_heartbeat.ui.effect_grip import paint_grip_hand
from stream_heartbeat.ui.effect_stetho import paint_stethoscope, stetho_radius
from stream_heartbeat.ui.effects import (
    BEAT_POP_KEEP_S,
    EFFECT_BURST,
    EFFECT_GRIP,
    EFFECT_STETHO,
    STETHO_EFFECTS,
    EffectMotion,
    HeartFrame,
    active_effect,
    flat_heart_frame,
    gl_heart_frame,
    heart_offset,
    point_from_heart,
)
from stream_heartbeat.ui.heart_paint import (
    CUTE_REIWA,
    beat_word_font,
    heart_lift,
    paint_beat_word,
    paint_heart,
)

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
# 肋骨（レントゲン4）は心臓のまわりに広く写るので、コマをこの倍の広さで描く
# （肋骨が薄れて消える所までコマに収める。窓の端で切ると、配信でそこだけ真っすぐ切れて見える）
RIB_ITEM_ZOOM = 1.5
# コマを広げる上限。拍の文字が遠くに置いてあっても、これより広げずに文字の方をコマへ寄せる
ITEM_ZOOM_MAX = 2.0
# 拍の文字の置き場所を写すときの配信用の窓（正方形なら大きさによらず同じ所になる）
TEXT_WINDOW = 720.0
# 拍の文字の出始めから消えきるまで（overlay の bursts_at と同じ）
TEXT_SECONDS = BURST_FADE_IN_S + BURST_HOLD_S + BURST_FADE_OUT_S
# 文字の縁取り（heart_paint は上下左右に 2px ずらして重ねる）と、コマの端までの余り
TEXT_MARGIN_PX = 6.0
# 「ぎゅっ」のコマは、この握りの強さまで緩んだら休んでいる形のコマで終える
SQUEEZE_END = 0.05
# コマを PNG に書くときに並べて動かす数（書き出しの間、操作画面と配信用の窓が止まるので短くする）
WRITE_WORKERS = 4


@dataclass(frozen=True)
class ItemText:
    """コマに描く拍の文字。dx・dy は心臓の真ん中から文字の基準点（左下）までの画素。

    画素は広げていないコマ（item_zoom が 1・size 角）でのもの。広げても心臓の画素の大きさは
    変わらないので、そのまま使える。
    """

    text: str
    dx: float
    dy: float
    font_px: int
    angle: float
    opacity: float
    color: str
    outline: str


def item_effect(profile: HeartProfile) -> str:
    """コマに描き込む演出（無ければ空）。"""
    effect = active_effect(profile.style, profile.effect)
    return effect if effect in ITEM_EFFECTS else ""


def _flat_scale(profile: HeartProfile) -> float:
    plain_cute = profile.style == "cute" and profile.realistic_look != CUTE_REIWA
    return CUTE_ITEM_SCALE if plain_cute else DECORATED_ITEM_SCALE


def _item_frame(profile: HeartProfile, side: float, zoom: float = 1.0) -> HeartFrame:
    """コマ（side 角・zoom 倍に広げて描く）の上の心臓の置き場所。"""
    rect = QRectF(0, 0, side, side)
    if profile.style in FLAT_ITEM_STYLES:
        # 配信用の窓の心臓は少し上へ寄せてあるが、コマは真ん中に描く（寄せた分を打ち消す）
        centered = rect.translated(0.0, heart_lift(profile.style) * side)
        return flat_heart_frame(
            centered, profile.style, _flat_scale(profile) / zoom, profile.realistic_look
        )
    return gl_heart_frame(rect, ITEM_SCALE / zoom, _look(profile))


def _window_frame(profile: HeartProfile, rect: QRectF) -> HeartFrame:
    """配信用の窓の心臓の置き場所（output_window の _heart_frame と同じ）。"""
    if profile.style in FLAT_ITEM_STYLES:
        return flat_heart_frame(rect, profile.style, profile.scale, profile.realistic_look)
    return gl_heart_frame(rect, profile.scale, _look(profile), heart_lift(profile.style))


def item_text(profile: HeartProfile, size: int = FRAME_SIZE) -> ItemText | None:
    """配信用の窓の拍の文字を、コマの心臓に対して同じ所・同じ大きさに置く（出さなければ None）。"""
    text = profile.beat_text.strip()
    if not profile.show_beat_text or not text or profile.style not in ITEM_STYLES:
        return None
    window = _window_frame(profile, QRectF(0, 0, TEXT_WINDOW, TEXT_WINDOW))
    item = _item_frame(profile, size)
    ratio = item.radius / max(1.0, window.radius)
    pos = (profile.beat_text_x, profile.beat_text_y)
    offset = heart_offset(window, QPointF(pos[0] * TEXT_WINDOW, pos[1] * TEXT_WINDOW))
    radius = max(1.0, item.radius)
    return ItemText(
        text=text,
        dx=offset[0] * radius,
        dy=offset[1] * radius,
        font_px=max(8, round(burst_font_px(TEXT_WINDOW, profile.beat_text_scale) * ratio)),
        angle=lean_angle_deg(pos, profile.beat_text_tilt),
        opacity=max(0.0, min(1.0, profile.beat_text_opacity)),
        color=profile.beat_text_color,
        outline=profile.beat_text_outline,
    )


def _text_corners(word: ItemText, anchor: QPointF) -> list[QPointF]:
    """文字の外枠の四隅（基準点 anchor のまわりに angle 度回したもの）。"""
    size = float(word.font_px)
    box = QFontMetricsF(beat_word_font(word.font_px)).boundingRect(word.text)
    if box.isEmpty() or abs(box.left()) > size * 4 or abs(box.top()) > size * 4:
        # フォントが無い環境（テストの offscreen）では寸法が当てにならない。文字数から見積もる
        box = QRectF(0.0, -size, size * len(word.text), size * 1.25)
    box = box.adjusted(-TEXT_MARGIN_PX, -TEXT_MARGIN_PX, TEXT_MARGIN_PX, TEXT_MARGIN_PX)
    turn = math.radians(word.angle)
    cos, sin = math.cos(turn), math.sin(turn)
    corners = (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight())
    return [
        QPointF(anchor.x() + c.x() * cos - c.y() * sin, anchor.y() + c.x() * sin + c.y() * cos)
        for c in corners
    ]


def item_zoom(profile: HeartProfile, text: bool = True, size: int = FRAME_SIZE) -> float:
    """コマを心臓のまわりにどれだけ広げて描くか（1 がふつう）。text は拍の文字も描くか。"""
    if profile.style not in ITEM_STYLES:
        return 1.0
    flat = profile.style in FLAT_ITEM_STYLES
    zoom = RIB_ITEM_ZOOM if not flat and _look(profile).bones else 1.0
    word = item_text(profile, size) if text else None
    if word is not None:
        heart = _item_frame(profile, size).center
        anchor = QPointF(heart.x() + word.dx, heart.y() + word.dy)
        half = size / 2.0
        reach = max(
            max(abs(c.x() - half), abs(c.y() - half)) for c in _text_corners(word, anchor)
        )
        zoom = max(zoom, reach / half)
    return min(ITEM_ZOOM_MAX, zoom)


def _text_alpha(age: float) -> float:
    """拍からの秒 age での拍の文字の濃さ（overlay の bursts_at と同じ出方）。"""
    if age < 0.0 or age > TEXT_SECONDS:
        return 0.0
    if age < BURST_FADE_IN_S:
        return age / BURST_FADE_IN_S
    if age < BURST_FADE_IN_S + BURST_HOLD_S:
        return 1.0
    return max(0.0, 1.0 - (age - BURST_FADE_IN_S - BURST_HOLD_S) / BURST_FADE_OUT_S)


def _text_anchor(word: ItemText, heart: QPointF, side: float) -> QPointF:
    """文字の基準点。上限まで広げても収まらない遠い文字は、コマの中へ寄せる。"""
    anchor = QPointF(heart.x() + word.dx, heart.y() + word.dy)
    corners = _text_corners(word, anchor)
    xs = [c.x() for c in corners]
    ys = [c.y() for c in corners]
    shift_x = max(0.0, -min(xs)) - max(0.0, max(xs) - side)
    shift_y = max(0.0, -min(ys)) - max(0.0, max(ys) - side)
    return QPointF(anchor.x() + shift_x, anchor.y() + shift_y)


def _paint_text(image: QImage, word: ItemText, anchor: QPointF, age: float) -> None:
    alpha = _text_alpha(age) * word.opacity
    if alpha <= 0.0:
        return
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    paint_beat_word(
        painter,
        anchor,
        word.text,
        font_px=word.font_px,
        angle=word.angle,
        opacity=alpha,
        color=word.color,
        outline=word.outline,
    )
    painter.end()


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


@cache
def squeeze_grips() -> tuple[float, ...]:
    """「ぎゅっ」の各コマの握りの強さ。配信用の窓で 1 回クリックしたときと同じ握り込み・緩め方で、
    最後は休んでいる形（0）。"""
    motion = EffectMotion()
    rest = (0.5, 0.5)
    motion.step(0.0, rest)
    motion.press(0.0)
    motion.release()
    grips: list[float] = []
    k = 1
    while k == 1 or motion.grip >= SQUEEZE_END:
        motion.step(k / FRAME_FPS, rest)
        grips.append(motion.grip)
        k += 1
    grips.append(0.0)
    return tuple(grips)


def squeeze_frame_count(profile: HeartProfile) -> int:
    """render_frames(squeeze=True) が休んでいる形のあとに足す「ぎゅっ」のコマの数（無ければ 0）。"""
    return len(squeeze_grips()) if item_effect(profile) == EFFECT_GRIP else 0


def frame_systole() -> float:
    """コマを作った心拍数での収縮の長さ（clock.cycle と同じ決め方）。"""
    interval = 60.0 / FRAME_BPM
    return min(0.34, max(0.20, interval * 0.36))


def _look(profile: HeartProfile) -> Look:
    return style_look(
        profile.style, profile.realistic_look, profile.heart_material, profile.xray_material
    )


def frame_side(size: int, zoom: float) -> int:
    """広げて描くコマの一辺の画素（心臓の画素の大きさは size 角のときと同じ）。"""
    return max(size, round(size * zoom))


def render_frames(
    profile: HeartProfile,
    size: int = FRAME_SIZE,
    stetho: tuple[float, float] = (0.0, 0.0),
    text: bool = False,
    squeeze: bool = False,
) -> list[QImage]:
    """プロファイルのスタイル・向き・演出で 1 拍ぶんのコマを描く。アイテムにできなければ空。

    stetho は聴診器を当てる所の、心臓の真ん中からのずれ（心臓の半径を 1 とする）。
    text は拍の文字も描くか。コマは item_zoom(profile, text) 倍に広げて描く
    （一辺は frame_side。心臓の画素の大きさは size 角のときと同じ）。
    squeeze が真で演出が心臓わしづかみなら、休んでいる形のあとに「ぎゅっ」のコマ
    （squeeze_frame_count 枚。拍の文字は無し）を足す。
    """
    if profile.style not in ITEM_STYLES:
        return []
    effect = item_effect(profile)
    word = item_text(profile, size) if text else None
    side = frame_side(size, item_zoom(profile, text, size))
    zoom = side / size
    # はじけるハート・拍の文字は消えきるまでコマにする
    seconds = FRAME_SECONDS
    if effect == EFFECT_BURST:
        seconds = max(seconds, BEAT_POP_KEEP_S)
    if word is not None:
        seconds = max(seconds, TEXT_SECONDS)
    cycles = beat_cycles(seconds)
    rest = len(cycles) - 1
    # 各コマの拍からの秒（最後は休んでいる形）と握りの強さ
    ages = [k / FRAME_FPS for k in range(rest)] + [60.0 / FRAME_BPM * 0.9]
    grips = [0.0] * len(cycles)
    if squeeze and effect == EFFECT_GRIP:
        # 「ぎゅっ」は休んでいる形の心臓を握る。秒は休んでいる形から続ける（手の震えの位相）
        extra = squeeze_grips()
        cycles += [cycles[rest]] * len(extra)
        ages += [ages[rest] + (k + 1) / FRAME_FPS for k in range(len(extra))]
        grips += list(extra)
    frame = _item_frame(profile, side, zoom)
    anchor = _text_anchor(word, frame.center, side) if word is not None else None
    if profile.style in FLAT_ITEM_STYLES:
        frames = _flat_frames(profile, side, zoom, frame, effect, cycles, ages, stetho, grips, rest)
    else:
        frames = _gl_frames(profile, side, zoom, frame, effect, cycles, ages, stetho, grips, rest)
    if word is not None and anchor is not None:
        for k, image in enumerate(frames[:rest]):
            _paint_text(image, word, anchor, ages[k])
    return frames


def _flat_frames(
    profile: HeartProfile,
    side: int,
    zoom: float,
    frame: HeartFrame,
    effect: str,
    cycles: list[CardiacCycle],
    ages: list[float],
    stetho: tuple[float, float],
    grips: list[float],
    rest: int,
) -> list[QImage]:
    """rest は休んでいる形のコマの番号（それより後は「ぎゅっ」のコマ）。"""
    rect = QRectF(0, 0, side, side)
    scale = _flat_scale(profile) / zoom
    frames: list[QImage] = []
    for k, cycle in enumerate(cycles):
        image = _clear_image(side)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if grips[k] > 0.0:
            # 「ぎゅっ」と握ると、配信用の窓と同じく心臓が真ん中を軸に潰れる
            squash_x, squash_y = grip_squash(held_grip(grips[k], cycle))
            painter.translate(frame.center)
            painter.scale(squash_x, squash_y)
            painter.translate(-frame.center)
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
            layer = _effect_layer(
                side, frame, effect, cycle, ages[k], k >= rest, stetho, grip=grips[k]
            )
            _overlay(image, layer)
        frames.append(image)
    return frames


def _gl_frames(
    profile: HeartProfile,
    side: int,
    zoom: float,
    frame: HeartFrame,
    effect: str,
    cycles: list[CardiacCycle],
    ages: list[float],
    stetho: tuple[float, float],
    grips: list[float],
    rest: int,
) -> list[QImage]:
    from stream_heartbeat.paths import cache_dir
    from stream_heartbeat.render.heart_gl import BASE_SCALE, OffscreenHeart
    from stream_heartbeat.render.mesh_cache import shared_heart_mesh

    # 配信用の窓と同じ形を使い回す（作り直すと 1.5 秒ほど止まる）
    heart = OffscreenHeart(shared_heart_mesh(cache_dir()))
    look = _look(profile)
    scale = ITEM_SCALE / zoom
    frames: list[QImage] = []
    grip = effect == EFFECT_GRIP
    # 手で掴んでいる間は、配信用の窓と同じく正面から見る（手の絵に合わせる）
    yaw = 0.0 if grip else profile.heart_yaw_deg
    pitch = 0.0 if grip else profile.heart_pitch_deg
    for k, cycle in enumerate(cycles):
        # 手を添えている間も、鼓動に合わせて握り直す強さで心臓が潰れる（配信用の窓と同じ。
        # Blender の心臓は手の胴と握り直しをその形と縮みに合わせる）
        body, grip_cycle = grip_for_look(look, cycle)
        squash_x, squash_y = grip_squash(held_grip(grips[k], grip_cycle)) if grip else (1.0, 1.0)
        pose = None
        if grip:
            pose = grip_pose(
                shift=(look.shift_x, look.shift_y),
                size=BASE_SCALE * scale * look.size_factor,
                cycle=grip_cycle,
                grip=grips[k],
                time_s=ages[k],
                body=body,
            )
        image = heart.render(
            width=side,
            height=side,
            cycle=cycle,
            look=look,
            yaw_deg=yaw,
            pitch_deg=pitch,
            scale=scale,
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
                width=side,
                height=side,
                pose=pose,
                opacity=1.0,
                see_through=look.additive or look.cutout,
            )
        if layer is None and effect:
            model = look.program == "model"
            layer = _effect_layer(
                side, frame, effect, cycle, ages[k], k >= rest, stetho, model, grip=grips[k]
            )
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
    model: bool = False,
    grip: float = 0.0,
) -> QImage:
    """心臓の上に重ねる演出（平らな手・聴診器・はじけるハート）を、背景の透けた絵にする。

    model は Blender の心臓（形が縮むので、聴診器を当てた所も表面と一緒に寄る）。
    grip は手の握りの強さ（「ぎゅっ」のコマ）。
    """
    layer = _clear_image(size)
    rect = QRectF(0, 0, size, size)
    painter = QPainter(layer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if effect == EFFECT_GRIP:
        paint_grip_hand(painter, rect, frame, cycle, grip=grip, time_s=age, opacity=1.0)
    elif effect in STETHO_EFFECTS:
        pos = point_from_heart(frame, stetho, STETHO_REACH)
        # チェストピースは薄くする所より上に当てる（下に置いてあっても消えかけない）
        pos.setY(min(pos.y(), size * FADE_FROM - stetho_radius(frame) * 1.2))
        if model:
            away = pos - frame.center
            pos = frame.center + away * follow_scale(cycle, away.x(), -away.y())
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
    # VTube Studio は名前の末尾の番号の順に並べる。桁をそろえて並びを崩さない
    paths = [str(folder / f"{FRAME_PREFIX}{tag}_{i + 1:03d}.png") for i in range(len(frames))]
    with ThreadPoolExecutor(max_workers=WRITE_WORKERS) as pool:
        saved = list(pool.map(lambda job: job[0].save(job[1]), zip(frames, paths, strict=True)))
    if not all(saved):
        raise OSError(f"コマを書けません: {folder}")
    return len(frames)


def count_frames(folder: Path) -> int:
    """folder に書いてあるコマの数（無ければ 0）。"""
    return sum(1 for _ in folder.glob("*.png")) if folder.is_dir() else 0
