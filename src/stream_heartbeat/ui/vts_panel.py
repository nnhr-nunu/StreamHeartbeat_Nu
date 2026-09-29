"""操作画面の「⑤ VTube Studio 連携」欄。

心臓を VTube Studio のアイテムにして拍ごとに動かす（モデルに留めれば体と一緒に動く）。
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

from stream_heartbeat.profile import HeartProfile, load_app_state, save_app_state
from stream_heartbeat.render.heart_frames import (
    FRAME_FPS,
    ITEM_STYLES,
    count_frames,
    frame_systole,
    render_frames,
    write_frames,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.fold import make_fold
from stream_heartbeat.ui.forms import CenteredForm
from stream_heartbeat.ui.slider import labeled_slider
from stream_heartbeat.vts import (
    CONNECTING,
    DEFAULT_PORT,
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
    WAITING_USER: "VTube Studio の画面に出た確認で「許可」を押してください",
    READY: "VTube Studio とつながっています",
    NO_VTS: (
        "VTube Studio が見つかりません。起動しているか、設定で API がオンになっているかを"
        "確かめてください（5 秒ごとにつなぎ直します）"
    ),
    DENIED: "VTube Studio で許可されませんでした。つなぐときはもう一度チェックを入れてください",
}
# つなげないときは目立たせる
WARN_STATES = frozenset({NO_VTS, DENIED})
INTRO = (
    "心臓を VTube Studio のアイテムにして、モデルの胸に留めます。"
    "アバターが動いても心臓がずれず、拍に合わせて動きます。"
)
SHOW_BUTTON = "心臓を出す"
REMAKE_BUTTON = "作り直す（今の見た目で）"
HIDE_BUTTON = "しまう"
PIN_BUTTON = "モデルの胸に留める"
PICKING_BUTTON = "クリック待ち…（押すとやめる）"
ITEM_STYLE_NAMES = "リアル1〜3・レントゲン3・かわいい・機械"
NOTE_BAD_STYLE = f"今のスタイルはアイテムにできません。{ITEM_STYLE_NAMES}のどれかを選んでください"
NOTE_NOT_SHOWN = "心臓はまだ出していません。「心臓を出す」を押してください"
NOTE_STALE = "見た目を変えました。「作り直す」を押すと VTube Studio の心臓にも反映します"
NOTE_UNPINNED = "心臓を出しました。次は「モデルの胸に留める」で付ける場所を決めてください"
NOTE_PINNED = "心臓をモデルに留めています"
PICK_NOTICE = "VTube Studio で、モデルの心臓を置きたい所をクリックしてください"
PINNED_NOTICE = "モデルに留めました。次からは出すたびにここへ留めます"
NOT_ITEMS_NOTICE = (
    "Items フォルダを選んでください"
    "（VTube Studio のフォルダの中の VTube Studio_Data → StreamingAssets → Items）"
)
GUIDE = (
    "【はじめて使うとき】\n"
    "1. VTube Studio を起動し、設定（歯車）の最初のページにある、プラグインの API を"
    "始めるスイッチ（英語表示では Start API (allow Plugins)）をオンにする\n"
    "2. 上の「VTube Studio とつなぐ」にチェックを入れ、VTube Studio の画面に出た確認で"
    "「許可」（Allow）を押す（次からは聞かれません）\n"
    f"3. 「{SHOW_BUTTON}」を押す（VTube Studio の画面に心臓が出ます）\n"
    f"4. 「{PIN_BUTTON}」を押し、VTube Studio でモデルの胸をクリックする\n"
    "5. 「大きさ」で合わせる\n"
    "\n"
    "【ふだん】\n"
    "・留めた場所と大きさはモデルごとに覚えます。次からはつなぐだけで同じ所に心臓が出ます\n"
    "・スタイルや向きを変えたら「作り直す」を押すと反映します\n"
    f"・「{HIDE_BUTTON}」を押すと心臓を消し、次につないでも出しません\n"
    "\n"
    "【うまくいかないとき】\n"
    f"・つながらない: VTube Studio の API がオンか、ポートが {DEFAULT_PORT} のままかを確かめる\n"
    "・心臓が出ない: 下の書き出し先が VTube Studio の Items フォルダか確かめる"
    "（Steam 以外で入れたときは「フォルダを選ぶ」で選び直す）\n"
    f"・VTube Studio 側で心臓を消した: 「{SHOW_BUTTON}」をもう一度押す\n"
    "\n"
    "【パラメータ（モデルを拍で動かしたい人向け）】\n"
    f"オンにすると {PARAM_BEAT}（拍の瞬間に 1）と {PARAM_BPM}（心拍数）を送ります。"
    "VTube Studio のモデル設定で入力に選ぶと、拍に合わせて体を動かせます。"
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


def look_key(profile: HeartProfile) -> tuple:
    """アイテムの絵を決める見た目（スタイル・種類・向き）。変わったら作り直しを促す。"""
    angle = () if profile.style == "cute" else (
        round(profile.heart_yaw_deg), round(profile.heart_pitch_deg)
    )
    return (profile.style, profile.realistic_look, *angle)


def _set_kind(label: QLabel, kind: str) -> None:
    """文の色分け（meta: ふつう / warn: 目立たせる）を切り替える。"""
    if label.objectName() != kind:
        label.setObjectName(kind)
        label.style().unpolish(label)
        label.style().polish(label)


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
        # このとき書き出した絵の見た目（起動し直した後は分からないので None）
        self._made_key: tuple | None = None
        self._view: tuple | None = None
        self._last_origin: float | None = None
        self._last_param = -1.0

        intro = QLabel(INTRO)
        intro.setObjectName("meta")
        intro.setWordWrap(True)
        self._enable = QCheckBox("VTube Studio とつなぐ")
        self._status = QLabel(STATE_LABELS[OFF])
        self._status.setObjectName("meta")
        self._status.setWordWrap(True)
        self._status.hide()
        self._note = QLabel("")
        self._note.setObjectName("meta")
        self._note.setWordWrap(True)
        self._note.hide()
        self._item_btn = QPushButton(SHOW_BUTTON)
        self._hide_btn = QPushButton(HIDE_BUTTON)
        self._pin_btn = QPushButton(PIN_BUTTON)
        self._pin_btn.setToolTip(
            "押したあと、VTube Studio でモデルの心臓を置きたい所をクリックします"
        )
        self._size, size_row = labeled_slider(
            round(ITEM_SIZE_MIN * 100), round(ITEM_SIZE_MAX * 100), "小さく", "大きく"
        )
        self._size.setValue(round(self._heart.size * 100))
        self._params = QCheckBox("拍と心拍数をパラメータでも送る（モデルを拍で動かしたい人向け）")
        self._folder = QLabel("")
        self._folder.setObjectName("meta")
        self._folder.setWordWrap(True)
        self._folder_btn = QPushButton("フォルダを選ぶ")
        guide = QLabel(GUIDE)
        guide.setObjectName("meta")
        guide.setWordWrap(True)

        item_row = QHBoxLayout()
        item_row.addWidget(self._item_btn, 1)
        item_row.addWidget(self._hide_btn)
        size_form = CenteredForm()
        size_form.addRow("大きさ", size_row)
        self._details = QWidget()
        details = QVBoxLayout(self._details)
        details.setContentsMargins(0, 0, 0, 0)
        details.addWidget(self._note)
        details.addLayout(item_row)
        details.addWidget(self._pin_btn)
        details.addLayout(size_form)
        details.addWidget(self._params)
        self._details.hide()

        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(self._folder_btn)
        guide_inner = QWidget()
        guide_col = QVBoxLayout(guide_inner)
        guide_col.setContentsMargins(0, 0, 0, 0)
        guide_col.addWidget(guide)
        guide_col.addLayout(folder_row)
        guide_wrap, _guide_fold = make_fold("使い方・うまくいかないとき", guide_inner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(intro)
        layout.addWidget(self._enable)
        layout.addWidget(self._status)
        layout.addWidget(self._details)
        layout.addWidget(guide_wrap)

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
        self._refresh()
        if state.get("vts_enabled"):
            self._enable.setChecked(True)

    # ------------------------------------------------------------ 状態

    def _on_state(self, state: str) -> None:
        self._status.setText(STATE_LABELS.get(state, state))
        self._status.setVisible(state != OFF)
        _set_kind(self._status, "warn" if state in WARN_STATES else "meta")
        if state == DENIED:
            # チェックを外し、次に起動したときも勝手に聞き直さない
            self._enable.blockSignals(True)
            self._enable.setChecked(False)
            self._enable.blockSignals(False)
            self._details.hide()
            self._save_flags()
        self._refresh()

    def _refresh(self) -> None:
        """ボタンの使える・使えないと、心臓の様子の一文を今の状態に合わせる（変わったときだけ）。"""
        ready = self._client.state == READY
        profile = self._session.profile
        can_item = profile.style in ITEM_STYLES
        shown = self._heart.instance_id is not None
        picking = self._heart.picking
        if not ready:
            note, warn = "", False
        elif not can_item:
            note, warn = NOTE_BAD_STYLE, True
        elif not shown:
            note, warn = NOTE_NOT_SHOWN, False
        elif self._made_key is not None and self._made_key != look_key(profile):
            note, warn = NOTE_STALE, True
        elif self._heart.model_id in self._heart.pins:
            note, warn = NOTE_PINNED, False
        else:
            note, warn = NOTE_UNPINNED, False
        view = (ready, can_item, shown, picking, note, warn)
        if view == self._view:
            return
        self._view = view
        self._item_btn.setText(REMAKE_BUTTON if shown else SHOW_BUTTON)
        self._item_btn.setEnabled(ready and can_item)
        self._hide_btn.setEnabled(ready and shown)
        self._pin_btn.setEnabled(ready and shown)
        self._pin_btn.setText(PICKING_BUTTON if picking else PIN_BUTTON)
        self._note.setText(note)
        self._note.setVisible(bool(note))
        _set_kind(self._note, "warn" if warn else "meta")

    def _on_token(self, token: str) -> None:
        self._save(vts_token=token or None)

    def _on_found(self, found: bool) -> None:
        """つないだ直後。前に出していて場に無ければ、書き出してあるコマで出し直す。"""
        if not found and self._auto_show:
            folder = self._resolved_dir()
            count = count_frames(folder / ITEM_FOLDER) if folder is not None else 0
            if count > 0:
                self._heart.show_item(count)
        self._refresh()

    def _on_enable(self, on: bool) -> None:
        self._details.setVisible(on)
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
            self._folder.setText("書き出し先: VTube Studio の Items フォルダが見つかりません")
        else:
            self._folder.setText(f"書き出し先: {folder}")

    def _choose_folder(self) -> None:
        start = str(self._resolved_dir() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, "VTube Studio の Items フォルダ（StreamingAssets の中）", start
        )
        if not chosen:
            return
        folder = Path(chosen)
        # 一つ上（StreamingAssets）を選んだときは中の Items を使う
        if folder.name.lower() != "items" and (folder / "Items").is_dir():
            folder = folder / "Items"
        if folder.name.lower() != "items":
            self._notify(NOT_ITEMS_NOTICE)
            return
        self._items_dir = folder
        self._save(vts_items_dir=str(folder))
        self._show_folder()

    def _make_item(self) -> None:
        profile = self._session.profile
        if profile.style not in ITEM_STYLES:
            self._notify(NOTE_BAD_STYLE)
            return
        if self._client.state != READY:
            self._notify("VTube Studio につながってから押してください")
            return
        folder = self._resolved_dir()
        if folder is None:
            self._notify(NOT_ITEMS_NOTICE)
            self._choose_folder()
            folder = self._resolved_dir()
            if folder is None:
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            count = write_frames(render_frames(profile), folder / ITEM_FOLDER)
        except (OSError, RuntimeError):
            self._notify("アイテムの画像を書き出せませんでした（書き出し先のフォルダを確かめてください）")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._made_key = look_key(profile)
        self._heart.show_item(count, self._item_shown)

    def _item_shown(self, ok: bool) -> None:
        if ok:
            self._auto_show = True
            self._save(vts_item_shown=True)
            pinned = self._heart.model_id in self._heart.pins
            self._notify(
                "VTube Studio に心臓を出し、覚えている場所に留めました"
                if pinned
                else "VTube Studio に心臓を出しました。次は「モデルの胸に留める」を押してください"
            )
        else:
            self._notify(f"VTube Studio に出せませんでした（{self._heart.last_error}）")
        self._refresh()

    def _hide_item(self) -> None:
        self._auto_show = False
        self._save(vts_item_shown=False)
        if self._client.state == READY:
            self._heart.hide_item()
        self._refresh()

    # ------------------------------------------------------------ 留める・大きさ

    def _toggle_pick(self) -> None:
        if self._heart.picking:
            self._heart.cancel_pick()
        elif self._client.state != READY:
            self._notify("VTube Studio につながってから押してください")
        elif not self._heart.start_pick(self._picked):
            self._notify(f"先に「{SHOW_BUTTON}」で VTube Studio に心臓を出してください")
        else:
            self._notify(PICK_NOTICE)
        self._refresh()

    def _picked(self, pin: dict | None) -> None:
        if pin is None:
            self._notify(f"モデルに留められませんでした（{self._heart.last_error}）")
        else:
            self._save(vts_pins=self._heart.pins)
            self._notify(PINNED_NOTICE)
        self._refresh()

    def _on_size(self, value: int) -> None:
        self._heart.set_size(value / 100.0)
        if not self._size.isSliderDown():
            self._save_size()

    def _save_size(self) -> None:
        self._save(vts_item_size=self._heart.size)

    # ------------------------------------------------------------ 拍

    def tick(self, t: float) -> None:
        """操作画面のタイマーごと。拍が来たらアイテムを再生し、パラメータを送る。"""
        self._refresh()
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
