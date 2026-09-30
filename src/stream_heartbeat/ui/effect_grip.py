"""心臓わしづかみ: 見ている人（視聴者）の手が、手前から心臓に触れて掴む絵。

手は絵の素材（assets/hand_touch.png。手の甲がこちらを向き、袖は窓の下の外へ伸びる）。
心臓の真ん中より少し下に手の甲を当て、指は心臓の前を上へ伸びる。
鼓動では手前へ押し返されて揺れる。握ると指が奥へ曲がって短く見え、指先が陰り、
関節が白み、手が細かく震える。素材を差し替えるときは下の目印の画素も合わせる。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QRadialGradient,
    QTransform,
)

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.ui.app_icon import assets_dir
from stream_heartbeat.ui.effects import HeartFrame, beat_jolt

HAND_IMAGE = "hand_touch.png"
# 素材の中の目印（素材の画素）
IMG_SIZE = (1024.0, 1536.0)
IMG_PALM = (505.0, 560.0)  # 手の甲の真ん中（心臓に当てる所）
IMG_KNUCKLE_Y = 440.0  # 指の付け根の関節の高さ。握るとここから先が奥へ曲がる
IMG_CENTER_X = 500.0  # 握ったときに指が寄っていく中心
IMG_HAND_WIDTH = 463.0  # 親指の先から小指の縁までの幅
IMG_KNUCKLES = ((405.0, 445.0), (478.0, 432.0), (560.0, 445.0), (628.0, 468.0))
IMG_ARM_SLOPE = 0.227  # 袖の傾き（下へ 1 進むと右へ進む量）
IMG_TAIL = 60.0  # 袖を窓の下まで伸ばすときに引き伸ばす下端の帯の高さ

# 心臓の半径に対する手の幅と、手の甲を当てる所（心臓の真ん中から、半径を単位に）
HAND_WIDTH_R = 1.5
HAND_ANCHOR = (0.04, 0.55)
# 握り切ったとき: 指の見かけの縮み・指先の寄り
CURL_SHRINK = 0.36
CURL_GATHER = 0.12
_STRIPS = 28

_source: QImage | None = None
_cache: tuple[int, QImage] | None = None


def hand_image() -> QImage:
    """素材を読む（読めなければ空の絵。描かずに済ませる）。"""
    global _source
    if _source is None:
        path = assets_dir() / HAND_IMAGE
        image = QImage(str(path)) if path.is_file() else QImage()
        if not image.isNull():
            image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        _source = image
    return _source


def _scaled(width_px: int) -> QImage:
    """画面の画素に近い大きさへ縮めた素材（毎回縮めると重いので、幅が変わるまで使い回す）。"""
    global _cache
    source = hand_image()
    width_px = max(16, min(int(IMG_SIZE[0]), width_px))
    # 鼓動の揺れ程度の違いでは作り直さない
    width_px -= width_px % 8
    if _cache is None or _cache[0] != width_px:
        scaled = source.scaledToWidth(width_px, Qt.TransformationMode.SmoothTransformation)
        _cache = (width_px, scaled)
    return _cache[1]


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
    image = _scaled(round(IMG_SIZE[0] * base * ratio))
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
    if g > 0.01:
        painter.drawImage(QRectF(0.0, 0.0, *IMG_SIZE), _curled(image, g))
    else:
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


def _curl_y(y: float, g: float) -> float:
    """握ったときの指の行の行き先（関節より上だけ縮む）。"""
    if y >= IMG_KNUCKLE_Y:
        return y
    return IMG_KNUCKLE_Y - (IMG_KNUCKLE_Y - y) * (1.0 - CURL_SHRINK * g)


def _curled(image: QImage, g: float) -> QImage:
    """指を奥へ曲げた絵（指の部分を縦に縮めて中へ寄せ、指先を陰らせ、関節を白ませる）。"""
    k = image.width() / IMG_SIZE[0]
    layer = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    layer.fill(Qt.GlobalColor.transparent)
    p = QPainter(layer)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.scale(k, k)
    knuckle = IMG_KNUCKLE_Y
    # 関節から下はそのまま
    p.drawImage(
        QRectF(0.0, knuckle, IMG_SIZE[0], IMG_SIZE[1] - knuckle),
        image,
        QRectF(0.0, knuckle * k, image.width(), (IMG_SIZE[1] - knuckle) * k),
    )
    for i in range(_STRIPS):
        y0 = knuckle * i / _STRIPS
        y1 = knuckle * (i + 1) / _STRIPS
        t = 1.0 - (y0 + y1) * 0.5 / knuckle
        gather = 1.0 - CURL_GATHER * g * t
        top = _curl_y(y0, g)
        # 帯の境目に隙間が出ないよう少し重ねる
        height = _curl_y(y1, g) - top + 0.8
        left = IMG_CENTER_X - IMG_CENTER_X * gather
        p.drawImage(
            QRectF(left, top, IMG_SIZE[0] * gather, height),
            image,
            QRectF(0.0, y0 * k, image.width(), (y1 - y0) * k),
        )
    # 描いた手の上にだけ色を重ねる
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
    tips = QLinearGradient(QPointF(0.0, knuckle), QPointF(0.0, _curl_y(40.0, g)))
    tips.setColorAt(0.0, QColor(70, 30, 20, 0))
    tips.setColorAt(1.0, QColor(70, 30, 20, int(95 * g)))
    p.fillRect(QRectF(0.0, 0.0, IMG_SIZE[0], knuckle), QBrush(tips))
    for x, y in IMG_KNUCKLES:
        glow = QRadialGradient(QPointF(x, y), 42.0)
        glow.setColorAt(0.0, QColor(255, 244, 236, int(150 * g)))
        glow.setColorAt(1.0, QColor(255, 244, 236, 0))
        p.fillRect(QRectF(x - 42.0, y - 42.0, 84.0, 84.0), QBrush(glow))
    p.end()
    return layer
