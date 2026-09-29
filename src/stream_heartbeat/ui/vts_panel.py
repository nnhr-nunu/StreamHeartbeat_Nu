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
    count_frames,
    frame_systole,
    render_frames,
    write_frames,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.slider import labeled_slider
from stream_heartbeat.vts import (
    CONNECTING,
    DENIED,
    ITEM_FOLDER,
    ITEM_SIZE,
    ITEM_SIZE_MAX,
    ITEM_SIZE_MIN,
    NO_VTS,
    OFF,
    PARAM_BEAT,
    PARAM_BPM,
    PARAM_INTERVAL_S,
    READY,
    WAITING_USER,
    VtsClient,
    VtsHeart,
    clean_pin,
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
HIDE_BUTTON = "しまう"
PIN_BUTTON = "モデルに留める"
PICKING_BUTTON = "クリック待ち（押すとやめる）"
SHOWN_NOTICE = "VTube Studio に心臓を出しました。「モデルに留める」で胸に留められます"
PICK_NOTICE = "VTube Studio で、モデルの心臓を置きたい所をクリックしてください"
PINNED_NOTICE = "モデルに留めました。次からは出すたびにここへ留めます"
STEPS = (
    "【つなぎ方】\n"
    "1. VTube Studio を起動し、設定の「API を開始」をオンにする\n"
    "2. 下の「VTube Studio とつなぐ」にチェックを入れ、VTube Studio に出た確認で「許可」を押す\n"
    "3. 「心臓をアイテムにして出す」を押す（書き出し先が見つからないときは"
    "「フォルダを選ぶ」で VTube Studio の StreamingAssets の中の Items を選ぶ）\n"
    "4. 「モデルに留める」を押し、VTube Studio でモデルの胸をクリックする\n"
    "5. 「心臓の大きさ」で大きさを合わせる"
)
HINT = (
    "・留めた場所と大きさはモデルごとに覚えて、次からは出すたびに留め直します。\n"
    "・アイテムにできるスタイルはリアル・機械・レントゲン3・かわいいです。"
    "スタイルや向きを変えたら、もう一度「出す」を押してください。\n"
    f"・パラメータ（{PARAM_BEAT}・{PARAM_BPM}）は、モデルの設定で好きな動きにつなげられます。"
)


def _saved_pins(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    pins = {}
    for model, pin in raw.items():
        cleaned = clean_pin(pin)
        if cleaned is not None and cleaned["modelID"] == model:
            pins[model] = cleaned
    return pins


def _saved_size(raw: object) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(ITEM_SIZE_MIN, min(ITEM_SIZE_MAX, float(raw)))
    return ITEM_SIZE


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
        self._heart = VtsHeart(
            self._client,
            size=_saved_size(state.get("vts_item_size")),
            pins=_saved_pins(state.get("vts_pins")),
        )
        self._heart.on_found = self._on_found
        saved_dir = state.get("vts_items_dir")
        self._items_dir: Path | None = Path(saved_dir) if isinstance(saved_dir, str) else None
        # 前に出していたら、つないだとき場に無ければ出し直す（VTube Studio を起動し直したときなど）
        self._auto_show = bool(state.get("vts_item_shown", False))
        self._last_origin: float | None = None
        self._last_param = -1.0
        self._pending_frames = 0

        self._enable = QCheckBox("VTube Studio とつなぐ")
        self._status = QLabel(STATE_LABELS[OFF])
        self._status.setObjectName("meta")
        self._status.setWordWrap(True)
        self._item_btn = QPushButton(ITEM_BUTTON)
        self._hide_btn = QPushButton(HIDE_BUTTON)
        self._pin_btn = QPushButton(PIN_BUTTON)
        self._size, size_row = labeled_slider(
            round(ITEM_SIZE_MIN * 100), round(ITEM_SIZE_MAX * 100), "小さく", "大きく"
        )
        self._size.setValue(round(self._heart.size * 100))
        self._params = QCheckBox("拍と心拍数をパラメータで送る")
        self._folder = QLabel("")
        self._folder.setObjectName("meta")
        self._folder.setWordWrap(True)
        self._folder_btn = QPushButton("フォルダを選ぶ")
        steps = QLabel(STEPS)
        steps.setObjectName("meta")
        steps.setWordWrap(True)
        hint = QLabel(HINT)
        hint.setObjectName("meta")
        hint.setWordWrap(True)

        item_row = QHBoxLayout()
        item_row.addWidget(self._item_btn, 1)
        item_row.addWidget(self._hide_btn)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(self._folder_btn)
        size_label = QLabel("心臓の大きさ")
        size_label.setObjectName("meta")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(steps)
        layout.addWidget(self._enable)
        layout.addWidget(self._status)
        layout.addLayout(item_row)
        layout.addWidget(self._pin_btn)
        layout.addWidget(size_label)
        layout.addWidget(size_row)
        layout.addLayout(folder_row)
        layout.addWidget(self._params)
        layout.addWidget(hint)

        self._client.state_changed.connect(self._on_state)
        self._client.token_changed.connect(self._on_token)
        self._enable.toggled.connect(self._on_enable)
        self._params.toggled.connect(self._save_flags)
        self._item_btn.clicked.connect(self._make_item)
        self._hide_btn.clicked.connect(self._hide_item)
        self._pin_btn.clicked.connect(self._toggle_pick)
        self._size.valueChanged.connect(self._on_size)
        self._size.sliderReleased.connect(self._save_size)
        self._folder_btn.clicked.connect(self._choose_folder)

        self._params.setChecked(bool(state.get("vts_params", False)))
        self._show_folder()
        if state.get("vts_enabled"):
            self._enable.setChecked(True)

    # ------------------------------------------------------------ 状態

    def _on_state(self, state: str) -> None:
        self._status.setText(STATE_LABELS.get(state, state))
        self._pin_btn.setText(PIN_BUTTON)
        if state == DENIED:
            self._enable.blockSignals(True)
            self._enable.setChecked(False)
            self._enable.blockSignals(False)

    def _on_token(self, token: str) -> None:
        self._save(vts_token=token or None)

    def _on_found(self, found: bool) -> None:
        """つないだ直後。書き出し待ちのコマがあれば出し、前に出していて場に無ければ出し直す。"""
        if self._pending_frames:
            count = self._pending_frames
            self._pending_frames = 0
            self._heart.show_item(count, self._item_shown)
            return
        if found or not self._auto_show:
            return
        folder = self._resolved_dir()
        count = count_frames(folder / ITEM_FOLDER) if folder is not None else 0
        if count > 0:
            self._heart.show_item(count)

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
            self._auto_show = True
            self._save(vts_item_shown=True)
            self._pin_btn.setText(PIN_BUTTON)
            pinned = self._heart.model_id in self._heart.pins
            self._notify("VTube Studio に心臓を出しました" if pinned else SHOWN_NOTICE)
        else:
            self._notify(f"VTube Studio に出せませんでした（{self._heart.last_error}）")

    def _hide_item(self) -> None:
        self._auto_show = False
        self._save(vts_item_shown=False)
        self._pending_frames = 0
        self._pin_btn.setText(PIN_BUTTON)
        if self._client.state == READY:
            self._heart.hide_item()

    # ------------------------------------------------------------ 留める・大きさ

    def _toggle_pick(self) -> None:
        if self._heart.picking:
            self._heart.cancel_pick()
            self._pin_btn.setText(PIN_BUTTON)
            return
        if self._client.state != READY:
            self._notify("VTube Studio につながってから押してください")
            return
        if not self._heart.start_pick(self._picked):
            self._notify("先に「出す」で VTube Studio に心臓を出してください")
            return
        self._pin_btn.setText(PICKING_BUTTON)
        self._notify(PICK_NOTICE)

    def _picked(self, pin: dict | None) -> None:
        self._pin_btn.setText(PIN_BUTTON)
        if pin is None:
            self._notify(f"モデルに留められませんでした（{self._heart.last_error}）")
            return
        self._save(vts_pins=self._heart.pins)
        self._notify(PINNED_NOTICE)

    def _on_size(self, value: int) -> None:
        self._heart.set_size(value / 100.0)
        if not self._size.isSliderDown():
            self._save_size()

    def _save_size(self) -> None:
        self._save(vts_item_size=self._heart.size)

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
