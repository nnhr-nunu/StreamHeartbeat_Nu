"""テスト全体の前準備。"""

from __future__ import annotations

from stream_heartbeat.render.gl_platform import set_default_format

# アプリと同じく、QApplication より前に OpenGL の既定を決める（Mac だけ 4.1 Core）
set_default_format()
