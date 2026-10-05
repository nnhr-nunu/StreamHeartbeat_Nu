"""立体の心臓の見た目（Look）。どのシェーダーで、どんな色・大きさ・材質で描くか。

スタイルと見た目（プロファイルの realistic_look）・材質から style_look で選ぶ。
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Look:
    key: str
    label: str
    program: str
    fat_amount: float = 1.0
    gloss: float = 1.0
    saturation: float = 1.0
    coronary: float = 0.0
    additive: bool = False
    # 足し算の代わりに、濃い所ほど下を隠して重ねる（緑や透明の背景にそのまま載せる）
    cutout: bool = False
    tint_dense: tuple[float, float, float] = (1.0, 1.0, 1.0)
    tint_thin: tuple[float, float, float] = (1.0, 1.0, 1.0)
    grain: float = 0.0
    density: float = 1.0
    size_factor: float = 1.0
    # 四腔断面で切って見せる。切り口がカメラへ向くよう向きを足す
    section: bool = False
    # 心房の時間差・心耳の別の動き・冠動脈の盛り上がり・送り出しの波（リアル2）
    lively: float = 0.0
    yaw_offset_deg: float = 0.0
    pitch_offset_deg: float = 0.0
    # 画面の上での置き場所のずれ（体の絵に合わせる。右・上が正）
    shift_x: float = 0.0
    shift_y: float = 0.0
    # Blender の心臓（program "model"）の材質。model_shaders の MATERIALS のどれか
    material: str = ""
    # Blender の心臓の周りに肋骨を描く（レントゲン4）
    bones: bool = False


# Blender で作った心臓（リアル1）。大きさと置き場所は、手や聴診器の位置（effects の BODY_*）に
# 合うよう、作った心臓の胴とそろえてある。太い血管が上に長いので、窓の上で切れないよう少し下げる
MODEL_LOOK = Look(
    "model", "Blender", "model", material="real", size_factor=1.06, shift_y=-0.08
)

REALISTIC_LOOKS: list[Look] = [
    MODEL_LOOK,
    Look("surgical", "手術寄り", "flesh", fat_amount=1.0, gloss=1.0, saturation=1.0, coronary=0.22),
    Look(
        "vivid",
        "生々しい",
        "flesh",
        fat_amount=0.8,
        gloss=1.12,
        saturation=1.05,
        coronary=0.72,
        lively=1.0,
    ),
    Look(
        "anatomy",
        "断面",
        "flesh",
        fat_amount=0.48,
        gloss=0.8,
        saturation=1.0,
        coronary=1.0,
        section=True,
        yaw_offset_deg=12.0,
        pitch_offset_deg=-10.0,
    ),
]

STYLE_LOOKS: dict[str, Look] = {
    "mech": Look("mech", "機械", "mech"),
    "poly": Look("poly", "ポリゴン", "poly"),
    "xray": Look(
        "xray",
        "レントゲン",
        "scan",
        additive=True,
        tint_dense=(0.80, 0.84, 0.88),
        tint_thin=(0.34, 0.37, 0.42),
        grain=0.35,
        density=0.95,
        size_factor=0.80,
        # 胸の正面像では心臓の 3 分の 2 が体の左（画面右）にあり、横隔膜に乗る
        shift_x=0.14,
        shift_y=-0.06,
    ),
    "xray_heart": Look(
        "xray_heart",
        "レントゲン（心臓だけ）",
        "scan",
        cutout=True,
        tint_dense=(0.86, 0.92, 1.0),
        tint_thin=(0.42, 0.52, 0.66),
        grain=0.3,
        density=1.1,
    ),
}

DEFAULT_REALISTIC_LOOK = MODEL_LOOK.key

# レントゲン4: Blender の心臓を X 線で写し、周りに肋骨を描く（スタイル xray_heart の見た目
# "model"）。肋骨が見えるよう心臓はリアル1 より小さめ。X 線の色はレントゲン3 と同じ
XRAY_MODEL_LOOK = Look(
    "model",
    "レントゲン（Blender）",
    "model",
    cutout=True,
    tint_dense=(0.86, 0.92, 1.0),
    tint_thin=(0.42, 0.52, 0.66),
    grain=0.3,
    size_factor=0.78,
    shift_y=-0.02,
    material="xray",
    bones=True,
)


def realistic_look(key: str, material: str = "") -> Look:
    """リアルの見た目。Blender の心臓には材質（material）も入れる（空なら赤）。"""
    for look in REALISTIC_LOOKS:
        if look.key == key:
            if look.program == "model" and material:
                return replace(look, material=material)
            return look
    return REALISTIC_LOOKS[0]


def xray_model_look(material: str = "") -> Look:
    """レントゲン4 の見た目。心臓の材質を変えられる（空なら X 線）。

    X 線のときだけ背景に重ねる描き方（cutout）。ほかの材質の心臓は透けない（手の裏も隠す）。
    """
    material = material or XRAY_MODEL_LOOK.material
    return replace(XRAY_MODEL_LOOK, material=material, cutout=material == XRAY_MODEL_LOOK.material)


def style_look(style: str, look: str = "", material: str = "", xray_material: str = "") -> Look:
    """立体で描くスタイルの見た目。look はプロファイルの realistic_look。

    material はリアル1、xray_material はレントゲン4 の心臓の材質。
    """
    if style == "realistic":
        return realistic_look(look, material)
    if style == "xray_heart" and look == XRAY_MODEL_LOOK.key:
        return xray_model_look(xray_material)
    return STYLE_LOOKS[style]
