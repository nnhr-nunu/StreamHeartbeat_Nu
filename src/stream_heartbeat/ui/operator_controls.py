"""操作画面の部品とプロファイルの値を行き来させる。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QAbstractSlider

from stream_heartbeat.audio import default_mic_id
from stream_heartbeat.config import DEFAULT_BEAT_TEXT, DEFAULT_BEAT_TEXT_COLOR
from stream_heartbeat.i18n import add_tr_item, tr
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.heart_looks import DEFAULT_REALISTIC_LOOK
from stream_heartbeat.render.model_shaders import MATERIAL_REAL, MATERIAL_XRAY
from stream_heartbeat.ui.combo import MarkedComboBox
from stream_heartbeat.ui.effects import EFFECT_HINTS, active_effect, effect_choices

if TYPE_CHECKING:
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.output_window import OutputWindow


class ProfileControlsMixin:
    """OperatorWindow が持つ部品（self._text など）を前提にする。"""

    _session: HeartSession
    _output: OutputWindow
    # マイクを操作画面で選び直したときだけプロファイルへ書く。保存したマイクが
    # つながっていないときに、代わりに開いたマイクで上書きしないため
    _mic_chosen: bool = False

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
            self._material,
            self._xray_material,
            self._angle_locked,
            self._mics,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self._text.setText(profile.beat_text)
            self._show_beat_text.setChecked(profile.show_beat_text)
            _set_percent(self._beat_scale, profile.beat_text_scale)
            _set_percent(self._beat_opacity, profile.beat_text_opacity)
            _set_percent(self._beat_x, profile.beat_text_x)
            _set_percent(self._beat_y, profile.beat_text_y)
            _set_percent(self._beat_jitter, profile.beat_text_jitter)
            _set_percent(self._beat_tilt, profile.beat_text_tilt)
            self._select_combo(self._beat_color, profile.beat_text_color)
            self._select_combo(self._beat_outline, profile.beat_text_outline)
            self._show_bpm.setChecked(profile.show_bpm)
            _set_percent(self._bpm_scale, profile.bpm_scale)
            _set_percent(self._bpm_x, profile.bpm_x)
            _set_percent(self._bpm_y, profile.bpm_y)
            self._select_combo(self._bpm_color, profile.bpm_color)
            self._select_combo(self._bpm_outline, profile.bpm_outline)
            self._select_combo(self._backdrop, profile.backdrop)
            _set_percent(self._scale, profile.scale)
            _set_percent(self._opacity, profile.opacity)
            self._public_id.setText(profile.oshilog_public_id)
            self._bpm_url.setText(profile.oshilog_bpm_url)
            self._select_style(profile.style, profile.realistic_look)
            index = self._material.findData(profile.heart_material)
            self._material.setCurrentIndex(max(0, index))
            index = self._xray_material.findData(profile.xray_material)
            self._xray_material.setCurrentIndex(max(0, index))
            self._select_mic(profile.mic_id)
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
            # 見た目の無いスタイル（レントゲン3 など）は空のまま。リアルの見た目で埋めると、
            # 同じ名前の見た目を持つ別のスタイル（レントゲン4）と取り違える
            look = str(data[1] or (DEFAULT_REALISTIC_LOOK if style == "realistic" else ""))
            return style, look
        return "realistic", DEFAULT_REALISTIC_LOOK

    def _select_style(self, style: str, look: str) -> None:
        # 見た目の違いがあるスタイル（リアル・レントゲン）はその見た目、無ければ素の形を選ぶ
        for wanted in ((style, look), (style, "")):
            for i in range(self._style.count()):
                if self._style.itemData(i) == wanted:
                    self._style.setCurrentIndex(i)
                    return
        if style == "realistic":
            for i in range(self._style.count()):
                if self._style.itemData(i) == ("realistic", DEFAULT_REALISTIC_LOOK):
                    self._style.setCurrentIndex(i)
                    return
        self._style.setCurrentIndex(0)

    def _select_combo(self, combo: MarkedComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        # 選択肢に無い値（手で書いた色など）は消さずに選択肢へ足して残す
        add_tr_item(combo, "保存値 {value}", value, value=value)
        combo.setCurrentIndex(combo.count() - 1)

    def _select_mic(self, mic_id: str) -> None:
        """保存したマイクを選ぶ。つながっていなければ OS の既定のマイクを開く。"""
        self._mic_chosen = False
        for wanted in (mic_id, default_mic_id()):
            index = self._mics.findData(wanted) if wanted else -1
            if index >= 0:
                self._mics.setCurrentIndex(index)
                return
        if self._mics.count():
            self._mics.setCurrentIndex(0)

    def _on_mic_picked(self, _index: int = 0) -> None:
        self._mic_chosen = True
        self._restart_mic()

    def _apply_controls(self) -> None:
        profile = self._session.profile
        profile.name = self._profiles.currentText().strip() or "default"
        style, look = self._style_choice()
        profile.style = style
        profile.realistic_look = look
        profile.heart_material = str(self._material.currentData() or MATERIAL_REAL)
        profile.xray_material = str(self._xray_material.currentData() or MATERIAL_XRAY)
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
        if self._mic_chosen and self._mics.currentData():
            profile.mic_id = str(self._mics.currentData())
        self._output.apply_backdrop()
        if self._output.needs_rebuild():
            self._rebuild_output()

    def _sync_effect_choices(self) -> None:
        """演出の一覧を今のスタイルで選べるものにそろえ、保存した演出を選ぶ。

        スタイルが対応しない演出は「なし」と見せるが、プロファイルの値は消さない
        （対応するスタイルへ戻せば、また出る）。
        """
        style, _look = self._style_choice()
        effect = self._session.profile.effect
        choices = effect_choices(style)
        keys = [key for key, _label in choices]
        self._effect.blockSignals(True)
        try:
            if [self._effect.itemData(i) for i in range(self._effect.count())] != keys:
                self._effect.clear()
                for key, label in choices:
                    self._effect.addItem(tr(label), key)
            self._effect.setCurrentIndex(keys.index(effect) if effect in keys else 0)
        finally:
            self._effect.blockSignals(False)
        has_choice = len(keys) > 1
        self._style_form.setRowVisible(self._effect, has_choice)
        hint = EFFECT_HINTS.get(active_effect(style, effect), "")
        self._effect_hint.setText(tr(hint))
        self._effect_hint.setVisible(has_choice and bool(hint))

    def _on_effect_picked(self, _index: int = 0) -> None:
        self._session.profile.effect = str(self._effect.currentData() or "")
        self._refresh_style_controls()

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


def _set_percent(slider: QAbstractSlider, value: float) -> None:
    """0.57 → 57 のように百分率で入れる。切り捨てると保存のたびに 1 ずつ減るので丸める。"""
    percent = int(round(value * 100))
    slider.setValue(max(slider.minimum(), min(slider.maximum(), percent)))
