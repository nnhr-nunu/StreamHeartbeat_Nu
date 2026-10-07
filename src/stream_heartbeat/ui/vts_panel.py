"""操作画面の「⑤ VTube Studio 連携」欄。

心臓を VTube Studio のアイテムにして拍ごとに動かす（モデルに留めれば体と一緒に動く）。
拍と心拍数をカスタムパラメータとして送ることもできる。
"""

from __future__ import annotations

import time
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

from stream_heartbeat.i18n import tr
from stream_heartbeat.profile import HeartProfile, load_app_state, save_app_state
from stream_heartbeat.render.heart_frames import (
    FLAT_ITEM_STYLES,
    FRAME_FPS,
    ITEM_STYLES,
    count_frames,
    frame_systole,
    item_effect,
    item_text,
    render_frames,
    squeeze_frame_count,
    write_frames,
)
from stream_heartbeat.session import HeartSession
from stream_heartbeat.ui.effects import GRIP_EFFECTS, STETHO_EFFECTS
from stream_heartbeat.ui.fold import make_fold_row
from stream_heartbeat.ui.forms import CenteredForm
from stream_heartbeat.ui.slider import labeled_slider
from stream_heartbeat.ui.style_catalog import STYLES, chosen_material
from stream_heartbeat.ui.vts_bpm_control import VtsBpmControl
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
    clean_place,
    find_items_dir,
    item_framerate,
)
from stream_heartbeat.vts_bpm import BPM_FOLDER
from stream_heartbeat.vts_text import (
    API_SWITCH,
    BPM_CHECK,
    HIDE_BUTTON,
    HOW_TO_LINES,
    INTRO,
    LABEL_CONNECTING,
    LABEL_DENIED,
    LABEL_NO_VTS,
    LABEL_OFF,
    LABEL_READY,
    LABEL_WAITING_USER,
    NOT_ITEMS_NOTICE,
    NOTE_STALE,
    PARAMS_CHECK,
    PICK_NOTICE,
    PICKING_BUTTON,
    PIN_BUTTON,
    PINNED_NOTICE,
    REMADE_NOTICE,
    REMAKE_BUTTON,
    SHOW_BUTTON,
    SIZE_LABEL,
    T_BAD_STYLE,
    T_HAND_PLACED,
    T_HAND_PLACED_NOTICE,
    T_HAND_REMADE_NOTICE,
    T_NOT_SHOWN,
    T_PICKING,
    T_PINNED,
    T_STALE_FAILED,
    T_UNPINNED,
    TEXT_CHECK,
    TROUBLE_LINES,
)

STATE_LABELS = {
    OFF: LABEL_OFF,
    CONNECTING: LABEL_CONNECTING,
    WAITING_USER: LABEL_WAITING_USER,
    READY: LABEL_READY,
    NO_VTS: LABEL_NO_VTS,
    DENIED: LABEL_DENIED,
}
# つなげないときは目立たせる
WARN_STATES = frozenset({NO_VTS, DENIED})
# 見た目を変えてから VTube Studio の心臓を作り直すまで待つ秒（続けて変えている間は待つ）
REMAKE_WAIT_S = 0.8


def style_names(keys: frozenset[str], *, translated: bool = True) -> str:
    """スタイルの一覧から、keys に入るものの表示名を短くまとめる（例: リアル1〜3、機械）。

    手で書くとスタイルを足したときに古くなるので、一覧から作る。translated が偽なら、
    表示言語に関わらず日本語で作る（テストや案内文の原文に使う）。
    """
    say = tr if translated else _plain
    groups: dict[str, list[str]] = {}
    for key, _look, label in STYLES:
        if key in keys:
            base = label.rstrip("0123456789")
            groups.setdefault(base, []).append(label[len(base) :])
    parts = []
    for base, nums in groups.items():
        # 表示名の数字より前が、その言語での名前（英語は Realistic、日本語は リアル）
        name = say(base + nums[0]).rstrip("0123456789 ")
        if not nums[0]:
            parts.append(say(base))
        elif len(nums) == 1:
            parts.append(say("{name}{a}", name=name, a=nums[0]))
        elif len(nums) == 2:
            parts.append(say("{name}{a}・{b}", name=name, a=nums[0], b=nums[1]))
        else:
            parts.append(say("{name}{a}〜{b}", name=name, a=nums[0], b=nums[-1]))
    return say("、").join(parts)


def _plain(text: str, **fmt: object) -> str:
    """翻訳しない tr（日本語の原文を作るとき）。"""
    return text.format(**fmt) if fmt else text


def _say(template: str, **names: object) -> str:
    """ひな形を今の言語で組む。値のうち文字（ボタン名など）は、それぞれ訳してから入れる。"""
    return tr(template, **{k: tr(v) if isinstance(v, str) else v for k, v in names.items()})


def state_label(state: str) -> str:
    template = STATE_LABELS.get(state)
    return state if template is None else _say(template, switch=API_SWITCH)


ITEM_STYLE_NAMES = style_names(ITEM_STYLES, translated=False)
def _guide_names() -> dict[str, object]:
    return {
        "switch": API_SWITCH,
        "port": DEFAULT_PORT,
        "show": SHOW_BUTTON,
        "pin": PIN_BUTTON,
        "hide": HIDE_BUTTON,
        "remake": REMAKE_BUTTON,
        "size": SIZE_LABEL,
        "params": PARAMS_CHECK,
        "words": TEXT_CHECK,
        "bpm_check": BPM_CHECK,
        "beat": PARAM_BEAT,
        "bpm": PARAM_BPM,
    }


def _guide(lines: tuple[str, ...], names: str) -> str:
    return "\n".join(_say(line, names=names, **_guide_names()) if line else "" for line in lines)


def how_to_text() -> str:
    return _guide(HOW_TO_LINES, style_names(ITEM_STYLES))


def trouble_text() -> str:
    return _guide(TROUBLE_LINES, "")


# 日本語の原文（案内文は表示言語に関わらずこの形）。テストが画面の文と突き合わせる
NOTE_BAD_STYLE = T_BAD_STYLE.format(names=ITEM_STYLE_NAMES)
NOTE_NOT_SHOWN = T_NOT_SHOWN.format(show=SHOW_BUTTON)
NOTE_STALE_FAILED = T_STALE_FAILED.format(remake=REMAKE_BUTTON)
NOTE_UNPINNED = T_UNPINNED.format(pin=PIN_BUTTON)
NOTE_PINNED = T_PINNED.format(size=SIZE_LABEL)
NOTE_PICKING = T_PICKING.format(pick=PICK_NOTICE)
HOW_TO = "\n".join(
    line.format(names=ITEM_STYLE_NAMES, **_guide_names()) for line in HOW_TO_LINES
)
TROUBLE = "\n".join(line.format(**_guide_names()) for line in TROUBLE_LINES)


def _saved_pins(raw: object) -> dict[str, dict]:
    if not isinstance(raw, dict):
        return {}
    pins = {}
    for model, pin in raw.items():
        cleaned = clean_pin(pin)
        if cleaned is not None and cleaned["modelID"] == model:
            pins[model] = cleaned
    return pins


def _saved_count(raw: object) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else 0


def _saved_size(raw: object) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(ITEM_SIZE_MIN, min(ITEM_SIZE_MAX, float(raw)))
    return ITEM_SIZE


def look_key(
    profile: HeartProfile, stetho: tuple[float, float] = (0.0, 0.0), text: bool = False
) -> tuple:
    """アイテムの絵を決める見た目（スタイル・種類・材質・向き・演出・拍の文字）。変わったら作り直す。

    stetho は聴診器を当てる所、text は拍の文字も描くか（render_frames と同じ）。
    保存できるよう、文字と数だけで作る。
    """
    effect = item_effect(profile)
    # 2D の絵と、手で掴んでいる間（正面から見る）は向きが無い
    front = profile.style in FLAT_ITEM_STYLES or effect in GRIP_EFFECTS
    angle = () if front else (round(profile.heart_yaw_deg), round(profile.heart_pitch_deg))
    place = (round(stetho[0], 1), round(stetho[1], 1)) if effect in STETHO_EFFECTS else ()
    material = chosen_material(profile)
    materials = (material,) if material else ()
    word = item_text(profile) if text else None
    # 文字は心臓に対する置き場所・大きさ（窓の心臓の大きさでも変わる）を数で持つ
    words = (
        ("text", word.text, round(word.dx), round(word.dy), word.font_px, round(word.angle),
         round(word.opacity, 2), word.color, word.outline)
        if word is not None
        else ()
    )  # fmt: skip
    # 心臓わしづかみは「ぎゅっ」のコマの数も入れる（コマを足す前の版で書き出した絵は作り直す）
    squeeze = squeeze_frame_count(profile)
    frames = ("squeeze", squeeze) if squeeze else ()
    return (
        profile.style, profile.realistic_look, *materials, *angle, effect, *place, *words, *frames
    )


def _saved_look(raw: object) -> tuple | None:
    return tuple(raw) if isinstance(raw, list) else None


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
        stetho_offset: Callable[[], tuple[float, float]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """stetho_offset は配信用の窓に置いてある聴診器の所（render_frames の stetho）を返す。"""
        super().__init__(parent)
        self._session = session
        self._data_dir = data_dir
        self._notify = notify
        self._stetho_offset = stetho_offset or (lambda: (0.0, 0.0))
        state = load_app_state(data_dir)
        token = state.get("vts_token")
        self._client = VtsClient(token=token if isinstance(token, str) else "")
        self._heart = VtsHeart(
            self._client,
            size=_saved_size(state.get("vts_item_size")),
            pins=_saved_pins(state.get("vts_pins")),
            place=clean_place(state.get("vts_item_place")),
            squeeze_frames=_saved_count(state.get("vts_item_squeeze")),
            hand_placed=state.get("vts_hand_placed") is True,
        )
        self._heart.on_found = self._on_found
        self._heart.on_moved = self._on_moved
        # 心拍数の数字のアイテム。VTube Studio の知らせは心臓がまとめて受けて渡す
        self._bpm = VtsBpmControl(
            self._client,
            lambda: self._session.profile,
            state,
            self._heart.size,
            self._resolved_dir,
            self._save,
            notify,
            self._choose_folder,
        )
        self._heart.item_files.append(BPM_FOLDER)
        self._heart.other_item_event = self._bpm.bpm.on_item_event
        saved_dir = state.get("vts_items_dir")
        self._items_dir: Path | None = Path(saved_dir) if isinstance(saved_dir, str) else None
        # 前に出していたら、つないだとき場に無ければ出し直す（VTube Studio を起動し直したときなど）
        self._auto_show = bool(state.get("vts_item_shown", False))
        # 書き出してある絵の見た目（look_key。分からなければ None）
        self._made_key = _saved_look(state.get("vts_item_look"))
        # 作り直して出し終えるまで真。作り直しを待っている見た目と、待ち始めた時刻
        self._busy = False
        self._pending: tuple[tuple, float] | None = None
        # 自動の作り直しに失敗した見た目（同じ見た目では試し直さない）
        self._failed_key: tuple | None = None
        self._view: tuple | None = None
        self._last_origin: float | None = None
        self._last_param = -1.0

        intro = QLabel(INTRO)
        intro.setObjectName("meta")
        intro.setWordWrap(True)
        self._enable = QCheckBox("VTube Studio とつなぐ")
        self._status = QLabel(state_label(OFF))
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
            "押したあと、VTube Studio の画面でモデルの心臓を付けたい所を左クリックします"
        )
        self._size, size_row = labeled_slider(
            round(ITEM_SIZE_MIN * 100), round(ITEM_SIZE_MAX * 100), "小さく", "大きく"
        )
        self._size.setValue(round(self._heart.size * 100))
        self._text = QCheckBox(TEXT_CHECK)
        self._text.setToolTip(
            "配信用の窓の拍の文字（❤ やドクンなど）を、VTube Studio の心臓にも同じ所に出します。"
            "文字・大きさ・色は「③ 同期文字」の設定のとおりです"
        )
        self._params = QCheckBox(PARAMS_CHECK)
        self._folder = QLabel("")
        self._folder.setObjectName("meta")
        self._folder.setWordWrap(True)
        self._folder_btn = QPushButton("フォルダを選ぶ")
        self._how_to = QLabel(how_to_text())
        self._how_to.setObjectName("guide")
        self._how_to.setWordWrap(True)
        self._trouble = QLabel(trouble_text())
        self._trouble.setObjectName("guide")
        self._trouble.setWordWrap(True)

        item_row = QHBoxLayout()
        item_row.addWidget(self._item_btn, 1)
        item_row.addWidget(self._hide_btn)
        size_form = CenteredForm()
        size_form.addRow(SIZE_LABEL, size_row)
        self._details = QWidget()
        details = QVBoxLayout(self._details)
        details.setContentsMargins(0, 0, 0, 0)
        details.addWidget(self._note)
        details.addLayout(item_row)
        details.addWidget(self._pin_btn)
        details.addLayout(size_form)
        details.addWidget(self._text)
        details.addWidget(self._bpm.check)
        details.addWidget(self._bpm.note)
        details.addWidget(self._params)
        self._details.hide()

        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(self._folder_btn)
        trouble_inner = QWidget()
        trouble_col = QVBoxLayout(trouble_inner)
        trouble_col.setContentsMargins(0, 0, 0, 0)
        trouble_col.addWidget(self._trouble)
        trouble_col.addLayout(folder_row)
        guide_wrap, _guide_folds = make_fold_row(
            [("使い方", self._how_to), ("上手くいかない時", trouble_inner)]
        )

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
        self._text.toggled.connect(self._save_flags)
        self._item_btn.clicked.connect(self._make_item)
        self._hide_btn.clicked.connect(self._hide_item)
        self._pin_btn.clicked.connect(self._toggle_pick)
        self._size.valueChanged.connect(self._on_size)
        self._size.sliderReleased.connect(self._save_size)
        self._folder_btn.clicked.connect(self._choose_folder)

        self._params.setChecked(bool(state.get("vts_params", False)))
        self._text.blockSignals(True)
        self._text.setChecked(bool(state.get("vts_beat_text", True)))
        self._text.blockSignals(False)
        self._show_folder()
        self._refresh()
        if state.get("vts_enabled"):
            self._enable.setChecked(True)

    def retranslate(self) -> None:
        """表示言語が変わったとき、実行中に組み立てた文を作り直す（静的な部品は走査が付け替える）。"""
        self._how_to.setText(how_to_text())
        self._trouble.setText(trouble_text())
        self._status.setText(state_label(self._client.state))
        self._show_folder()
        self._view = None
        self._refresh()

    # ------------------------------------------------------------ 状態

    def _on_state(self, state: str) -> None:
        if state != READY:
            # 切れると出し終えた知らせは来ない
            self._busy = False
            self._pending = None
        self._status.setText(state_label(state))
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
        key = self._look_key()
        if not ready:
            note, warn = "", False
        elif picking:
            note, warn = _say(T_PICKING, pick=PICK_NOTICE), True
        elif not can_item:
            note, warn = _say(T_BAD_STYLE, names=style_names(ITEM_STYLES)), True
        elif not shown:
            note, warn = _say(T_NOT_SHOWN, show=SHOW_BUTTON), False
        elif key != self._made_key:
            failed = key == self._failed_key
            if failed:
                note, warn = _say(T_STALE_FAILED, remake=REMAKE_BUTTON), True
            else:
                note, warn = tr(NOTE_STALE), False
        elif self._heart.hand_placed:
            note, warn = _say(T_HAND_PLACED, pin=PIN_BUTTON), True
        elif self._heart.model_id in self._heart.pins:
            note, warn = _say(T_PINNED, size=SIZE_LABEL), False
        else:
            note, warn = _say(T_UNPINNED, pin=PIN_BUTTON), False
        self._bpm.refresh()
        view = (ready, can_item, shown, picking, note, warn)
        if view == self._view:
            return
        self._view = view
        self._item_btn.setText(tr(REMAKE_BUTTON if shown else SHOW_BUTTON))
        self._item_btn.setEnabled(ready and can_item)
        self._hide_btn.setEnabled(ready and shown)
        self._pin_btn.setEnabled(ready and shown)
        self._pin_btn.setText(tr(PICKING_BUTTON if picking else PIN_BUTTON))
        self._note.setText(note)
        self._note.setVisible(bool(note))
        _set_kind(self._note, "warn" if warn else "meta")

    def _on_token(self, token: str) -> None:
        self._save(vts_token=token or None)

    def _on_found(self, found: bool) -> None:
        """つないだ直後。前に出していて場に無ければ出し直す。

        書き出してあるコマが今の見た目と違えば、今の見た目で作り直して出す。
        """
        if not found and self._auto_show:
            can_item = self._session.profile.style in ITEM_STYLES
            if can_item and self._made_key != self._look_key():
                self._make_item(auto=True)
            else:
                folder = self._resolved_dir()
                count = count_frames(folder / ITEM_FOLDER) if folder is not None else 0
                if count > 0:
                    self._heart.show_item(count, squeeze_frames=self._heart.squeeze_frames)
        self._refresh()

    def _on_enable(self, on: bool) -> None:
        self._details.setVisible(on)
        self._save_flags()
        if on:
            self._client.start()
        else:
            self._client.stop()

    def _save_flags(self, _on: bool = False) -> None:
        self._save(
            vts_enabled=self._enable.isChecked(),
            vts_params=self._params.isChecked(),
            vts_beat_text=self._text.isChecked(),
        )

    def _on_moved(self) -> None:
        """VTube Studio の画面で心臓を置き直した。次に出すときも同じ所に出すよう覚えておく。"""
        place = self._heart.place
        hand = self._heart.hand_placed
        self._save(
            vts_pins=self._heart.pins,
            vts_item_place=list(place) if place else None,
            vts_hand_placed=hand,
        )
        if hand:
            self._notify(_say(T_HAND_PLACED_NOTICE, pin=PIN_BUTTON))
        self._refresh()

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
            self._folder.setText(tr("書き出し先: VTube Studio の Items フォルダが見つかりません"))
        else:
            self._folder.setText(tr("書き出し先: {folder}", folder=folder))

    def _choose_folder(self) -> None:
        start = str(self._resolved_dir() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, tr("VTube Studio の Items フォルダ（StreamingAssets の中）"), start
        )
        if not chosen:
            return
        folder = Path(chosen)
        # 一つ上（StreamingAssets）を選んだときは中の Items を使う
        if folder.name.lower() != "items" and (folder / "Items").is_dir():
            folder = folder / "Items"
        if folder.name.lower() != "items":
            self._notify(tr(NOT_ITEMS_NOTICE))
            return
        self._items_dir = folder
        self._save(vts_items_dir=str(folder))
        self._show_folder()

    def _look_key(self) -> tuple:
        return look_key(self._session.profile, self._stetho_offset(), self._text.isChecked())

    def _make_item(self, auto: bool = False) -> None:
        """今の見た目でコマを書き出して出す（出ていれば出し直す）。

        auto は見た目が変わったときの自動の作り直し。フォルダを選ぶ窓は出さず、
        失敗したら同じ見た目では試し直さない。
        """
        profile = self._session.profile
        if profile.style not in ITEM_STYLES:
            self._notify(_say(T_BAD_STYLE, names=style_names(ITEM_STYLES)))
            return
        if self._client.state != READY:
            self._notify(tr("VTube Studio につながってから押してください"))
            return
        stetho = self._stetho_offset()
        text = self._text.isChecked()
        key = look_key(profile, stetho, text)
        folder = self._resolved_dir()
        if folder is None:
            self._notify(tr(NOT_ITEMS_NOTICE))
            if auto:
                self._failed_key = key
                return
            self._choose_folder()
            folder = self._resolved_dir()
            if folder is None:
                return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            # 心臓わしづかみは、クリックで流す「ぎゅっ」のコマも後ろに足す
            frames = render_frames(profile, stetho=stetho, text=text, squeeze=True)
            squeeze = squeeze_frame_count(profile)
            count = write_frames(frames, folder / ITEM_FOLDER)
        except (OSError, RuntimeError):
            self._failed_key = key
            self._notify(
                tr("アイテムの画像を書き出せませんでした（書き出し先のフォルダを確かめてください）")
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._made_key = key
        self._failed_key = None
        # 次に起動したとき、書き出してあるコマが今の見た目か・「ぎゅっ」のコマが何枚かを見分ける
        self._save(vts_item_look=list(key), vts_item_squeeze=squeeze)
        self._busy = True
        hand = self._heart.hand_placed
        self._heart.show_item(count, lambda ok: self._item_shown(ok, auto, hand), squeeze)

    def _item_shown(self, ok: bool, auto: bool = False, hand: bool = False) -> None:
        """hand は、手で体に置いた心臓を作り直した（置いてあった所に出し、体からは外れた）。"""
        self._busy = False
        if ok:
            self._auto_show = True
            # 手で体に置いた心臓は、出し直す前に読んだ今の場所に出した。次に起動したときもそこへ
            place = self._heart.place
            self._save(
                vts_item_shown=True,
                vts_item_place=list(place) if place else None,
                vts_hand_placed=self._heart.hand_placed,
            )
            pinned = self._heart.model_id in self._heart.pins
            if hand:
                self._notify(_say(T_HAND_REMADE_NOTICE, pin=PIN_BUTTON))
            elif auto:
                self._notify(tr(REMADE_NOTICE))
            elif pinned:
                self._notify(tr("VTube Studio に心臓を出し、覚えている場所に付けました"))
            else:
                self._notify(
                    _say(
                        "VTube Studio に心臓を出しました。次は「{pin}」を押してください",
                        pin=PIN_BUTTON,
                    )
                )
        else:
            self._notify(
                _say("VTube Studio に出せませんでした（{error}）", error=self._heart.last_error)
            )
        self._refresh()

    def _auto_remake(self) -> None:
        """出している心臓と見た目が違えば、少し待ってから今の見た目で作り直す。"""
        key = self._look_key()
        if (
            self._client.state != READY
            or self._busy
            or self._heart.instance_id is None
            or self._heart.picking
            or self._session.profile.style not in ITEM_STYLES
            or key in (self._made_key, self._failed_key)
        ):
            self._pending = None
            return
        now = time.monotonic()
        if self._pending is None or self._pending[0] != key:
            self._pending = (key, now)
            return
        # 続けて変えている間と、つまみや心臓を回すドラッグの途中は待つ
        dragging = QApplication.mouseButtons() != Qt.MouseButton.NoButton
        if now - self._pending[1] < REMAKE_WAIT_S or dragging:
            return
        self._pending = None
        self._make_item(auto=True)

    def _hide_item(self) -> None:
        self._auto_show = False
        self._save(vts_item_shown=False, vts_hand_placed=False)
        if self._client.state == READY:
            self._heart.hide_item()
        self._refresh()

    # ------------------------------------------------------------ 留める・大きさ

    def _toggle_pick(self) -> None:
        if self._heart.picking:
            self._heart.cancel_pick()
        elif self._client.state != READY:
            self._notify(tr("VTube Studio につながってから押してください"))
        elif not self._heart.start_pick(self._picked):
            self._notify(
                _say("先に「{show}」で VTube Studio に心臓を出してください", show=SHOW_BUTTON)
            )
        else:
            self._notify(tr(PICK_NOTICE))
        self._refresh()

    def _picked(self, pin: dict | None) -> None:
        if pin is None:
            self._notify(
                _say("モデルに付けられませんでした（{error}）", error=self._heart.last_error)
            )
        else:
            self._save(vts_pins=self._heart.pins, vts_hand_placed=False)
            self._notify(tr(PINNED_NOTICE))
        self._refresh()

    def _on_size(self, value: int) -> None:
        self._heart.set_size(value / 100.0)
        self._bpm.set_size(self._heart.size)
        if not self._size.isSliderDown():
            self._save_size()

    def _save_size(self) -> None:
        self._save(vts_item_size=self._heart.size)

    # ------------------------------------------------------------ 拍

    def tick(self, t: float) -> None:
        """操作画面のタイマーごと。拍が来たらアイテムを再生し、パラメータを送る。"""
        self._auto_remake()
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
        self._bpm.tick(float(clock.bpm))
        if self._params.isChecked() and t - self._last_param >= PARAM_INTERVAL_S:
            self._last_param = t
            cycle = clock.cycle(t)
            pulse = max(cycle.squeeze, cycle.eject * 0.55)
            self._heart.send_params(pulse, float(clock.bpm))

    def shutdown(self) -> None:
        self._client.stop()
