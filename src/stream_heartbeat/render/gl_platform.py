"""OpenGL の OS ごとの違いを吸収する（Mac）。

Mac の OpenGL は、何も頼まないと古い 2.1 になり、新しい書き方のシェーダーが通らない。
4.1 Core を頼めば通るが、こんどは版の宣言 130 を受け付けないので 150 に読み替える。
シェーダーの本文は 130 と 150 のどちらでも通る書き方にしてある。Windows は今まで通り。
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QSurfaceFormat

MAC = sys.platform == "darwin"


def glsl(source: str) -> str:
    """シェーダーの版の宣言を、この PC の OpenGL に合わせる。"""
    if not MAC:
        return source
    return source.replace("#version 130", "#version 150", 1)


def core_profile(fmt: QSurfaceFormat) -> QSurfaceFormat:
    """Mac だけ OpenGL 4.1 Core を頼む。ほかはそのまま返す。"""
    if MAC:
        fmt.setVersion(4, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    return fmt


def set_default_format() -> None:
    """QApplication を作る前に呼ぶ。Mac は後からだと、窓と裏の描画で GL を共有できない。"""
    if MAC:
        QSurfaceFormat.setDefaultFormat(core_profile(QSurfaceFormat.defaultFormat()))
