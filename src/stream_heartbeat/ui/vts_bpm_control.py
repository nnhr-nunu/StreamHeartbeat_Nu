"""「⑤ VTube Studio 連携」の「心拍数の数字」の段（チェック・数字の大きさ・様子の一文）。

チェックを入れると心拍数の数字のコマ（bpm_frames）を書き出して VTube Studio に出し、
心拍数が変わるたびにそのコマを出す。数字の色・縁取り・文字の大きさ（「④ 心拍数」の設定）を
変えたら、少し待ってから作り直す。VTube Studio での大きさは、この段の「数字の大きさ」で変える
（心臓とは別。配信用の窓と同じ比率だとモデルに対して小さく見えるため）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QVBoxLayout, QWidget

from stream_heartbeat.i18n import tr
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.bpm_frames import render_bpm_frames
from stream_heartbeat.render.heart_frames import write_frames
from stream_heartbeat.ui.forms import CenteredForm
from stream_heartbeat.ui.slider import labeled_slider
from stream_heartbeat.vts import ITEM_SIZE, ITEM_SIZE_MAX, ITEM_SIZE_MIN, READY, VtsClient
from stream_heartbeat.vts_bpm import BPM_FOLDER, VtsBpm
from stream_heartbeat.vts_support import clean_place
from stream_heartbeat.vts_text import (
    BPM_CHECK,
    BPM_SHOWN_NOTE,
    BPM_SHOWN_NOTICE,
    BPM_SIZE_LABEL,
    NOT_ITEMS_NOTICE,
    T_BPM_FAILED,
)

# 色などを変えてから作り直すまで待つ秒（続けて変えている間は待つ）
REMAKE_WAIT_S = 0.8


def saved_bpm_size(raw: object) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(ITEM_SIZE_MIN, min(ITEM_SIZE_MAX, float(raw)))
    return ITEM_SIZE


def bpm_look(profile: HeartProfile) -> tuple:
    """数字の絵を決める設定。変わったら作り直す。保存できるよう文字と数だけで作る。"""
    return (profile.bpm_color, profile.bpm_outline, round(profile.bpm_scale, 2))


class VtsBpmControl:
    def __init__(
        self,
        client: VtsClient,
        profile: Callable[[], HeartProfile],
        state: dict,
        items_dir: Callable[[], Path | None],
        save: Callable[..., None],
        notify: Callable[[str], None],
        choose_folder: Callable[[], None] | None = None,
    ) -> None:
        """profile は今のプロファイル、state は保存してある app_state、items_dir は書き出し先。

        choose_folder は、書き出し先が見つからないときにフォルダを選ばせる
        （チェックを入れたときだけ）。
        """
        self._client = client
        self._profile = profile
        self._items_dir = items_dir
        self._choose_folder = choose_folder
        self._save = save
        self._notify = notify
        self.bpm = VtsBpm(
            client,
            size=saved_bpm_size(state.get("vts_bpm_size")),
            place=clean_place(state.get("vts_bpm_place")),
        )
        self.bpm.on_found = self._on_found
        self.bpm.on_moved = self._on_moved
        saved_look = state.get("vts_bpm_look")
        self._made: tuple | None = tuple(saved_look) if isinstance(saved_look, list) else None
        self._pending: tuple[tuple, float] | None = None
        # 書き出しに失敗した設定（同じ設定では自動で試し直さない）と、出せなかった理由の一文
        self._failed: tuple | None = None
        self._error: Callable[[], str] | None = None
        # 数字の様子の一文（出している・出せなかった）。知らせはすぐ消えるので出し続ける
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.hide()
        self.check = QCheckBox(BPM_CHECK)
        self.check.setToolTip(
            "数字の色・縁取りは「④ 心拍数」の設定のとおりです。大きさは「数字の大きさ」で変えます。"
            "置き場所は VTube Studio の画面でドラッグして決めます"
        )
        self.size, size_row = labeled_slider(
            round(ITEM_SIZE_MIN * 100), round(ITEM_SIZE_MAX * 100), "小さく", "大きく"
        )
        self.size.setValue(round(self.bpm.size * 100))
        size_form = CenteredForm()
        size_form.setContentsMargins(0, 0, 0, 0)
        size_form.addRow(BPM_SIZE_LABEL, size_row)
        # 数字の大きさは、出すことにしている間だけ見せる
        self._size_wrap = QWidget()
        self._size_wrap.setLayout(size_form)
        # この段の部品をまとめた入れ物（⑤ の「心拍数の数字」の小見出しの下に置く）
        self.box = QWidget()
        col = QVBoxLayout(self.box)
        col.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self.check)
        col.addWidget(self._size_wrap)
        col.addWidget(self.note)
        self.check.setChecked(bool(state.get("vts_bpm_shown", False)))
        self._size_wrap.setVisible(self.check.isChecked())
        self.check.toggled.connect(self._on_toggled)
        self.size.valueChanged.connect(self._on_size)
        self.size.sliderReleased.connect(self._save_size)

    def _on_found(self, found: bool) -> None:
        """つないだ直後。出すことにしていて、場に無いか見た目が古ければ出し直す。

        つながっていない間にチェックを外していて、場に残っていればしまう（止まった数字を残さない）。
        """
        if not self.check.isChecked():
            if found:
                self.bpm.hide()
        elif not found or self._made != bpm_look(self._profile()):
            self.make()

    def _on_toggled(self, on: bool) -> None:
        self._size_wrap.setVisible(on)
        self._save(vts_bpm_shown=on)
        if self._client.state != READY:
            return
        if on:
            self.make(notice=True)
        else:
            self._error = None
            self.bpm.hide()
        self.refresh()

    def _on_moved(self) -> None:
        place = self.bpm.place
        self._save(vts_bpm_place=list(place) if place else None)

    def make(self, notice: bool = False) -> None:
        """今の設定で数字のコマを書き出して出す（出ていれば出し直す）。"""
        if self._client.state != READY:
            return
        look = bpm_look(self._profile())
        folder = self._items_dir()
        if folder is None and notice and self._choose_folder is not None:
            self._choose_folder()
            folder = self._items_dir()
        if folder is None:
            self._fail(look, lambda: tr(NOT_ITEMS_NOTICE))
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            write_frames(render_bpm_frames(self._profile()), folder / BPM_FOLDER)
        except (OSError, RuntimeError):
            self._fail(
                look,
                lambda: tr(
                    "心拍数の画像を書き出せませんでした（書き出し先のフォルダを確かめてください）"
                ),
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._made = look
        self._failed = None
        self._error = None
        self._save(vts_bpm_look=list(look))

        def shown(ok: bool) -> None:
            if not ok:
                error = self.bpm.last_error
                self._fail(None, lambda: tr(T_BPM_FAILED, error=tr(error)))
            elif notice:
                self._notify(tr(BPM_SHOWN_NOTICE))
            self.refresh()

        self.bpm.show(shown)

    def _fail(self, look: tuple | None, message: Callable[[], str]) -> None:
        """出せなかった。知らせ、様子の一文にも残す（look はその設定では自動で試し直さない）。

        message は今の表示言語で文を作る（言語を切り替えても、その言語で出し続ける）。
        """
        if look is not None:
            self._failed = look
        self._error = message
        self._notify(message())
        self.refresh()

    def refresh(self) -> None:
        """数字の様子の一文を今の状態に合わせる（変わったときだけ書き換える）。"""
        shown = self._client.state == READY and self.check.isChecked()
        if shown and self._error is not None:
            text, kind = self._error(), "warn"
        elif shown and self.bpm.instance_id is not None:
            text, kind = tr(BPM_SHOWN_NOTE), "meta"
        else:
            text, kind = "", "meta"
        if self.note.objectName() != kind:
            self.note.setObjectName(kind)
            self.note.style().unpolish(self.note)
            self.note.style().polish(self.note)
        if self.note.text() != text:
            self.note.setText(text)
        self.note.setVisible(bool(text))

    def tick(self, bpm: float) -> None:
        """操作画面のタイマーごと。心拍数のコマを出し、設定が変わっていれば作り直す。"""
        if self._client.state != READY or not self.check.isChecked():
            self._pending = None
            return
        self.bpm.set_bpm(bpm)
        look = bpm_look(self._profile())
        if self.bpm.instance_id is None or look in (self._made, self._failed):
            self._pending = None
            return
        now = time.monotonic()
        if self._pending is None or self._pending[0] != look:
            self._pending = (look, now)
            return
        # 続けて変えている間と、つまみのドラッグの途中は待つ
        dragging = QApplication.mouseButtons() != Qt.MouseButton.NoButton
        if now - self._pending[1] < REMAKE_WAIT_S or dragging:
            return
        self._pending = None
        self.make()

    def _on_size(self, value: int) -> None:
        self.bpm.set_size(value / 100.0)
        if not self.size.isSliderDown():
            self._save_size()

    def _save_size(self) -> None:
        self._save(vts_bpm_size=self.bpm.size)
