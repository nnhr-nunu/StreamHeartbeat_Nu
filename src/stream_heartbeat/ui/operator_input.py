"""操作画面「① 入力」: マイクと、マイクの代わりの入力（ファイル・心拍計）の切り替え。

OperatorWindow の部品（self._mics・self._meter・self._level・self._input など）を前提にする。
"""

from __future__ import annotations

from stream_heartbeat.audio import list_mics
from stream_heartbeat.i18n import tr
from stream_heartbeat.ui.input_panel import MODE_BLE, MODE_MIC

# この秒数マイクから何も届かなければ、抜けたか止まったとみなして知らせる
NO_AUDIO_S = 2.0
NO_AUDIO_LABEL = "マイクから音が届いていません。つながりと、選んだマイクを確かめてください"
MIC_FAIL_LABEL = "マイクを開けません。OBS と同時に使うときは、独占モードをオフにしてください"


class InputMixin:
    def _fill_mics(self) -> None:
        self._mics.blockSignals(True)
        self._mics.clear()
        for mic in list_mics():
            self._mics.addItem(mic.name, mic.id)
        self._mics.blockSignals(False)

    def _on_mics_changed(self) -> None:
        """保存したマイクが戻ればそれに、抜けたら既定のマイクに切り替える。"""
        # 閉じたあとに届いた知らせで、止めたマイクを開き直さない（止める人がいなくなる）
        if self._closing:
            return
        self._fill_mics()
        self._mics.blockSignals(True)
        self._select_mic(self._session.profile.mic_id)
        self._mics.blockSignals(False)
        self._restart_mic()

    def _restart_mic(self) -> None:
        self._apply_controls()
        if self._input.mode != MODE_MIC:
            return
        mic_id = str(self._mics.currentData() or "")
        self._last_audio = self._now()
        self._no_audio = False
        try:
            self._mic.start(mic_id)
        except Exception:
            self._mic_open = False
            self._meter.setValue(0)
            self._level.setText(tr(MIC_FAIL_LABEL))
            self._level.show()
            return
        self._mic_open = True
        self._level.hide()

    def _watch_audio(self, got_samples: bool, now: float) -> None:
        if got_samples:
            self._last_audio = now
            if self._no_audio:
                self._no_audio = False
                self._level.hide()
            return
        if self._mic_open and not self._no_audio and now - self._last_audio > NO_AUDIO_S:
            self._no_audio = True
            self._meter.setValue(0)
            self._level.setText(tr(NO_AUDIO_LABEL))
            self._level.show()

    def _on_input_mode(self, mode: str) -> None:
        """入力のしかたを変えた。マイクを使わない間はマイクを閉じる。"""
        self._show_input_rows()
        if mode == MODE_MIC:
            self._restart_mic()
        else:
            self._mic.stop()
            self._mic_open = False
            self._no_audio = False
            self._level.hide()
            self._meter.setValue(0)
        # 心拍計は音が無いので、心拍の補正は使えない
        self._sync_cal_ui()

    def _show_input_rows(self) -> None:
        mode = self._input.mode
        self._input_form.setRowVisible(self._mics, mode == MODE_MIC)
        self._input_form.setRowVisible(self._meter, mode != MODE_BLE)

    def _pull_input(self, now: float) -> tuple[list[float], list[float]]:
        """(音, 心拍計の拍の時刻)。"""
        if self._input.mode == MODE_MIC:
            return self._mic.pull_mono(), []
        return self._input.pull(now), self._input.beats(now)

    def _input_live_text(self, bpm: int) -> str | None:
        """拍を取れているときの上の帯の文（心拍計のときだけ。ほかは None）。"""
        if self._input.mode == MODE_BLE:
            return tr("心拍計から受信中  {bpm} BPM", bpm=bpm)
        return None
