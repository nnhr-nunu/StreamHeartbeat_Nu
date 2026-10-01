"""心臓わしづかみ: 見ている人（視聴者）の手が、手前から心臓に触れて掴む絵（2D の代わり）。

立体の心臓を GL で描けるときは render/hand_gl が手を心臓へ巻き付けて描く。ここは GL が使えない
ときの代わりで、平らな手を重ねる。手は絵の素材 2 枚（assets/hand_touch.png が開いた手、
hand_grip.png が握った手。どちらも手の甲がこちらを向き、袖は窓の下の外へ伸びる）。
心臓の真ん中より少し下に手の甲を当て、指は心臓の前を上へ伸びる。
鼓動では手前へ押し返されて揺れる。握ると握った手の絵へ替わり、手が細かく震える。
素材を差し替えるときは下の目印の画素も合わせる。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QTransform

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.ui.app_icon import assets_dir
from stream_heartbeat.ui.effects import HeartFrame, beat_jolt

HAND_IMAGE = "hand_touch.png"
GRIP_IMAGE = "hand_grip.png"
# 素材の中の目印（素材の画素。2 枚とも同じ大きさ・同じ袖）
IMG_SIZE = (843.0, 1264.0)
IMG_PALM = (420.0, 560.0)  # 手の甲の真ん中（心臓に当てる所）
IMG_HAND_WIDTH = 409.0  # 親指の先から小指の縁まで
IMG_ARM_SLOPE = 0.175  # 袖の傾き（下へ 1 進むと右へ進む量）
IMG_TAIL = 50.0  # 袖を窓の下まで伸ばすときに引き伸ばす下端の帯の高さ

# 心臓の半径に対する手の幅と、手の甲を当てる所（心臓の真ん中から、半径を単位に）
HAND_WIDTH_R = 1.5
HAND_ANCHOR = (0.04, 0.55)
# 握った手の絵へ替わる所（握る強さ）
GRIP_SWAP = (0.2, 0.8)

_sources: dict[str, QImage] = {}
_cache: dict[str, tuple[int, QImage]] = {}


def _load(name: str) -> QImage:
    """素材を読む（読めなければ空の絵。描かずに済ませる）。"""
    if name not in _sources:
        path = assets_dir() / name
        image = QImage(str(path)) if path.is_file() else QImage()
        if not image.isNull():
            image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        _sources[name] = image
    return _sources[name]


def hand_image() -> QImage:
    """開いた手の素材。"""
    return _load(HAND_IMAGE)


def grip_image() -> QImage:
    """握った手の素材。"""
    return _load(GRIP_IMAGE)


def _scaled(name: str, width_px: int) -> QImage:
    """画面の画素に近い大きさへ縮めた素材（毎回縮めると重いので、幅が変わるまで使い回す）。"""
    width_px = max(16, min(int(IMG_SIZE[0]), width_px))
    # 鼓動の揺れ程度の違いでは作り直さない
    width_px -= width_px % 8
    cached = _cache.get(name)
    if cached is None or cached[0] != width_px:
        scaled = _load(name).scaledToWidth(width_px, Qt.TransformationMode.SmoothTransformation)
        cached = (width_px, scaled)
        _cache[name] = cached
    return cached[1]


def paint_grip_hand(
    painter: QPainter,
    rect: QRectF,
    frame: HeartFrame,
    cycle: CardiacCycle,
    *,
    grip: float,
    time_s: float,
    opacity: float,
) -> None:
    """心臓に触れて掴む手を描く（心臓の後に描く）。grip は握る強さ 0〜1。"""
    source = hand_image()
    radius = frame.radius
    if source.isNull() or radius <= 1.0:
        return
    g = max(0.0, min(1.0, grip))
    jolt = beat_jolt(cycle.squeeze, cycle.fill)
    base = HAND_WIDTH_R * radius / IMG_HAND_WIDTH
    ratio = painter.device().devicePixelRatioF() if painter.device() is not None else 1.0
    width_px = round(IMG_SIZE[0] * base * ratio)
    image = _scaled(HAND_IMAGE, width_px)
    swap = _smoothstep(GRIP_SWAP[0], GRIP_SWAP[1], g)
    if swap > 0.0 and not grip_image().isNull():
        image = _blended(image, _scaled(GRIP_IMAGE, width_px), swap)
    # 鼓動: 手前へ押し返されて少し大きく・下へ。握ると奥へ押し込んで少し小さく、震える
    scale = base * (1.0 + 0.035 * jolt - 0.035 * g)
    shake = radius * 0.012 * g
    anchor = QPointF(
        frame.center.x() + HAND_ANCHOR[0] * radius + shake * math.sin(time_s * 53.0),
        frame.center.y()
        + HAND_ANCHOR[1] * radius
        + radius * 0.035 * jolt
        + shake * math.cos(time_s * 61.0),
    )

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setOpacity(max(0.08, min(1.0, opacity)))
    painter.translate(anchor)
    painter.rotate(-1.2 * jolt)
    painter.scale(scale, scale)
    painter.translate(-IMG_PALM[0], -IMG_PALM[1])
    # ここから先は素材の画素の座標
    bottom = painter.transform().inverted()[0].map(QPointF(anchor.x(), rect.bottom())).y()
    _paint_sleeve_tail(painter, image, bottom)
    painter.drawImage(QRectF(0.0, 0.0, *IMG_SIZE), image)
    painter.restore()


def _paint_sleeve_tail(painter: QPainter, image: QImage, bottom: float) -> None:
    """心臓が小さいと袖の下端が窓の中に来るので、下端の帯を袖の向きに窓の下まで伸ばす。"""
    top = IMG_SIZE[1] - IMG_TAIL
    if bottom <= IMG_SIZE[1] - 2.0:
        return
    stretch = (bottom + 20.0 - top) / IMG_TAIL
    k = image.width() / IMG_SIZE[0]
    painter.save()
    painter.setTransform(
        QTransform(1.0, 0.0, IMG_ARM_SLOPE * stretch, stretch, 0.0, top), True
    )
    painter.drawImage(
        QRectF(0.0, 0.0, IMG_SIZE[0], IMG_TAIL),
        image,
        QRectF(0.0, top * k, image.width(), IMG_TAIL * k),
    )
    painter.restore()


def _blended(open_hand: QImage, grip_hand: QImage, t: float) -> QImage:
    """開いた手と握った手を t の割合で混ぜた絵（重なる所が薄くならないよう足し合わせる）。"""
    if t >= 1.0:
        return grip_hand
    layer = _faded(open_hand, 1.0 - t)
    p = QPainter(layer)
    # 足し合わせに不透明度を掛けると元の絵との間を取ってしまうので、薄めた絵を足す
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.drawImage(0, 0, _faded(grip_hand, t))
    p.end()
    return layer


def _faded(image: QImage, t: float) -> QImage:
    layer = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    layer.fill(Qt.GlobalColor.transparent)
    p = QPainter(layer)
    p.setOpacity(t)
    p.drawImage(0, 0, image)
    p.end()
    return layer


def _smoothstep(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)
