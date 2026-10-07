"""操作画面の「新しい版が出ています」。通信できて、新しい版があったときだけ出す。"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

from stream_heartbeat.i18n import SKIP_PROP, tr
from stream_heartbeat.update_check import RELEASE_PAGE, UpdateChecker

# 起動の重い所（GL の準備など）と重ならないよう、少し待ってから確かめる
START_DELAY_MS = 3000
POLL_MS = 500
LINK_COLOR = "#c9a0ff"


class UpdateNotice(QLabel):
    def __init__(self, checker: UpdateChecker | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("meta")
        # 版を差し込んだ文なので translate_tree では付け替えず、retranslate で作り直す
        self.setProperty(SKIP_PROP, True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setOpenExternalLinks(True)
        self.setContentsMargins(12, 6, 12, 4)
        self.setToolTip(tr("GitHub のダウンロードページを開きます"))
        self.hide()
        self._checker = checker or UpdateChecker()
        self._newer: str | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._step)
        self._timer.start(START_DELAY_MS)

    def _step(self) -> None:
        if not self._checker.started:
            self._checker.start()
        if not self._checker.finished:
            self._timer.start(POLL_MS)
            return
        self._newer = self._checker.newer
        self.retranslate()

    def retranslate(self) -> None:
        if not self._newer:
            return
        text = html.escape(tr("新しい版 v{version} が出ています", version=self._newer))
        self.setText(f'<a href="{RELEASE_PAGE}" style="color: {LINK_COLOR};">{text}</a>')
        self.show()
