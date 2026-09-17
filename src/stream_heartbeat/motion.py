"""血液が押し出される軌跡。描画座標は心臓中心からの相対。"""

from __future__ import annotations

import math


def ejection_blobs(eject: float, dt: float) -> list[tuple[float, float, float, float]]:
    if eject <= 0.02:
        return []
    blobs: list[tuple[float, float, float, float]] = []
    travel = max(0.0, dt - 0.04)
    for i in range(12):
        p = travel * 3.6 + i * 0.055
        if p <= 0.0 or p >= 1.15:
            continue
        clamped = min(p, 1.0)
        x = 0.06 + clamped * 0.46
        y = -0.10 - clamped * 0.50 + 0.035 * math.sin(i * 1.7)
        fade = max(0.0, 1.0 - p) * eject
        radius = 0.055 * fade * (1.15 - 0.45 * clamped)
        if fade < 0.04:
            continue
        blobs.append((x, y, radius, fade))
    return blobs
