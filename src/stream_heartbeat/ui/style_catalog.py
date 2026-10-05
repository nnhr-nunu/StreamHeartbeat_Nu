"""操作画面で選べるスタイルの一覧。(スタイル, 見た目, 表示名) の並び。

見た目はプロファイルの realistic_look に入る（リアルの 1〜4・レントゲンの女性の像・
レントゲン4 の Blender の心臓・かわいい2・心電図2 の縁取りなど）。見た目の無いスタイルは空。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stream_heartbeat.render.heart_looks import MODEL_LOOK, XRAY_MODEL_LOOK
from stream_heartbeat.render.model_shaders import (
    MATERIAL_GLASS,
    MATERIAL_GRADIENT,
    MATERIAL_REAL,
    MATERIAL_XRAY,
)
from stream_heartbeat.ui.heart_paint import CUTE_REIWA, ECG_OUTLINE

if TYPE_CHECKING:
    from stream_heartbeat.profile import HeartProfile

STYLES = [
    ("realistic", MODEL_LOOK.key, "リアル1"),
    ("realistic", "surgical", "リアル2"),
    ("realistic", "vivid", "リアル3"),
    ("realistic", "anatomy", "リアル4"),
    ("echo", "", "心エコー"),
    ("mri", "", "MRI"),
    ("xray", "", "レントゲン1"),
    ("xray", "female", "レントゲン2"),
    ("xray_heart", "", "レントゲン3"),
    ("xray_heart", XRAY_MODEL_LOOK.key, "レントゲン4"),
    ("cute", "", "かわいい1"),
    ("cute", CUTE_REIWA, "かわいい2"),
    ("chic", "", "オシャレ1"),
    ("poly", "", "オシャレ2"),
    ("mech", "", "機械"),
    ("particles", "", "パーティクル"),
    ("ecg", "", "心電図1"),
    ("ecg", ECG_OUTLINE, "心電図2"),
]

# リアル1（Blender の心臓）の材質。(キー, 表示名)。プロファイルの heart_material に入る
MODEL_MATERIALS = [
    (MATERIAL_REAL, "赤"),
    (MATERIAL_GRADIENT, "グラデ"),
    (MATERIAL_GLASS, "ガラス"),
]


# レントゲン4（Blender の心臓と肋骨）の心臓の材質。プロファイルの xray_material に入る。
# ガラスなら肋骨もガラス、ほかは X 線の肋骨
XRAY_MATERIALS = [
    (MATERIAL_XRAY, "X線"),
    (MATERIAL_REAL, "赤"),
    (MATERIAL_GRADIENT, "グラデ"),
    (MATERIAL_GLASS, "ガラス"),
]


def has_material(style: str, look: str) -> bool:
    """材質を選べるスタイル（リアル1）か。"""
    return style == "realistic" and look == MODEL_LOOK.key


def has_xray_material(style: str, look: str) -> bool:
    """心臓の材質を選べるレントゲン（レントゲン4）か。"""
    return style == "xray_heart" and look == XRAY_MODEL_LOOK.key


def chosen_material(profile: HeartProfile) -> str:
    """今のスタイルで選んでいる心臓の材質（材質を選べないスタイルは空）。"""
    if has_material(profile.style, profile.realistic_look):
        return profile.heart_material
    if has_xray_material(profile.style, profile.realistic_look):
        return profile.xray_material
    return ""
