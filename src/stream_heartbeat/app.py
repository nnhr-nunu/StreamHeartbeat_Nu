"""操作用と配信用の 2 窓を起動する。

起動は数秒かかるので、Qt が動き出したらまず「お待ちください」の小窓を出す。
重い部品（操作画面・音の処理・心臓の形）はその後で読み込む。
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

from stream_heartbeat.render.gl_platform import set_default_format
from stream_heartbeat.ui.app_icon import apply_app_icon, configure_process_identity

if TYPE_CHECKING:
    from stream_heartbeat.session import HeartSession


def _initial_session() -> HeartSession:
    from stream_heartbeat.paths import resolve_data_dir
    from stream_heartbeat.profile import (
        HeartProfile,
        load_last_profile_name,
        load_profile,
        profiles_dir,
    )
    from stream_heartbeat.session import HeartSession

    data = resolve_data_dir()
    name = load_last_profile_name(data)
    path = profiles_dir(data) / f"{name}.json"
    profile = load_profile(path) if path.is_file() else HeartProfile(name=name)
    return HeartSession(profile)


def run() -> int:
    configure_process_identity()
    set_default_format()
    app = QApplication(sys.argv)
    app.setApplicationName("StreamHeartbeat(ぬ)")
    apply_app_icon(app)

    from stream_heartbeat.ui.splash import StartupSplash

    splash = StartupSplash()
    splash.show_now()
    splash.step("設定を読み込んでいます")

    from stream_heartbeat.paths import cache_dir, resolve_data_dir
    from stream_heartbeat.profile import load_app_state
    from stream_heartbeat.render.mesh_cache import has_cached_mesh, shared_heart_mesh
    from stream_heartbeat.ui.operator_window import OperatorWindow
    from stream_heartbeat.ui.output_window import OutputWindow
    from stream_heartbeat.ui.placement import apply_window_geom, place_side_by_side

    session = _initial_session()
    cache = cache_dir()
    if has_cached_mesh(cache):
        splash.step("心臓を用意しています")
    else:
        splash.step("心臓の形を作っています（初回だけ少しかかります）")
    # 配信用の窓が OpenGL を始めるときに使う形を、先に読んでおく（2 回目からは保存した形を読むだけ）
    shared_heart_mesh(cache)
    splash.step("画面を組み立てています")
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    output.set_quit_handler(operator.close)
    operator.show()
    output.show()
    screen = app.primaryScreen()
    area = screen.availableGeometry() if screen is not None else None
    screens = [item.availableGeometry() for item in app.screens()]
    state = load_app_state(resolve_data_dir())
    op_ok = False
    out_ok = False
    if area is not None:
        op_ok = apply_window_geom(operator, state.get("operator_geom"), area, screens)
        out_ok = apply_window_geom(output, state.get("output_geom"), area, screens)
        if not op_ok and not out_ok:
            op_pos, out_pos = place_side_by_side(operator.size(), output.size(), area)
            output.move(out_pos)
            operator.move(op_pos)
        elif not op_ok:
            op_pos, _out_pos = place_side_by_side(operator.size(), output.size(), area)
            operator.move(op_pos)
        elif not out_ok:
            _op_pos, out_pos = place_side_by_side(operator.size(), output.size(), area)
            output.move(out_pos)
    output.raise_()
    operator.raise_()
    operator.activateWindow()
    splash.finish(operator)
    return app.exec()
