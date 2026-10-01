"""心臓に重ねる演出の選び方と動き。どのスタイルにも 1 つ以上の演出がある。

手と聴診器は、見ている人（視聴者）が手前から触れる向きで描く（手も聴診器の管も窓の下から来る）。
- 心臓わしづかみ: レントゲン 1〜3 で、ふつうの手が心臓に触れて掴む。鼓動で揺れ、
  配信用の窓を押すと強く握る
- 聴診器1・2: 心臓の形が出るスタイルで、マウスの所にチェストピースが来て鼓動で揺れる。
  1 は当てている人から見える裏側（ベルの側）、2 は膜の面をこちらへ向けた姿。
  クリックした所に置いておけ、マウスが窓の外へ出るとそこへ戻る
- カラードプラ（心エコー）: 弁を抜ける血の流れを赤・青で重ねる（echo_gl が描く）
- タギング（MRI）: 拍の頭に格子の縞を焼き付け、縞が心筋と一緒に曲がりながら薄れる（mri_gl）
- モニター画面（心電図）: ベッドサイドのモニターの画面に映す（effect_monitor）
- はじけるハート（どのスタイルでも）: 配信用の窓をクリックした所からハートがはじける

手・聴診器・ハートの絵は effect_grip / effect_stetho / effect_burst が描く。ここは描く場所
（心臓の画面上の位置と大きさ）と、時間で滑らかに追う値（握る強さ・聴診器の位置・はじけた時刻）を
受け持つ。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF

from stream_heartbeat.render.heart_gl import CAMERA_DISTANCE, CAMERA_TARGET_Y, FOV_DEG
from stream_heartbeat.render.heart_shaders import Look
from stream_heartbeat.ui.heart_paint import heart_lift

EFFECT_NONE = ""
EFFECT_GRIP = "grip"
EFFECT_STETHO = "stethoscope"
EFFECT_STETHO_FLIP = "stethoscope_flip"
EFFECT_DOPPLER = "doppler"
EFFECT_TAGGING = "tagging"
EFFECT_MONITOR = "monitor"
EFFECT_BURST = "burst"
# 聴診器の演出（1: 裏側のベルを見せる / 2: 膜の面を見せる）
STETHO_EFFECTS = frozenset({EFFECT_STETHO, EFFECT_STETHO_FLIP})
EFFECT_LABELS = {
    EFFECT_NONE: "なし",
    EFFECT_GRIP: "心臓わしづかみ",
    EFFECT_STETHO: "聴診器1",
    EFFECT_STETHO_FLIP: "聴診器2",
    EFFECT_DOPPLER: "カラードプラ",
    EFFECT_TAGGING: "タギング",
    EFFECT_MONITOR: "モニター画面",
    EFFECT_BURST: "はじけるハート",
}
_STETHO_HINT = (
    "配信用の窓の上でマウスを動かすと聴診器がついてきます。"
    "クリックした所に置いておけます（マウスが窓の外へ出るとそこへ戻ります）。"
)
EFFECT_HINTS = {
    EFFECT_GRIP: "配信用の窓をクリックすると、ぎゅっと強く握ります（押している間は握ったまま）。",
    EFFECT_STETHO: _STETHO_HINT,
    EFFECT_STETHO_FLIP: _STETHO_HINT,
    EFFECT_DOPPLER: "血の流れを色で重ねます（赤: 探触子へ向かう流れ / 青: 遠ざかる流れ）。",
    EFFECT_TAGGING: "拍のたびに格子の縞を焼き付けます。縞は心筋と一緒に曲がりながら薄れます。",
    EFFECT_MONITOR: "心電図をベッドサイドのモニターの画面に映します。拍で右上のハートが光ります。",
    EFFECT_BURST: "配信用の窓をクリックすると、その場所からハートがはじけます。",
}
# 手はレントゲン 1〜3 だけ。聴診器は心臓の形が出るスタイル（断面・波形・窓いっぱいの絵は除く）。
# None はどのスタイルでも選べる演出
_HEART_STYLES = frozenset({"realistic", "mech", "xray", "xray_heart", "cute", "chic", "poly"})
EFFECT_STYLES: dict[str, frozenset[str] | None] = {
    EFFECT_GRIP: frozenset({"xray", "xray_heart"}),
    EFFECT_STETHO: _HEART_STYLES,
    EFFECT_STETHO_FLIP: _HEART_STYLES,
    EFFECT_DOPPLER: frozenset({"echo"}),
    EFFECT_TAGGING: frozenset({"mri"}),
    EFFECT_MONITOR: frozenset({"ecg"}),
    EFFECT_BURST: None,
}

# 立体の心臓（正面から見たとき）の胴の真ん中と半分の幅・高さ。拡大 1 のときの世界の長さ。
# heart_mesh の胴の頂点の範囲から測った値（tests/test_effects.py で確かめる）
BODY_CENTER = (-0.03, -0.01)
BODY_HALF = (0.86, 0.94)

# 握る強さの追い方（秒）。握るのは速く、緩めるのはゆっくり
GRIP_ATTACK_S = 0.06
GRIP_RELEASE_S = 0.22
# 一瞬のクリックでも握ったと分かるよう、この秒数は握り続ける
GRIP_MIN_HOLD_S = 0.28
# 握り切ったときの心臓の潰れ（横の縮み・縦の伸び）
GRIP_SQUASH_X = 0.13
GRIP_SQUASH_Y = 0.06
# 聴診器がマウスへ追いつく速さ・置いた所へ戻る速さ（秒）
STETHO_FOLLOW_S = 0.045
STETHO_RETURN_S = 0.25
# はじけたハートが消えるまでの秒（effect_burst の POP_LIFE_S と同じ）
POP_KEEP_S = 1.3


def _offers(style: str, effect: str) -> bool:
    styles = EFFECT_STYLES.get(effect, frozenset())
    return styles is None or style in styles


def effect_choices(style: str) -> list[tuple[str, str]]:
    """このスタイルで選べる演出（先頭は「なし」）。"""
    keys = [key for key in EFFECT_STYLES if _offers(style, key)]
    return [(EFFECT_NONE, EFFECT_LABELS[EFFECT_NONE])] + [(k, EFFECT_LABELS[k]) for k in keys]


def active_effect(style: str, effect: str) -> str:
    """今描く演出。スタイルが対応しなければ無し（選んだ値は残し、対応するスタイルに戻せば出る）。"""
    return effect if effect in EFFECT_STYLES and _offers(style, effect) else EFFECT_NONE


def beat_jolt(squeeze: float, fill: float) -> float:
    """鼓動の揺れの強さ（0〜1 程度）。ドッ（収縮）を強く、クン（拡張）を弱く。"""
    return max(0.0, min(1.2, squeeze + 0.35 * fill))


def grip_squash(grip: float) -> tuple[float, float]:
    g = max(0.0, min(1.0, grip))
    return 1.0 - GRIP_SQUASH_X * g, 1.0 + GRIP_SQUASH_Y * g


@dataclass(frozen=True)
class HeartFrame:
    """画面の上の心臓の置き場所。center は胴の真ん中、half_w / half_h は胴の半分の幅と高さ。"""

    center: QPointF
    half_w: float
    half_h: float

    @property
    def radius(self) -> float:
        return (self.half_w + self.half_h) * 0.5


def gl_heart_frame(rect: QRectF, scale: float, look: Look, lift: float = 0.0) -> HeartFrame:
    """立体の心臓を正面から描いたときの画面上の置き場所（heart_gl のカメラと同じ式）。

    lift は画面の上へ寄せる量（窓の高さに対する割合。heart_gl の lift と同じ）。
    """
    px_per_unit = rect.height() / (2.0 * CAMERA_DISTANCE * math.tan(math.radians(FOV_DEG / 2.0)))
    size = max(0.05, scale) * look.size_factor
    wx = look.shift_x + BODY_CENTER[0] * size
    wy = look.shift_y + BODY_CENTER[1] * size
    center = QPointF(
        rect.center().x() + wx * px_per_unit,
        rect.center().y() - (wy - CAMERA_TARGET_Y) * px_per_unit - lift * rect.height(),
    )
    return HeartFrame(
        center=center,
        half_w=BODY_HALF[0] * size * px_per_unit,
        half_h=BODY_HALF[1] * size * px_per_unit,
    )


def flat_heart_frame(rect: QRectF, style: str, scale: float) -> HeartFrame:
    """2D で描く心臓（かわいい・立体が使えないときの代替）の置き場所。"""
    rect = rect.translated(0.0, -heart_lift(style) * rect.height())
    side = min(rect.width(), rect.height())
    if style == "cute":
        size = side * 0.36 * scale
        center = QPointF(rect.center().x(), rect.center().y() - size * 0.17)
        return HeartFrame(center=center, half_w=size * 0.72, half_h=size * 0.6)
    if style == "chic":
        size = side * 0.36 * scale
        center = QPointF(rect.center().x(), rect.center().y() - size * 0.10)
        return HeartFrame(center=center, half_w=size * 0.84, half_h=size * 0.76)
    size = side * 0.36 * scale
    return HeartFrame(center=QPointF(rect.center()), half_w=size, half_h=size)


class EffectMotion:
    """握る強さと聴診器の位置を、時間で滑らかに追う。時刻は壁時計の秒。"""

    def __init__(self) -> None:
        self.grip = 0.0
        self._pressed = False
        self._hold_until = 0.0
        self._last: float | None = None
        # 聴診器の今の位置と、マウスのいる所（窓の中の割合）。マウスが外なら None
        self.stetho: tuple[float, float] | None = None
        self._hover: tuple[float, float] | None = None
        # はじけるハート: (クリックの時刻, x の割合, y の割合)
        self._pops: list[tuple[float, float, float]] = []

    @property
    def squeezing(self) -> bool:
        return self._pressed

    def press(self, now: float) -> None:
        self._pressed = True
        self._hold_until = now + GRIP_MIN_HOLD_S

    def release(self) -> None:
        self._pressed = False

    def hover(self, pos: tuple[float, float] | None) -> None:
        self._hover = pos

    def pop(self, now: float, pos: tuple[float, float]) -> None:
        """クリックした所からハートをはじけさせる。"""
        self._pops.append((now, pos[0], pos[1]))
        # 連打しても重くならないよう、古いものから捨てる
        self._pops = self._pops[-12:]

    def pops_at(self, now: float) -> list[tuple[float, float, float, float]]:
        """いま描くはじけたハート: (はじけてからの秒, x, y, クリックの時刻)。"""
        return [(now - t, x, y, t) for t, x, y in self._pops if 0.0 <= now - t < POP_KEEP_S]

    def step(self, now: float, rest: tuple[float, float]) -> None:
        dt = 0.0 if self._last is None else max(0.0, min(0.1, now - self._last))
        self._last = now
        target = 1.0 if self._pressed or now < self._hold_until else 0.0
        tau = GRIP_ATTACK_S if target > self.grip else GRIP_RELEASE_S
        self.grip += (target - self.grip) * _approach(dt, tau)
        if self.grip < 1e-3 and target == 0.0:
            self.grip = 0.0
        self._pops = [p for p in self._pops if now - p[0] < POP_KEEP_S]
        goal = self._hover if self._hover is not None else rest
        if self.stetho is None:
            self.stetho = goal
            return
        k = _approach(dt, STETHO_FOLLOW_S if self._hover is not None else STETHO_RETURN_S)
        self.stetho = (
            self.stetho[0] + (goal[0] - self.stetho[0]) * k,
            self.stetho[1] + (goal[1] - self.stetho[1]) * k,
        )


def _approach(dt: float, tau: float) -> float:
    return 1.0 - math.exp(-dt / tau) if tau > 0.0 else 1.0
