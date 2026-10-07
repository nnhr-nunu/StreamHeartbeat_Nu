"""操作画面の補正（心拍の補正の録音・拍・保存・消去）。OperatorWindow の部品を前提にする。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from stream_heartbeat.i18n import tr
from stream_heartbeat.samples import AUDIO_FILTER, load_audio_mono
from stream_heartbeat.ui.input_panel import MODE_BLE

CAL_START = "補正開始"
CAL_SAVE = "補正を保存"
CAL_DISCARD = "中止"
CAL_RESET = "保存した補正を消す"


class CalibrationMixin:
    """OperatorWindow が持つ部品（self._cal_btn など）と _flash・_save_current を前提にする。"""

    def _sync_cal_ui(self) -> None:
        on = self._session.recording
        saved = bool(self._session.profile.calibration)
        self._refresh_cal_texts()
        # 心拍計は音が無いので、補正を始められない（補正中に切り替えたときは保存・中止はできる）
        self._cal_btn.setEnabled(on or self._input.mode != MODE_BLE)
        self._discard_cal.setEnabled(on)
        self._tap_btn.setEnabled(on)
        self._tap_shortcut.setEnabled(on)
        self._reset_cal.setEnabled(saved and not on)
        if on:
            self._monitor.start()
            self._tap_btn.setFocus()
            return
        self._monitor.stop()

    def _tap_text(self) -> str:
        """「拍」ボタンの文字。補正中は打った数も付ける。"""
        count = len(self._session.taps) if self._session.recording else 0
        return f"{tr('拍')}  {count}" if count else tr("拍")

    def _refresh_cal_texts(self) -> None:
        self._cal_btn.setText(tr(CAL_SAVE if self._session.recording else CAL_START))
        self._tap_btn.setText(self._tap_text())

    def _cal_hint_text(self) -> str:
        return tr(
            "心拍数が半分や倍に出るときだけ使います。"
            "「{start}」を押すと自分の心音が聞こえるので（ヘッドホン推奨）、"
            "鼓動に合わせて「拍」かスペースキーを10回ほど押し、"
            "「{save}」を押します。",
            start=tr(CAL_START),
            save=tr(CAL_SAVE),
        )

    def _on_cal_primary(self) -> None:
        if self._session.recording:
            self._commit_cal()
        else:
            self._begin_cal()

    def _begin_cal(self) -> None:
        self._session.begin_calibration(self._session.now)
        self._sync_cal_ui()

    def _discard_current_cal(self) -> None:
        self._session.discard_calibration()
        self._sync_cal_ui()
        self._flash("補正を中止しました")

    def _tap_now(self) -> None:
        if self._session.tap(self._session.now):
            self._tap_btn.setText(self._tap_text())

    def _commit_cal(self) -> None:
        saved = self._session.commit_calibration()
        self._sync_cal_ui()
        if not saved:
            self._flash("音が録れていなかったので保存しませんでした。マイクを確かめてください")
            return
        self._save_current(notice="補正を保存しました")

    def _confirm_reset(self) -> bool:
        answer = QMessageBox.question(
            self,
            tr(CAL_RESET),
            tr("保存した心拍の補正を全部消して、最初からやり直しますか？"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _reset_saved_cal(self) -> None:
        if not self._confirm_reset():
            return
        self._session.reset_calibration()
        self._sync_cal_ui()
        self._save_current(notice="保存した補正を消しました")

    def _add_audio_sample(self) -> None:
        path, _ok = QFileDialog.getOpenFileName(
            self, tr("心音ファイルを追加"), "", tr(AUDIO_FILTER)
        )
        if not path:
            return
        try:
            samples = load_audio_mono(Path(path))
        except (OSError, ValueError, RuntimeError):
            self._flash("この音声ファイルは読めませんでした")
            return
        if not samples:
            self._flash("音声ファイルが空でした")
            return
        self._session.profile.calibration.append(samples)
        self._session.rebuild_detector()
        self._sync_cal_ui()
        self._save_current(notice="心音サンプルを追加しました")
