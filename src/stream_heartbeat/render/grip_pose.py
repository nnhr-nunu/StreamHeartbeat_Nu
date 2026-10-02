"""心臓わしづかみの手の形。GL で描く手（hand_gl）と、指で凹む心臓（heart_shaders）の両方が使う。

手の絵（assets/hand_touch.png。握ると hand_grip.png へ変形する: hand_morph）を 1 枚の紙と見て、
心臓の胴のふくらみに巻き付ける。紙の上の点は、
胴の正面のてっぺん（画面の心臓の真ん中）からの距離だけ表面に沿って進む（地球儀に紙を貼るのと同じ）。
指は付け根から表面を這い、輪郭を越えると奥へ回り込む。手首から先（袖）は巻き付けず、見ている人の側
（手前・下）へ抜ける。

座標
- 素材の画素: 右・下が正
- 紙: 胴の真ん中からの、表面に沿った長さ（胴の単位。右・上が正）
- 胴: 胴の真ん中からの位置（胴の単位。右・上・手前が正）。世界 = 真ん中 + 胴 × body
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.hand_morph import claw_point

# 胴（立体の心臓の、血管を除いた部分）を正面から見たときの真ん中と、輪郭までの長さ。
# 輪郭は -180° から 10° おき（右が 0°、上が 90°）。heart_mesh の頂点から測った値
# （tests/test_grip_pose.py で確かめる）。右下へ突き出すのが心尖
BODY_CENTER = (-0.03, -0.01, 0.0)
BODY_RIM = (
    0.877, 0.846, 0.827, 0.819, 0.812, 0.805, 0.797, 0.787, 0.781, 0.807, 0.896, 1.022,
    1.117, 1.140, 1.102, 1.035, 0.963, 0.904, 0.862, 0.832, 0.807, 0.788, 0.795, 0.847,
    0.915, 0.953, 0.961, 0.949, 0.915, 0.864, 0.820, 0.822, 0.861, 0.895, 0.906, 0.901,
)  # fmt: skip
# 胴の奥行きの半分（正面から背中まで）
BODY_DEPTH = 0.61

# 素材の目印（開いた手の画素。握った手の絵も同じ大きさ）
HAND_IMAGE_SIZE = (843.0, 1264.0)
HAND_PALM = (420.0, 560.0)  # 手の甲の真ん中（心臓に当てる所）
HAND_WIDTH_PX = 409.0  # 親指の先から小指の縁まで
# 指の付け根（曲げる軸）・指先・太さの半分。親指・人差し指・中指・薬指・小指
FINGERS = (
    ((290.0, 545.0), (195.0, 330.0), 32.0),
    ((333.0, 405.0), (314.0, 75.0), 28.0),
    ((408.0, 410.0), (395.0, 58.0), 28.0),
    ((473.0, 430.0), (481.0, 114.0), 26.0),
    ((532.0, 452.0), (562.0, 204.0), 23.0),
)
# 巻き付ける所と手首: 指の付け根より上は表面に沿い、手の甲から手首は平らなまま手前へ
# （手の甲まで心臓の下の丸みへ巻き付けると、手の甲が奥へ折れて重なり、ぎざぎざの筋が出る）
WRAP_FULL_V = 420.0
WRAP_NONE_V = 600.0
ARM_SLOPE = 0.175  # 袖の傾き（下へ 1 進むと右へ進む量）
TAIL_V = 1258.0  # 素材の下端。ここより下は袖をこの行で伸ばす
# 握った手の絵へ切り替える所（変形の進み具合）。鼓動の握り直し程度では開いた手の絵のまま曲がる
BLEND_FROM = 0.5
BLEND_TO = 0.75
# 握った手の絵は指の曲がりまで描いてあるので、絵が替わるほど心臓の丸みへの巻き付けを少し弱める。
# 指先は縁の手前に収まるので、弱めすぎると指が心臓から浮いて輪郭の外へはみ出す
CLAW_FLATTEN = 0.2

# 心臓の大きさ（胴の単位）に対する手の幅と、手の甲を当てる所（紙の座標）。
# 開いた手の指先が心臓の縁の手前（正面寄り）に収まる大きさと高さ。縁を越えて奥へ回ると、
# 指先が心臓に隠れて切れたように見える
HAND_WIDTH = 1.40
ANCHOR = (0.04, -0.68)
TURN = math.radians(3.0)
# 指の開き（ラジアン、画面で右回りが正）。絵の指はもう開いているので少しだけ。
# 親指と人差し指は心臓の左の縁からはみ出さないよう、少し内へ起こす
FAN_REST = (0.04, 0.0, -0.01, 0.04, 0.09)
# 人差し指の第2関節・第1関節（指の付け根→先 0〜1 の所）から先を曲げる角度（画面で右回りが正）。
# 人差し指は心臓の左上の丸みに載るので、巻き付けると指先が輪郭に沿って右へ流れ、第2関節から先が
# 右へ折れて見える。絵の上で少し左へ曲げておき、画面でまっすぐ〜わずかに左へ向ける
INDEX_BEND = ((0.55, math.radians(-8.0)), (0.78, math.radians(-12.0)))
BEND_SOFT = 0.06  # 関節の前後で曲げ始める幅（指の長さの割合）
# 指の途中（付け根→先 0〜1 の所）から先は硬い節なので、心臓の丸みに貼り付かずに接線の方へ少し浮く。
# STIFF_CURL は表面に沿う割合（1 で貼り付いたまま・0 で接線のまっすぐ）。縁の近くまで届く
# 人差し指・中指の指先が真横を向いて、爪が潰れて短く見えないように。握った手の絵では効かせない
STIFF_FROM = 0.55
STIFF_CURL = 0.4
STIFF_STEP = 0.01  # 接線を測る刻み（紙の長さ）
# 指の厚み（表面からの浮き、胴の大きさに対する割合）と、強く握ったときの沈み
LIFT = 0.075
SINK = 0.045
# 袖が手前へ寄ってくる量（下へ胴 1 進むごと）と、その上限
ARM_RISE = 0.28
ARM_RISE_MAX = 0.55

# 握り切ったときの心臓の潰れ（横の縮み・縦の伸び）
GRIP_SQUASH_X = 0.13
GRIP_SQUASH_Y = 0.06
# 握ると手が心臓へ食い込みながら少し上へ滑る（鼓動の握り直しでは指が奥へ回り込む）
GRIP_PUSH = 0.03
GRIP_CLOSE = 0.30
# クリックで握り込んだときの震え（紙の座標の長さと、横・縦の速さ ラジアン/秒）。
# 速すぎるとコマごとにばらばらに跳ねて見えるので、ゆっくり小さく
SHAKE = 0.004
SHAKE_SPEED = (23.0, 29.0)
# 鼓動で心臓が縮む・膨らむ量（胴の大きさに対する割合）と、縮むときに左へ寄る量（胴の単位）。
# heart_shaders の頂点の動きで輪郭がどれだけ動くかを測った値
BEAT_SQUEEZE = 0.03
BEAT_FILL = 0.01
BEAT_SHIFT = (-0.06, 0.012, 0.028)
ROCK = math.radians(2.0)
# 鼓動に合わせて握り直す: ドッ（収縮）で締まり、充満で押し返されて緩む。クリックの握りに足す
PULSE_SQUEEZE = 0.32
PULSE_FILL = -0.10
# 拍の頭に手が突き上げられて揺れ戻る（秒・紙の座標の長さ・ラジアン）
KICK_DECAY_S = 0.09
KICK_PERIOD_S = 0.19
KICK_PUSH = 0.03
KICK_FAN = 0.05
# 指の下の凹み・指の間の盛り上がり（胴の単位）と、指の影の濃さ
DENT_REST = 0.035
DENT_GRIP = 0.045
BULGE_REST = 0.018
BULGE_GRIP = 0.03
SHADE_REST = 0.30
SHADE_GRIP = 0.22
# 指の影がずれる向き（紙の座標。光は左上の手前から）
SHADE_SHIFT = (0.035, -0.045)


def grip_squash(grip: float) -> tuple[float, float]:
    """握る強さ 0〜1 に対する心臓の潰れ（横・縦の倍率）。"""
    g = max(0.0, min(1.0, grip))
    return 1.0 - GRIP_SQUASH_X * g, 1.0 + GRIP_SQUASH_Y * g


def held_grip(grip: float, cycle: CardiacCycle) -> float:
    """手の握りの強さ: クリックの握りに、鼓動に合わせた締め付けを足す（心臓の潰れにも使う）。"""
    pulse = PULSE_SQUEEZE * cycle.squeeze + PULSE_FILL * cycle.fill
    return max(0.0, min(1.0, grip + pulse))


def rim_at(phi: float) -> float:
    """胴の真ん中から角度 phi（ラジアン）の向きの、輪郭までの長さ。"""
    steps = len(BODY_RIM)
    x = (phi + math.pi) / (2.0 * math.pi) * steps
    i = math.floor(x)
    t = x - i
    return BODY_RIM[i % steps] * (1.0 - t) + BODY_RIM[(i + 1) % steps] * t


def arc_radius(r: float) -> float:
    """正面のてっぺんから輪郭まで表面に沿った長さ（楕円の 4 分の 1）を、90° で割った値。"""
    d = BODY_DEPTH
    return 0.5 * (3.0 * (r + d) - math.sqrt((3.0 * r + d) * (r + 3.0 * d)))


def arc_length(theta: float, r: float) -> float:
    """正面のてっぺんから角度 theta まで表面に沿った長さ（x = r sinθ, z = 奥行き cosθ の楕円）。

    正面では r、輪郭では奥行きの速さで伸びる。輪郭までの長さは arc_radius × 90° に合う。
    """
    a = arc_radius(r)
    return a * theta + 0.5 * (r - a) * math.sin(2.0 * theta)


def arc_angle(length: float, r: float) -> float:
    """arc_length の逆（ニュートン法 3 回）。"""
    a = arc_radius(r)
    theta = length / a
    for _ in range(3):
        f = a * theta + 0.5 * (r - a) * math.sin(2.0 * theta) - length
        theta -= f / (a + (r - a) * math.cos(2.0 * theta))
    return theta


def wrap(fx: float, fy: float, lift: float = 0.0) -> tuple[float, float, float, float]:
    """紙の点を胴の表面へ: (x, y, z, 向き)。向きは正面 1・輪郭 0・裏 -1。"""
    rho = math.hypot(fx, fy)
    phi = math.atan2(fy, fx) if rho > 1e-9 else 0.0
    r = rim_at(phi)
    theta = arc_angle(rho, r)
    s = math.sin(theta) * r * (1.0 + lift)
    return (
        s * math.cos(phi),
        s * math.sin(phi),
        BODY_DEPTH * math.cos(theta) * (1.0 + lift),
        math.cos(theta),
    )


def unwrap(x: float, y: float, z: float) -> tuple[float, float]:
    """胴の表面の点を紙へ戻す（wrap の逆）。"""
    rxy = math.hypot(x, y)
    phi = math.atan2(y, x) if rxy > 1e-9 else 0.0
    r = rim_at(phi)
    theta = math.atan2(rxy / r, z / BODY_DEPTH)
    rho = arc_length(theta, r)
    return rho * math.cos(phi), rho * math.sin(phi)


def kick(age: float) -> float:
    """拍の頭からの揺れ（突き上げて、揺れ戻って収まる。-1〜1）。"""
    if age <= 0.0:
        return 0.0
    return math.exp(-age / KICK_DECAY_S) * math.sin(2.0 * math.pi * age / KICK_PERIOD_S)


def _rotate(x: float, y: float, angle: float) -> tuple[float, float]:
    c = math.cos(angle)
    s = math.sin(angle)
    return c * x - s * y, s * x + c * y


def bend_index(u: float, v: float, weight: float = 1.0) -> tuple[float, float]:
    """開いた手の素材の画素を、人差し指の関節で曲げた所へ（weight は人差し指へのつき方）。"""
    (kx, ky), (tx, ty), _half = FINGERS[1]
    ax, ay = tx - kx, ty - ky
    t = ((u - kx) * ax + (v - ky) * ay) / (ax * ax + ay * ay)
    # 先の関節から曲げる（手前の関節で曲げると、先の関節も一緒に回る）
    for along, angle in reversed(INDEX_BEND):
        a = angle * weight * _smoothstep(along - BEND_SOFT, along + BEND_SOFT, t)
        px, py = kx + ax * along, ky + ay * along
        dx, dy = _rotate(u - px, v - py, a)
        u, v = px + dx, py + dy
    return u, v


@dataclass(frozen=True)
class HandPose:
    """1 コマの手の形。長さは断りが無ければ胴の単位、world は世界の長さ。"""

    center: tuple[float, float, float]  # 胴の真ん中（世界）
    body: tuple[float, float, float]  # 胴の 1 単位の世界の長さ（横・縦・奥。潰れと鼓動込み）
    size: float  # 手首から先（巻き付けない所）の 1 単位の世界の長さ
    anchor: tuple[float, float]  # 手の甲の真ん中（紙）
    turn: float  # 手の傾き（左回り）
    px: float  # 素材の 1 画素の紙の上の長さ
    fan: tuple[float, float, float, float, float]  # 指の開き（画面で右回りが正）
    lift: float
    sink: float
    palm_z: float  # 手の甲の真ん中の奥行き（手首から先の単位）
    grip: float
    morph: float  # 握った手の形への変形（0 開いた手〜1 握った手）
    blend: float  # 握った手の絵の混ぜ具合
    flatten: float  # 巻き付けを弱める割合
    dent: float  # 指の下の凹み（世界）
    bulge: float  # 指の間の盛り上がり（世界）
    shade: float  # 指の影の濃さ

    def sheet_point(self, u: float, v: float) -> tuple[float, float]:
        """素材の画素（指は開く前）を紙の点へ。"""
        lx, ly = _rotate((u - HAND_PALM[0]) * self.px, (HAND_PALM[1] - v) * self.px, self.turn)
        return self.anchor[0] + lx, self.anchor[1] + ly

    def knuckle(self, index: int) -> tuple[float, float]:
        """指の付け根の素材の画素（握った形への変形込み）。"""
        return _mix(FINGERS[index][0], claw_fingers()[index][0], self.morph)

    def finger_tip(self, index: int) -> tuple[float, float]:
        """指を開いた後の指先の素材の画素（握った形への変形込み）。"""
        kx, ky = self.knuckle(index)
        tip = bend_index(*FINGERS[index][1]) if index == 1 else FINGERS[index][1]
        tx, ty = _mix(tip, claw_fingers()[index][1], self.morph)
        # 素材の画素は下が正なので、画面で右回りの角度をそのまま回せる
        dx, dy = _rotate(tx - kx, ty - ky, self.fan[index])
        return kx + dx, ky + dy

    def finger_axes(self) -> list[tuple[float, float, float, float]]:
        """指の軸: 紙の上の付け根と、先へ向かう向き（長さ 1）。"""
        out = []
        for bx, by, ex, ey, _half in self.segments():
            length = max(math.hypot(ex - bx, ey - by), 1e-9)
            out.append((bx, by, (ex - bx) / length, (ey - by) / length))
        return out

    def segments(self) -> list[tuple[float, float, float, float, float]]:
        """心臓を凹ませる指の線: 紙の上の付け根・先と、太さの半分。"""
        out = []
        for i, (_knuckle, _tip, half) in enumerate(FINGERS):
            bx, by = self.sheet_point(*self.knuckle(i))
            ex, ey = self.sheet_point(*self.finger_tip(i))
            out.append((bx, by, ex, ey, half * self.px))
        return out

    def finger_facing(self, index: int, along: float = 1.0) -> float:
        """指の付け根から along（0〜1）の所が、表面でどちらを向くか（正面 1・輪郭 0・裏 -1）。

        指先が浮く前の、表面の上の置き場所で測る（浮いた後の向きは finger_point）。
        """
        bx, by, ex, ey, _half = self.segments()[index]
        return wrap(bx + (ex - bx) * along, by + (ey - by) * along)[3]

    def stiff_curl(self) -> float:
        """指先の方が表面に沿う割合（握った手の絵へ替わるほど貼り付いたままに戻す）。"""
        return STIFF_CURL + (1.0 - STIFF_CURL) * self.blend

    def finger_point(
        self, index: int, fx: float, fy: float, lift: float = 0.0
    ) -> tuple[float, float, float, float]:
        """指 index の上の紙の点を胴へ: (x, y, z, 向き)。

        hand_gl の頂点シェーダーと同じ式（筒に起こす所は除く）。指の途中から先は接線の方へ浮く。
        """
        on = wrap(fx, fy, lift)
        bx, by, ex, ey, _half = self.segments()[index]
        length = math.hypot(ex - bx, ey - by)
        dx, dy = (ex - bx) / length, (ey - by) / length
        s = (fx - bx) * dx + (fy - by) * dy
        start = STIFF_FROM * length
        if index == 0 or s <= start:
            return on
        center = wrap(bx + dx * s, by + dy * s, lift)
        a = wrap(bx + dx * start, by + dy * start, lift)
        b = wrap(bx + dx * (start + STIFF_STEP), by + dy * (start + STIFF_STEP), lift)
        lifted = 1.0 - self.stiff_curl()
        run = (s - start) / STIFF_STEP
        x, y, z = (on[j] + (a[j] + (b[j] - a[j]) * run - center[j]) * lifted for j in range(3))
        return x, y, z, on[3] + (a[3] - on[3]) * lifted

    def dent_uniforms(self) -> dict[str, object]:
        """心臓の頂点シェーダーへ渡す値（heart_shaders の GRIP_DENT_GLSL）。"""
        segs = self.segments()
        values: dict[str, object] = {
            "uHandOn": 1.0,
            "uHandC": self.center,
            "uHandS": self.body,
            "uHandDent": (self.dent, self.bulge, self.shade),
        }
        for i, (bx, by, ex, ey, half) in enumerate(segs):
            values[f"uHandSeg[{i}]"] = (bx, by, ex, ey)
            values[f"uHandSegR[{i}]"] = half
        return values


def grip_pose(
    *,
    shift: tuple[float, float],
    size: float,
    cycle: CardiacCycle,
    grip: float,
    time_s: float,
) -> HandPose:
    """shift は心臓の置き場所のずれ（look.shift_x / shift_y）、size は心臓の大きさ（世界）。

    grip はクリックの握り（0〜1）。鼓動に合わせた締め付けはここで足す（held_grip）。
    """
    clicked = max(0.0, min(1.0, grip))
    g = held_grip(clicked, cycle)
    sx, sy = grip_squash(g)
    beat = 1.0 - BEAT_SQUEEZE * cycle.squeeze + BEAT_FILL * cycle.fill
    jolt = kick(cycle.age)
    # 心臓は縮むときに左へ寄り、少し左回りに揺れる（heart_shaders の rock と同じ向き）
    rock = ROCK * cycle.squeeze
    center = (
        shift[0] + size * (sx * BODY_CENTER[0] + BEAT_SHIFT[0] * cycle.squeeze),
        shift[1] + size * (sy * BODY_CENTER[1] + BEAT_SHIFT[1] * cycle.squeeze),
        size * (BODY_CENTER[2] + BEAT_SHIFT[2] * cycle.squeeze),
    )
    body = (size * sx * beat, size * sy * beat, size * beat)
    # クリックで握り込むと小さく震える
    shake = SHAKE * clicked
    ax = ANCHOR[0] + shake * math.sin(time_s * SHAKE_SPEED[0])
    blend = _smoothstep(BLEND_FROM, BLEND_TO, g)
    ay = ANCHOR[1] + GRIP_PUSH * g + KICK_PUSH * jolt + shake * math.cos(time_s * SHAKE_SPEED[1])
    anchor = _rotate(ax, ay, rock)
    # 握ると指を寄せ、拍の頭で揺さぶられ、充満で心臓が膨らむと押し開かれる
    spread = 1.0 - GRIP_CLOSE * g + 0.15 * cycle.fill
    fan = tuple(a * spread + math.copysign(KICK_FAN * jolt, a) for a in FAN_REST)
    lift = LIFT
    palm = wrap(anchor[0], anchor[1], lift)
    return HandPose(
        center=center,
        body=body,
        size=size,
        anchor=anchor,
        turn=TURN + rock,
        px=HAND_WIDTH / HAND_WIDTH_PX,
        fan=fan,  # type: ignore[arg-type]
        lift=lift,
        sink=SINK * (0.35 + 0.65 * g),
        palm_z=palm[2] * body[2] / size,
        grip=g,
        morph=g,
        blend=blend,
        flatten=CLAW_FLATTEN * blend,
        dent=size * (DENT_REST + DENT_GRIP * g),
        bulge=size * (BULGE_REST + BULGE_GRIP * g) * (0.7 + 0.8 * cycle.fill),
        shade=SHADE_REST + SHADE_GRIP * g,
    )


# 指ごとの付け根と指先（素材の画素）
FingerLines = tuple[tuple[tuple[float, float], tuple[float, float]], ...]

_claw_fingers: FingerLines | None = None


def claw_fingers() -> FingerLines:
    """握った手の絵での指の付け根と指先（FINGERS を hand_morph で動かした所）。"""
    global _claw_fingers
    if _claw_fingers is None:
        _claw_fingers = tuple((claw_point(*k), claw_point(*t)) for k, t, _half in FINGERS)
    return _claw_fingers


def _mix(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def skin(
    u: float, v: float, fingers: FingerLines | None = None
) -> tuple[tuple[float, float, float, float, float], float, float, int]:
    """素材の画素の点が、どの指と一緒に動くか。

    (5 本の指へのつき方, 指の付け根→先 0〜1, 関節の近さ, いちばん強くつく指)。
    いちばん強くつく指は、どれにもつかなければ -1。fingers は指の付け根と指先（省くと開いた手の絵。
    握った手の絵の上で測るときは claw_fingers()）

    付け根より手前（手の甲）はどの指にもつかない。指の間の隙間は透明なので、そこで隣の指へ移る。
    """
    lines = fingers if fingers is not None else tuple((k, t) for k, t, _half in FINGERS)
    dists: list[float] = []
    alongs: list[float] = []
    for (kx, ky), (tx, ty) in lines:
        ax, ay = tx - kx, ty - ky
        length = math.hypot(ax, ay)
        t = ((u - kx) * ax + (v - ky) * ay) / (length * length)
        h = max(0.0, min(1.0, t))
        dists.append(math.hypot(u - kx - ax * h, v - ky - ay * h))
        alongs.append(t)
    nearest = min(dists)
    sigma = 21.0
    raw = [math.exp(-(d * d - nearest * nearest) / (sigma * sigma)) for d in dists]
    total = sum(raw)
    weights = []
    along = 0.0
    for w, t in zip(raw, alongs):
        # 付け根の少し手前から動き始める
        reach = _smoothstep(-0.12, 0.08, t)
        share = w / total * reach
        weights.append(share)
        along += w / total * max(0.0, min(1.0, t)) * reach
    knuckle = 0.0
    for (kx, ky), _tip in lines[1:]:
        d = math.hypot(u - kx, v - ky)
        knuckle = max(knuckle, math.exp(-(d * d) / (36.0 * 36.0)))
    main = max(range(len(weights)), key=lambda i: weights[i])
    return tuple(weights), along, knuckle, (main if weights[main] > 0.02 else -1)  # type: ignore[return-value]


def wrap_weight(v: float) -> float:
    """素材の行 v が表面に沿う割合（手の甲より上 1・手首より下 0）。"""
    return 1.0 - _smoothstep(WRAP_FULL_V, WRAP_NONE_V, v)


def _smoothstep(a: float, b: float, x: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3.0 - 2.0 * t)


def _glsl_floats(values: tuple[float, ...]) -> str:
    return ", ".join(f"{v:.4f}" for v in values)


# 胴の形と、紙と表面の行き来（wrap / unwrap と同じ式）
GRIP_SHAPE_GLSL = f"""
const float GRIP_PI = 3.14159265;
const float GRIP_DEPTH = {BODY_DEPTH:.4f};
const float GRIP_RIM[{len(BODY_RIM)}] = float[{len(BODY_RIM)}]({_glsl_floats(BODY_RIM)});
float gripRim(float phi) {{
    float x = (phi + GRIP_PI) / (2.0 * GRIP_PI) * {float(len(BODY_RIM)):.1f};
    float i = floor(x);
    int a = int(mod(i, {float(len(BODY_RIM)):.1f}));
    int b = int(mod(i + 1.0, {float(len(BODY_RIM)):.1f}));
    return mix(GRIP_RIM[a], GRIP_RIM[b], x - i);
}}
float gripArc(float r) {{
    float d = GRIP_DEPTH;
    return 0.5 * (3.0 * (r + d) - sqrt((3.0 * r + d) * (r + 3.0 * d)));
}}
float gripArcLength(float th, float r) {{
    float a = gripArc(r);
    return a * th + 0.5 * (r - a) * sin(2.0 * th);
}}
float gripArcAngle(float len, float r) {{
    float a = gripArc(r);
    float th = len / a;
    for (int i = 0; i < 3; i++) {{
        float f = a * th + 0.5 * (r - a) * sin(2.0 * th) - len;
        th -= f / (a + (r - a) * cos(2.0 * th));
    }}
    return th;
}}
// 紙の点を表面へ。xyz は胴の点、w は向き（正面 1・輪郭 0・裏 -1）
vec4 gripWrap(vec2 f, float lift) {{
    float rho = length(f);
    float phi = rho > 1e-6 ? atan(f.y, f.x) : 0.0;
    float r = gripRim(phi);
    float th = gripArcAngle(rho, r);
    float s = sin(th) * r * (1.0 + lift);
    return vec4(s * cos(phi), s * sin(phi), GRIP_DEPTH * cos(th) * (1.0 + lift), cos(th));
}}
vec2 gripUnwrap(vec3 b) {{
    float rxy = length(b.xy);
    float phi = rxy > 1e-6 ? atan(b.y, b.x) : 0.0;
    float r = gripRim(phi);
    float th = atan(rxy / r, b.z / GRIP_DEPTH);
    return gripArcLength(th, r) * vec2(cos(phi), sin(phi));
}}
"""

# 心臓の頂点シェーダーに足す: 指の下を凹ませ、指の間を盛り上げ、指の影を付ける
GRIP_DENT_GLSL = (
    GRIP_SHAPE_GLSL
    + f"""
uniform float uHandOn;
uniform vec3 uHandC;
uniform vec3 uHandS;
uniform vec4 uHandSeg[5];
uniform float uHandSegR[5];
// x: 指の下の凹み（世界の長さ） y: 指の間の盛り上がり z: 指の影の濃さ
uniform vec3 uHandDent;
const vec2 GRIP_SHADE_SHIFT = vec2({SHADE_SHIFT[0]:.4f}, {SHADE_SHIFT[1]:.4f});
float gripSegDist(vec2 f, vec4 seg) {{
    vec2 e = seg.zw - seg.xy;
    float h = clamp(dot(f - seg.xy, e) / max(dot(e, e), 1e-6), 0.0, 1.0);
    return length(f - seg.xy - e * h);
}}
// x: 表面を外へ動かす量（世界） y: 影 z: 盛り上がり（濃く写る）
vec3 gripContact(vec3 world) {{
    vec2 f = gripUnwrap((world - uHandC) / uHandS);
    float under = 0.0;
    float near = 0.0;
    float shade = 0.0;
    for (int i = 0; i < 5; i++) {{
        float r = uHandSegR[i];
        float d = gripSegDist(f, uHandSeg[i]);
        float ds = gripSegDist(f - GRIP_SHADE_SHIFT, uHandSeg[i]);
        under = max(under, exp(-d * d / (r * r)));
        near = max(near, exp(-d * d / (5.0 * r * r)));
        shade = max(shade, exp(-ds * ds / (1.7 * r * r)));
    }}
    float swell = max(near - under, 0.0);
    return vec3(uHandDent.y * swell - uHandDent.x * under, uHandDent.z * shade, swell);
}}
"""
)
