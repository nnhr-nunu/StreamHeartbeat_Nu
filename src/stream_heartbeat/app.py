"""操作用と配信用の 2 窓を起動する。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from stream_heartbeat.paths import resolve_data_dir
from stream_heartbeat.profile import (
    HeartProfile,
    load_last_profile_name,
    load_profile,
    profiles_dir,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.app_icon import apply_app_icon, configure_process_identity
from stream_heartbeat.ui.operator_window import OperatorWindow
from stream_heartbeat.ui.output_window import OutputWindow


def _initial_session() -> HeartSession:
    data = resolve_data_dir()
    name = load_last_profile_name(data)
    path = profiles_dir(data) / f"{name}.json"
    profile = load_profile(path) if path.is_file() else HeartProfile(name=name)
    return HeartSession(profile)


def run() -> int:
    configure_process_identity()
    app = QApplication(sys.argv)
    app.setApplicationName("StreamHeartbeat(ぬ)")
    apply_app_icon(app)
    session = _initial_session()
    output = OutputWindow(session)
    operator = OperatorWindow(session, output)
    operator.show()
    output.show()
    return app.exec()
