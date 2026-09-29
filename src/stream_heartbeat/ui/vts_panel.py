"""操作画面の「VTube Studio 連携」欄。

心臓を VTube Studio のアイテムにして拍ごとに動かす（モデルにピン留めすれば体と一緒に動く）。
拍と心拍数をカスタムパラメータとして送ることもできる。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stream_heartbeat.profile import load_app_state, save_app_state
from stream_heartbeat.render.heart_frames import (
    FRAME_FPS,
    ITEM_STYLES,
    frame_systole,
    render_frames,
    write_frames,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.vts import (
    CONNECTING,
    DENIED,
    ITEM_FOLDER,
    NO_VTS,
    OFF,
    PARAM_BEAT,
    PARAM_BPM,
    PARAM_INTERVAL_S,
    READY,
    WAITING_USER,
    VtsClient,
    VtsHeart,
    find_items_dir,
    item_framerate,
)

STATE_LABELS = {
    OFF: "つないでいません",
    CONNECTING: "VTube Studio につないでいます…",
    WAITING_USER: "VTube Studio に出た確認で「許可」を押してください",
    READY: "つながりました",
    NO_VTS: "VTube Studio が見つかりません（起動して、設定の「API を開始」をオンに）",
    DENIED: "VTube Studio で許可されませんでした。つなぐにはチェックを入れ直してください",
}
ITEM_BUTTON = "心臓をアイテムにして出す（作り直す）"
SHOWN_NOTICE = "VTube Studio に心臓を出しました。モデルの胸へ動かしてピン留めしてください"
HINT = (
    "出した心臓は VTube Studio 上でモデルの胸へ動かし、モデルにピン留めすると"
    "体と一緒に動きます。スタイルや向きを変えたら、もう一度ボタンを押してください。"
    f"パラメータ（{PARAM_BEAT}・{PARAM_BPM}）は、モデルの設定で好きな動きにつなげられます。"
)


class VtsPanel(QWidget):
    def __init__(
        self,
        session: HeartSession,
        data_dir: Path,
        notify: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._data_dir = data_dir
        self._notify = notify
        state = load_app_state(data_dir)
        token = state.get("vts_token")
        self._client = VtsClient(token=token if isinstance(token, str) else "")
        self._heart = VtsHeart(self._client)
        saved_dir = state.get("vts_items_dir")
        self._items_dir: Path | None = Path(saved_dir) if isinstance(saved_dir, str) else None
        self._last_origin: float | None = None
        self._last_param = -1.0
        self._pending_frames = 0

        self._enable = QCheckBox("VTube Studio とつなぐ")
        self._status = QLabel(STATE_LABELS[OFF])
        self._status.setObjectName("meta")
        self._status.setWordWrap(True)
        self._item_btn = QPushButton(ITEM_BUTTON)
        self._params = QCheckBox("拍と心拍数をパラメータで送る")
        self._folder = QLabel("")
        self._folder.setObjectName("meta")
        self._folder.setWordWrap(True)
        self._folder_btn = QPushButton("フォルダを選ぶ")
        hint = QLabel(HINT)
        hint.setObjectName("meta")
        hint.setWordWrap(True)

        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(self._folder_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._enable)
        layout.addWidget(self._status)
        layout.addWidget(self._item_btn)
        layout.addLayout(folder_row)
        layout.addWidget(self._params)
        layout.addWidget(hint)

        self._client.state_changed.connect(self._on_state)
        self._client.token_changed.connect(self._on_token)
        self._client.ready.connect(self._on_ready)
        self._enable.toggled.connect(self._on_enable)
        self._params.toggled.connect(self._save_flags)
        self._item_btn.clicked.connect(self._make_item)
        self._folder_btn.clicked.connect(self._choose_folder)

        self._params.setChecked(bool(state.get("vts_params", False)))
        self._show_folder()
        if state.get("vts_enabled"):
            self._enable.setChecked(True)

    # ------------------------------------------------------------ 状態

    def _on_state(self, state: str) -> None:
        self._status.setText(STATE_LABELS.get(state, state))
        if state == DENIED:
            self._enable.blockSignals(True)
            self._enable.setChecked(False)
            self._enable.blockSignals(False)

    def _on_token(self, token: str) -> None:
        self._save(vts_token=token or None)

    def _on_ready(self) -> None:
        if self._pending_frames:
            count = self._pending_frames
            self._pending_frames = 0
            self._heart.show_item(count, self._item_shown)

    def _on_enable(self, on: bool) -> None:
        self._save_flags()
        if on:
            self._client.start()
        else:
            self._client.stop()

    def _save_flags(self, _on: bool = False) -> None:
        self._save(vts_enabled=self._enable.isChecked(), vts_params=self._params.isChecked())

    def _save(self, **values: object) -> None:
        try:
            save_app_state(self._data_dir, **values)
        except OSError:
            pass

    # ------------------------------------------------------------ アイテム

    def _resolved_dir(self) -> Path | None:
        if self._items_dir is not None and self._items_dir.is_dir():
            return self._items_dir
        return find_items_dir()

    def _show_folder(self) -> None:
        folder = self._resolved_dir()
        if folder is None:
            self._folder.setText("VTube Studio の Items フォルダが見つかりません")
        else:
            self._folder.setText(f"書き出し先: {folder}")

    def _choose_folder(self) -> None:
        start = str(self._resolved_dir() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, "VTube Studio の Items フォルダ（StreamingAssets の中）", start
        )
        if not chosen:
            return
        self._items_dir = Path(chosen)
        self._save(vts_items_dir=chosen)
        self._show_folder()

    def _make_item(self) -> None:
        profile = self._session.profile
        if profile.style not in ITEM_STYLES:
            self._notify("アイテムにできるのはリアル・機械・レントゲン3・かわいいです")
            return
        folder = self._resolved_dir()
        if folder is None:
            self._choose_folder()
            folder = self._resolved_dir()
            if folder is None:
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            count = write_frames(render_frames(profile), folder / ITEM_FOLDER)
        except (OSError, RuntimeError):
            self._notify("アイテムの画像を書き出せませんでした（フォルダを確かめてください）")
            return
        finally:
            QApplication.restoreOverrideCursor()
        if self._client.state == READY:
            self._heart.show_item(count, self._item_shown)
            return
        self._pending_frames = count
        self._notify("アイテムの画像を書き出しました。VTube Studio につながると出します")

    def _item_shown(self, ok: bool) -> None:
        if ok:
            self._notify(SHOWN_NOTICE)
        else:
            self._notify(f"VTube Studio に出せませんでした（{self._heart.last_error}）")

    # ------------------------------------------------------------ 拍

    def tick(self, t: float) -> None:
        """操作画面のタイマーごと。拍が来たらアイテムを再生し、パラメータを送る。"""
        if self._client.state != READY:
            self._last_origin = None
            return
        clock = self._session.clock
        origin = clock.origin_before(t)
        if self._last_origin is None or origin < self._last_origin - 1.0:
            self._last_origin = origin
        elif origin > self._last_origin + 1e-3:
            self._last_origin = origin
            systole = min(0.34, max(0.20, clock.interval() * 0.36))
            self._heart.beat(item_framerate(FRAME_FPS, systole, frame_systole()))
        if self._params.isChecked() and t - self._last_param >= PARAM_INTERVAL_S:
            self._last_param = t
            cycle = clock.cycle(t)
            pulse = max(cycle.squeeze, cycle.eject * 0.55)
            self._heart.send_params(pulse, float(clock.bpm))

    def shutdown(self) -> None:
        self._client.stop()
