"""Blender の心臓（リアル1）の胴の形。心臓わしづかみの手と聴診器を、この心臓の形と動きに合わせる。

手は作った心臓と同じ式（grip_pose）で胴へ巻き付けるが、巻き付ける輪郭と奥行きはこの心臓のものを
使う。この心臓は鼓動で形そのもの（シェイプキー）が動くので、コマごとに今のキーの重みから輪郭と
奥行きを出し、手も同じだけ縮む。値は scripts/heart_model/measure_body.py で測った
（胴は形の座標で y が 0.4 より下。真ん中は model_gl の MODEL_BODY_CENTER）。
"""

from __future__ import annotations

import math
from dataclasses import replace

from stream_heartbeat.clock import CardiacCycle
from stream_heartbeat.render.grip_pose import HEART_BODY, GripBody, rim_at
from stream_heartbeat.render.heart_shaders import Look
from stream_heartbeat.render.model_mesh import beat_weights, load_model_anim

# 休んでいる形（アニメの最後のコマ）のキーの重み。下の輪郭・奥行きはこの重みのときの値
REST_WEIGHTS = (0.367, 0.0, 0.0)
# 正面から見た胴の輪郭（-180° から 10° おき）と、楕円に合わせた奥行き
MODEL_RIM = (
    0.798, 0.718, 0.710, 0.760, 0.744, 0.677, 0.594, 0.566, 0.592, 0.633, 0.681, 0.768,
    0.890, 1.000, 1.009, 0.992, 0.933, 0.899, 0.872, 0.849, 0.793, 0.740, 0.796, 0.863,
    0.926, 0.926, 0.856, 0.840, 0.863, 0.923, 1.023, 1.115, 1.148, 1.019, 0.933, 0.868,
)  # fmt: skip
MODEL_DEPTH = 0.678
# キーの重みが 1 増えたときの輪郭・奥行きの変わり方。キー 2 が左室の大きな縮み、
# キー 3（上下）が全体の縮み、キー 1 は右の小さな縮み
MODEL_RIM_KEYS = (
    (
        -0.096, -0.050, -0.003, -0.020, -0.030, -0.033, -0.026, 0.001, 0.002,
        0.002, 0.001, 0.006, 0.031, 0.010, 0.012, 0.007, 0.011, 0.010,
        0.009, 0.010, 0.008, 0.008, 0.004, -0.002, -0.017, -0.005, 0.007,
        0.000, 0.008, 0.003, -0.012, -0.005, -0.004, -0.003, -0.042, -0.089,
    ),
    (
        0.014, 0.017, -0.004, 0.000, 0.000, 0.000, 0.000, -0.086, -0.114,
        -0.137, -0.161, -0.220, -0.261, -0.289, -0.221, -0.205, -0.191, -0.205,
        -0.205, -0.200, -0.148, -0.011, -0.008, 0.000, 0.000, 0.000, 0.000,
        0.003, -0.024, -0.028, 0.000, 0.002, 0.000, 0.000, 0.006, 0.008,
    ),
    (
        -0.008, -0.003, 0.003, -0.013, -0.026, -0.036, -0.049, -0.025, -0.031,
        -0.033, -0.041, -0.055, -0.052, -0.032, -0.019, -0.005, -0.002, 0.003,
        -0.001, 0.001, 0.000, -0.006, -0.009, -0.012, -0.023, -0.033, -0.024,
        -0.026, -0.025, -0.041, -0.041, -0.018, -0.015, -0.009, 0.005, 0.000,
    ),
)  # fmt: skip
MODEL_DEPTH_KEYS = (0.0133, -0.0999, 0.0115)
# 胴の半分の幅・高さ（聴診器の大きさ・はじけるハートの置き場所。effects の BODY_HALF と同じ使い方）
MODEL_HALF = (0.87, 0.80)
# 胴が縮んだ量（輪郭の平均）を、拍の縮み 0〜1 に直す割合（アニメのいちばん縮んだコマで 1）
SHRINK_PER_KEY = (0.0081, 0.0740, 0.0196)
SHRINK_FULL = 0.0666
# 手の大きさと当てる所。この心臓は作った心臓より胴の下半分が小さいので、手を少し小さくし、
# 指先が上の縁（太い血管の根元）を越えないよう少し下に当てる
MODEL_HAND_WIDTH = 1.22
MODEL_ANCHOR = (0.03, -0.64)


def model_rim(weights: tuple[float, ...]) -> tuple[float, ...]:
    """キーの重み weights のときの、正面から見た胴の輪郭。"""
    moves = [w - r for w, r in zip(weights, REST_WEIGHTS)]
    return tuple(
        base + sum(m * keys[k] for m, keys in zip(moves, MODEL_RIM_KEYS))
        for k, base in enumerate(MODEL_RIM)
    )


def model_depth(weights: tuple[float, ...]) -> float:
    moves = [w - r for w, r in zip(weights, REST_WEIGHTS)]
    return MODEL_DEPTH + sum(m * d for m, d in zip(moves, MODEL_DEPTH_KEYS))


def model_squeeze(weights: tuple[float, ...]) -> float:
    """胴がどれだけ縮んでいるか（休み 0・いちばん縮んだコマ 1）。"""
    shrink = sum((w - r) * s for w, r, s in zip(weights, REST_WEIGHTS, SHRINK_PER_KEY))
    return max(0.0, min(1.0, shrink / SHRINK_FULL))


def model_grip_body(weights: tuple[float, ...]) -> GripBody:
    """キーの重み weights のときの、手を巻き付ける胴。

    形が動くので鼓動の縮み・寄りは足さない。この心臓は拍の頭より後でゆっくり縮むので、拍の頭で
    手が跳ねる動き（kick）も入れない（膨らみ終えた所で指がぶるっと震えて見える）。
    """
    return GripBody(
        rim=model_rim(weights),
        depth=model_depth(weights),
        hand_width=MODEL_HAND_WIDTH,
        anchor=MODEL_ANCHOR,
        beat_squeeze=0.0,
        beat_fill=0.0,
        beat_shift=(0.0, 0.0, 0.0),
        rock=0.0,
        kick=0.0,
    )


def current_weights(cycle: CardiacCycle) -> tuple[float, ...] | None:
    """今のキーの重み（形のファイルが読めなければ None）。"""
    anim = load_model_anim()
    if anim is None:
        return None
    return beat_weights(anim, cycle.age, cycle.interval)


def model_grip(cycle: CardiacCycle) -> tuple[GripBody, CardiacCycle]:
    """Blender の心臓を掴むときの胴と拍。

    拍の縮み（squeeze）はこの心臓の今の縮み具合に置き換え、手の握り直しや心臓の潰れを形の動きに
    そろえる。この心臓は休んだ形より膨らまないので充満（fill）は 0。形のファイルが読めなければ
    作った心臓の胴（そのときは作った心臓が描かれる）。
    """
    weights = current_weights(cycle)
    if weights is None:
        return HEART_BODY, cycle
    return model_grip_body(weights), replace(cycle, squeeze=model_squeeze(weights), fill=0.0)


def grip_for_look(look: Look, cycle: CardiacCycle) -> tuple[GripBody, CardiacCycle]:
    """見た目 look の心臓を掴むときの胴と拍（Blender の心臓なら model_grip、ほかは作った心臓）。"""
    if look.program == "model":
        return model_grip(cycle)
    return HEART_BODY, cycle


def follow_scale(cycle: CardiacCycle, dx: float, dy: float) -> float:
    """胴の真ん中から (dx, dy)（右・上が正）の向きの表面が、休んだ形から縮んだ割合。

    聴診器を当てた所が、心臓の表面と一緒に寄るのに使う。
    """
    weights = current_weights(cycle)
    if weights is None or (dx == 0.0 and dy == 0.0):
        return 1.0
    phi = math.atan2(dy, dx)
    rest = rim_at(phi, MODEL_RIM)
    return rim_at(phi, model_rim(weights)) / max(1e-6, rest)
