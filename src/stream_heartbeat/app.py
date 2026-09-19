"""操作用と配信用の 2 窓を起動する。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from stream_heartbeat.paths import resolve_data_dir
from stream_heartbeat.profile import (
    HeartProfile,
    load_app_state,
    load_last_profile_name,
    load_profile,
    profiles_dir,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon, configure_process_identity
from stream_heartbeat.ui.capture_exclude import configure_dev_allow_capture_from_env
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow
from stream_heartbeat.ui.placement import apply_window_geom, place_side_by_side


def _initial_session() -> HeartSession:
    data = resolve_data_dir()
    name = load_last_profile_name(data)
    path = profiles_dir(data) / f"{name}.json"
    profile = load_profile(path) if path.is_file() else HeartProfile(name=name)
    return HeartSession(profile)


def run() -> int:
    configure_process_identity()
    configure_dev_allow_capture_from_env()
    app = QApplication(sys.argv)
    app.setApplicationName("StreamHeartbeat(ぬ)")
    apply_app_icon(app)
    session = _initial_session()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    output.set_quit_handler(operator.close)
    operator.show()
    output.show()
    screen = app.primaryScreen()
    area = screen.availableGeometry() if screen is not None else None
    state = load_app_state(resolve_data_dir())
    op_ok = False
    out_ok = False
    if area is not None:
        op_ok = apply_window_geom(operator, state.get("operator_geom"), area)
        out_ok = apply_window_geom(output, state.get("output_geom"), area)
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
    return app.exec()
