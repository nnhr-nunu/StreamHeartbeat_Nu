"""操作画面: 透明な背景の心臓を、ほかの窓の手前に重ねる設定（この PC の設定に覚える）。

OperatorWindow の部品（self._output・self._data_dir）を前提にする。
"""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from stream_heartbeat.profile import load_app_state, save_app_state

OVERLAY_HINT = "心臓を右ドラッグで移動、ホイールで窓の大きさを変えます"


class OverlayMixin:
    def _build_overlay_controls(self) -> QWidget:
        state = load_app_state(self._data_dir)
        self._on_top = QCheckBox("ほかの窓の手前に重ねる")
        self._on_top.setChecked(bool(state.get("overlay_on_top", False)))
        self._click_through = QCheckBox("クリックを後ろの窓へ通す")
        self._click_through.setChecked(bool(state.get("overlay_click_through", False)))
        self._overlay_hint = QLabel(OVERLAY_HINT)
        self._overlay_hint.setObjectName("meta")
        self._overlay_hint.setWordWrap(True)
        self._overlay_wrap = QWidget()
        col = QVBoxLayout(self._overlay_wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self._on_top)
        col.addWidget(self._click_through)
        col.addWidget(self._overlay_hint)
        self._on_top.toggled.connect(self._on_overlay_changed)
        self._click_through.toggled.connect(self._on_overlay_changed)
        return self._overlay_wrap

    def _on_overlay_changed(self, _checked: bool = False) -> None:
        try:
            save_app_state(
                self._data_dir,
                overlay_on_top=self._on_top.isChecked(),
                overlay_click_through=self._click_through.isChecked(),
            )
        except OSError:
            pass
        self._apply_controls()

    def _sync_overlay(self) -> None:
        """透明な背景のときだけ選べる。窓へ今の選択を渡す（作り直すかは呼ぶ側が決める）。"""
        on_top = self._on_top.isChecked()
        through = self._click_through.isChecked()
        self._overlay_wrap.setVisible(self._session.profile.backdrop == "transparent")
        self._click_through.setEnabled(on_top)
        self._overlay_hint.setVisible(on_top and not through)
        self._output.set_overlay_choice(on_top, through)
