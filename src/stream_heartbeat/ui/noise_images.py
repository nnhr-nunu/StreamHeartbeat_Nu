"""スペックルや粒子のタイル画像。起動後に一度だけ作って使い回す。"""

from __future__ import annotations

import math

from PySide6.QtGui import QColor, QImage

TILE = 256
_CACHE: dict[tuple[str, int], QImage] = {}


def _hash(x: int, y: int, seed: int) -> int:
    n = x * 1664525 + y * 1013904223 + seed * 2246822519
    n &= 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n >> 16) & 255


def speckle_tile(seed: int) -> QImage:
    """心エコーのスペックル。明るい粒が疎らに、暗い粒が多め。"""
    key = ("speckle", seed)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    image = QImage(TILE, TILE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    for y in range(TILE):
        for x in range(TILE):
            a = _hash(x, y, seed)
            b = _hash(x // 2, y // 2, seed + 7)
            c = _hash(x // 4, y // 3, seed + 19)
            v = a * 0.55 + b * 0.30 + c * 0.15
            if v > 176:
                strength = min(255, int((v - 176) * 4.2))
                image.setPixelColor(x, y, QColor(236, 242, 250, strength))
            elif v < 84:
                strength = min(255, int((84 - v) * 3.0))
                image.setPixelColor(x, y, QColor(0, 0, 0, strength))
    _CACHE[key] = image
    return image


def tissue_tile(seed: int) -> QImage:
    """心エコーの組織。灰色の粒が密に詰まり、ところどころ明るい反射。"""
    key = ("tissue", seed)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    image = QImage(TILE, TILE, QImage.Format.Format_ARGB32_Premultiplied)
    for y in range(TILE):
        for x in range(TILE):
            a = _hash(x, y, seed)
            b = _hash(x // 2, y // 2, seed + 5)
            c = _hash(x // 5, y // 3, seed + 13)
            v = a * 0.45 + b * 0.35 + c * 0.20
            gray = int(56 + v * 0.66)
            if v > 205:
                gray = min(255, gray + 50)
            image.setPixelColor(x, y, QColor(gray, gray + 3, gray + 8, 255))
    _CACHE[key] = image
    return image


def grain_tile(seed: int, color: QColor, density: int = 150) -> QImage:
    """MRI・レントゲンの粒子。単色の点が疎らに乗る。"""
    key = (f"grain-{color.name()}-{density}", seed)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    image = QImage(TILE, TILE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    for y in range(TILE):
        for x in range(TILE):
            n = _hash(x, y, seed)
            if n < density:
                continue
            alpha = min(255, (n - density + 6) * 4)
            image.setPixelColor(x, y, QColor(color.red(), color.green(), color.blue(), alpha))
    _CACHE[key] = image
    return image


def lung_tile(seed: int) -> QImage:
    """肺野のもや。柔らかい濃淡と細い血管影。"""
    key = ("lung", seed)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    image = QImage(TILE, TILE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(0, 0, 0, 0))
    for y in range(TILE):
        for x in range(TILE):
            soft = _hash(x // 16, y // 16, seed) * 0.5 + _hash(x // 8, y // 8, seed + 3) * 0.5
            fine = _hash(x, y, seed + 11)
            vessel = abs(math.sin(x * 0.11 + y * 0.07 + soft * 0.02)) < 0.03
            alpha = int(soft * 0.18 + fine * 0.10)
            if vessel:
                alpha += 60
            image.setPixelColor(x, y, QColor(200, 210, 222, min(255, alpha)))
    _CACHE[key] = image
    return image
