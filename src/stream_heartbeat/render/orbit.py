"""配信用キャンバスのドラッグで心臓を回す角度計算。"""

from __future__ import annotations

from dataclasses import dataclass

DEG_PER_PIXEL = 0.35
PITCH_LIMIT = 89.0
DEFAULT_YAW = -18.0
DEFAULT_PITCH = 12.0


@dataclass
class Orbit:
    yaw: float = DEFAULT_YAW
    pitch: float = DEFAULT_PITCH

    def drag(self, dx: float, dy: float) -> None:
        self.yaw = wrap_yaw(self.yaw + dx * DEG_PER_PIXEL)
        self.pitch = clamp_pitch(self.pitch + dy * DEG_PER_PIXEL)

    def reset(self) -> None:
        self.yaw = DEFAULT_YAW
        self.pitch = DEFAULT_PITCH


def wrap_yaw(yaw: float) -> float:
    yaw = (yaw + 180.0) % 360.0 - 180.0
    return yaw


def clamp_pitch(pitch: float) -> float:
    return max(-PITCH_LIMIT, min(PITCH_LIMIT, pitch))
