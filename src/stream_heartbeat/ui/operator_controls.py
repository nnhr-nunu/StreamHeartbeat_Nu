"""操作画面の部品とプロファイルの値を行き来させる。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stream_heartbeat.config import DEFAULT_BEAT_TEXT, DEFAULT_BEAT_TEXT_COLOR
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.ui.combo import MarkedComboBox

if TYPE_CHECKING:
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.output_window import OutputWindow


class ProfileControlsMixin:
    """OperatorWindow が持つ部品（self._text など）を前提にする。"""

    _session: HeartSession
    _output: OutputWindow

    def _load_into_controls(self, profile: HeartProfile) -> None:
        # 途中で値変更の合図が飛ぶと、まだ初期値の他の項目でプロファイルが上書きされる。
        # 全部入れ終わってから一度だけ反映する。
        widgets = (
            self._text,
            self._show_beat_text,
            self._beat_scale,
            self._beat_opacity,
            self._beat_x,
            self._beat_y,
            self._beat_jitter,
            self._beat_tilt,
            self._beat_color,
            self._beat_outline,
            self._show_bpm,
            self._bpm_scale,
            self._bpm_x,
            self._bpm_y,
            self._bpm_color,
            self._bpm_outline,
            self._backdrop,
            self._scale,
            self._opacity,
            self._public_id,
            self._bpm_url,
            self._style,
            self._angle_locked,
            self._mics,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self._text.setText(profile.beat_text)
            self._show_beat_text.setChecked(profile.show_beat_text)
            self._beat_scale.setValue(int(profile.beat_text_scale * 100))
            self._beat_opacity.setValue(int(profile.beat_text_opacity * 100))
            self._beat_x.setValue(int(round(profile.beat_text_x * 100)))
            self._beat_y.setValue(int(round(profile.beat_text_y * 100)))
            self._beat_jitter.setValue(int(round(profile.beat_text_jitter * 100)))
            self._beat_tilt.setValue(int(round(profile.beat_text_tilt * 100)))
            self._select_combo(self._beat_color, profile.beat_text_color)
            self._select_combo(self._beat_outline, profile.beat_text_outline)
            self._show_bpm.setChecked(profile.show_bpm)
            self._bpm_scale.setValue(int(profile.bpm_scale * 100))
            self._bpm_x.setValue(int(round(profile.bpm_x * 100)))
            self._bpm_y.setValue(int(round(profile.bpm_y * 100)))
            self._select_combo(self._bpm_color, profile.bpm_color)
            self._select_combo(self._bpm_outline, profile.bpm_outline)
            self._select_combo(self._backdrop, profile.backdrop)
            self._scale.setValue(int(profile.scale * 100))
            self._opacity.setValue(int(profile.opacity * 100))
            self._public_id.setText(profile.oshilog_public_id)
            self._bpm_url.setText(profile.oshilog_bpm_url)
            self._select_style(profile.style, profile.realistic_look)
            for i in range(self._mics.count()):
                if self._mics.itemData(i) == profile.mic_id:
                    self._mics.setCurrentIndex(i)
                    break
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._output.canvas.sync_orbit_from_profile()
        self._apply_controls()
        self._sync_cal_ui()

    def _style_choice(self) -> tuple[str, str]:
        data = self._style.currentData()
        if isinstance(data, tuple) and len(data) == 2:
            style = str(data[0] or "realistic")
            look = str(data[1] or "surgical")
            return style, look
        return "realistic", "surgical"

    def _select_style(self, style: str, look: str) -> None:
        wanted = (style, look if style == "realistic" else "")
        for i in range(self._style.count()):
            if self._style.itemData(i) == wanted:
                self._style.setCurrentIndex(i)
                return
        if style == "realistic":
            for i in range(self._style.count()):
                if self._style.itemData(i) == ("realistic", "surgical"):
                    self._style.setCurrentIndex(i)
                    return
        self._style.setCurrentIndex(0)

    def _select_combo(self, combo: MarkedComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _apply_controls(self) -> None:
        profile = self._session.profile
        profile.name = self._profiles.currentText().strip() or "default"
        style, look = self._style_choice()
        profile.style = style
        profile.realistic_look = look
        self._output.canvas.angle_locked = self._angle_locked.isChecked()
        self._refresh_style_controls()
        profile.scale = self._scale.value() / 100.0
        profile.opacity = self._opacity.value() / 100.0
        profile.beat_text = self._text.text() or DEFAULT_BEAT_TEXT
        profile.show_beat_text = self._show_beat_text.isChecked()
        profile.beat_text_scale = self._beat_scale.value() / 100.0
        profile.beat_text_opacity = self._beat_opacity.value() / 100.0
        profile.beat_text_x = self._beat_x.value() / 100.0
        profile.beat_text_y = self._beat_y.value() / 100.0
        profile.beat_text_jitter = self._beat_jitter.value() / 100.0
        profile.beat_text_tilt = self._beat_tilt.value() / 100.0
        profile.beat_text_color = str(self._beat_color.currentData() or DEFAULT_BEAT_TEXT_COLOR)
        profile.beat_text_outline = str(self._beat_outline.currentData() or "")
        profile.show_bpm = self._show_bpm.isChecked()
        self._beat_details.setVisible(profile.show_beat_text)
        self._bpm_details.setVisible(profile.show_bpm)
        profile.bpm_scale = self._bpm_scale.value() / 100.0
        profile.bpm_x = self._bpm_x.value() / 100.0
        profile.bpm_y = self._bpm_y.value() / 100.0
        profile.bpm_color = str(self._bpm_color.currentData() or "#FFFFFF")
        profile.bpm_outline = str(self._bpm_outline.currentData() or "")
        profile.backdrop = str(self._backdrop.currentData() or "green")
        profile.show_arrhythmia = False
        profile.oshilog_public_id = self._public_id.text().strip()
        profile.oshilog_bpm_url = self._bpm_url.text().strip()
        if self._mics.currentData():
            profile.mic_id = str(self._mics.currentData())
        self._output.apply_backdrop()

    def _reset_beat_look(self) -> None:
        blank = HeartProfile()
        profile = self._session.profile
        profile.beat_text = blank.beat_text
        profile.show_beat_text = blank.show_beat_text
        profile.beat_text_scale = blank.beat_text_scale
        profile.beat_text_opacity = blank.beat_text_opacity
        profile.beat_text_x = blank.beat_text_x
        profile.beat_text_y = blank.beat_text_y
        profile.beat_text_jitter = blank.beat_text_jitter
        profile.beat_text_tilt = blank.beat_text_tilt
        profile.beat_text_color = blank.beat_text_color
        profile.beat_text_outline = blank.beat_text_outline
        self._load_into_controls(profile)

    def _reset_bpm_look(self) -> None:
        blank = HeartProfile()
        profile = self._session.profile
        profile.show_bpm = blank.show_bpm
        profile.bpm_scale = blank.bpm_scale
        profile.bpm_x = blank.bpm_x
        profile.bpm_y = blank.bpm_y
        profile.bpm_color = blank.bpm_color
        profile.bpm_outline = blank.bpm_outline
        self._load_into_controls(profile)
