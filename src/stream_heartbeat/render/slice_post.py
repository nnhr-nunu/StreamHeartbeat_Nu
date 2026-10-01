"""断面のスタイル（心エコー・MRI）を 2 回に分けて描く。

1 回目は窓より粗い画（縮めた画）へ信号の強さを書き、2 回目でその画をぼかしながら
窓へ重ねる。実機の画のにじみ（エコーの横方向の広がり・MRI の撮像の粗さ）を、
画素ごとの重い計算を増やさずに出せる。
"""

from __future__ import annotations

import math

from PySide6.QtGui import QOpenGLFunctions
from PySide6.QtOpenGL import QOpenGLFramebufferObject

from stream_heartbeat.render.chamber_glsl import SliceShader, SliceShaderError, UniformValue

GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_LINEAR = 0x2601
GL_FRAMEBUFFER = 0x8D40
GL_FRAMEBUFFER_BINDING = 0x8CA6
GL_TEXTURE0 = 0x84C0
GL_COLOR_BUFFER_BIT = 0x4000

# 2 回目の断片シェーダーが粗い画を読む名前と、その大きさ（画素）の名前
COARSE_SAMPLER = "uCoarse"
COARSE_SIZE = "uCoarseSize"


class BlurredSlice:
    """粗い画へ描く 1 回目と、ぼかして窓へ重ねる 2 回目。作成時にカレントなコンテキストが必要。"""

    def __init__(self, functions: QOpenGLFunctions, coarse: str, final: str) -> None:
        self._gl = functions
        self._coarse = SliceShader(functions, coarse)
        self._final = SliceShader(functions, final)
        self._fbo: QOpenGLFramebufferObject | None = None
        # 粗い画を作れない環境では、ここで分かるようにする（呼び出し側は 2D の代替へ戻る）
        self._target(4, 4)

    def _target(self, width: int, height: int) -> QOpenGLFramebufferObject:
        fbo = self._fbo
        if fbo is None or fbo.width() != width or fbo.height() != height:
            fbo = QOpenGLFramebufferObject(width, height)
            if not fbo.isValid():
                raise SliceShaderError("粗い画を作れません")
            gl = self._gl
            # 引き伸ばすときに画素を混ぜて、なめらかにつなぐ
            gl.glBindTexture(GL_TEXTURE_2D, fbo.texture())
            gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            gl.glBindTexture(GL_TEXTURE_2D, 0)
            self._fbo = fbo
        return fbo

    def draw(
        self,
        width: int,
        height: int,
        factor: float,
        coarse: dict[str, UniformValue],
        final: dict[str, UniformValue],
    ) -> None:
        """factor は粗い画の、窓に対する大きさ（0〜1）。

        1 回目の uniforms は窓の画素で書く。1 回目のシェーダーは uCoarseScale（粗い画の画素 /
        窓の画素）で gl_FragCoord を窓の画素へ直して使う。
        """
        gl = self._gl
        factor = max(0.1, min(1.0, factor))
        cw = max(1, math.ceil(width * factor))
        ch = max(1, math.ceil(height * factor))
        # 描き終えたら、もとの描き先（窓・確認用の画）へ戻す
        previous = int(gl.glGetIntegerv(GL_FRAMEBUFFER_BINDING))
        fbo = self._target(cw, ch)
        fbo.bind()
        gl.glClearColor(0.0, 0.0, 0.0, 0.0)
        gl.glClear(GL_COLOR_BUFFER_BIT)
        scale = (cw / max(1, width), ch / max(1, height))
        self._coarse.draw(cw, ch, {**coarse, "uCoarseScale": scale})
        gl.glBindFramebuffer(GL_FRAMEBUFFER, previous)
        gl.glActiveTexture(GL_TEXTURE0)
        gl.glBindTexture(GL_TEXTURE_2D, fbo.texture())
        self._final.draw(
            width,
            height,
            {**final, COARSE_SIZE: (float(cw), float(ch))},
            samplers={COARSE_SAMPLER: 0},
        )
        gl.glBindTexture(GL_TEXTURE_2D, 0)
