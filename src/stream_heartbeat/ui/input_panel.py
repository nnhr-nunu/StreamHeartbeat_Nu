"""操作画面「① 入力」のうち、マイクの代わりの入力（β）: 音声・動画ファイルと Bluetooth の心拍計。

どちらを使っているか・選んだファイル・つないだ心拍計は、この PC の設定（app_state.json）に覚える。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt, Signal
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

from stream_heartbeat.audio import MicMonitor
from stream_heartbeat.ble_heart_rate import (
    CONNECTED,
    CONNECTING,
    IDLE,
    NO_BLUETOOTH,
    RETRYING,
    SCANNING,
    HeartRateLink,
    bluetooth_supported,
)
from stream_heartbeat.file_input import MAX_FILE_S, FilePlayer, load_pcm16
from stream_heartbeat.heart_rate import BeatsFromRate, HeartRateReading
from stream_heartbeat.i18n import SKIP_PROP, tr
from stream_heartbeat.profile import load_app_state, save_app_state
from stream_heartbeat.samples import AUDIO_FILTER
from stream_heartbeat.ui.combo import MarkedComboBox
from stream_heartbeat.ui.forms import CenteredForm

MODE_MIC = "mic"
MODE_FILE = "file"
MODE_BLE = "ble"
MODES = (
    (MODE_MIC, "マイク"),
    (MODE_FILE, "音声・動画ファイル（β）"),
    (MODE_BLE, "Bluetooth 心拍計（β）"),
)
# 再生の位置の表示を書き換える間隔（秒）
POSITION_REFRESH_S = 0.25
PLAY = "▶ 再生"
STOP = "■ 止める"
CONNECT = "つなぐ"
DISCONNECT = "切る"
FILE_GUIDE = (
    "録音した心音のファイルを、マイクの代わりに流して心臓を動かします（β）。"
    "動画のファイルは音だけを使います。長いファイルは最初の {minutes} 分まで読みます。"
)
BLE_GUIDE = (
    "Bluetooth で心拍を送れる心拍計・時計から、心拍数を受け取って動かします（β）。"
    "届くのは心拍数だけなので、拍の瞬間は本物の鼓動とずれます。"
    "確実なのは胸ベルトや腕のセンサー（Polar H10・Verity Sense、Garmin HRM-Dual・HRM-Pro、"
    "Wahoo TICKR、COOSPO など）。時計は心拍を送る設定にします（Pixel Watch 2 以降の"
    "「Connected Fitness」、Fitbit Charge 6 の「機器内の心拍数」、"
    "Garmin の心拍数のブロードキャストなど。"
    "PC とつながらない機種もあります）。Apple Watch・Galaxy Watch はそのままでは送れません。"
    "スマホのアプリとつながっている間は、PC からつなげない機種があります。"
)
NO_BLE_SUPPORT = "この版では Bluetooth の心拍計を使えません"
STATE_TEXTS = {
    IDLE: "つないでいません",
    SCANNING: "探しています…",
    CONNECTING: "つないでいます…",
    CONNECTED: "つながりました。心拍数を待っています",
    RETRYING: "見つかりません。心拍計が心拍を送る設定か・近くにあるかを確かめてください"
    "（つなぎ直しています）",
    NO_BLUETOOTH: "Bluetooth を使えません。PC の Bluetooth がオンかを確かめてください",
}
NOT_FOUND = (
    "心拍計が見つかりませんでした。心拍を送る設定にしてから、もう一度「探す」を押してください"
)


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def _saved_mode(raw: object) -> str:
    known = {key for key, _label in MODES}
    return raw if isinstance(raw, str) and raw in known else MODE_MIC


class InputPanel(QWidget):
    """入力のしかたの一覧（mode_combo）と、ファイル・心拍計の欄。マイクの欄は操作画面が持つ。"""

    mode_changed = Signal(str)

    def __init__(
        self,
        data_dir: Path,
        notify: Callable[[str], None],
        now: Callable[[], float],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._notify = notify
        self._now = now
        state = load_app_state(data_dir)
        saved_file = state.get("input_file")
        self._file: Path | None = Path(saved_file) if isinstance(saved_file, str) else None
        self._player: FilePlayer | None = None
        self._sound = MicMonitor()
        self._shown_at = -1.0
        address = state.get("ble_address")
        self._address = address if isinstance(address, str) else ""
        name = state.get("ble_name")
        self._device_name = name if isinstance(name, str) else ""
        self._beats = BeatsFromRate()
        self._link = HeartRateLink(self)
        self._link.devices_found.connect(self._on_found)
        self._link.state_changed.connect(self._on_link_state)
        self._link.reading.connect(self._on_reading)

        self.mode_combo = MarkedComboBox()
        for key, label in MODES:
            self.mode_combo.addItem(label, key)

        # ---- ファイル
        self._file_name = QLabel("")
        self._file_name.setObjectName("meta")
        self._file_name.setProperty(SKIP_PROP, True)
        self._file_name.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        choose = QPushButton("選ぶ…")
        choose.clicked.connect(self._choose_file)
        file_row = QHBoxLayout()
        file_row.addWidget(self._file_name, 1)
        file_row.addWidget(choose)
        self._play = QPushButton(PLAY)
        self._play.clicked.connect(self._toggle_play)
        self._position = QLabel("")
        self._position.setObjectName("meta")
        play_row = QHBoxLayout()
        play_row.addWidget(self._play)
        play_row.addWidget(self._position, 1)
        self._loop = QCheckBox("くり返し再生")
        self._loop.setChecked(bool(state.get("input_loop", True)))
        self._loop.toggled.connect(self._on_loop)
        self._hear = QCheckBox("音も鳴らす（配信に乗らないよう注意）")
        self._hear.setToolTip(
            "ファイルの音をこの PC のスピーカーから出します。ヘッドホンがおすすめです"
        )
        self._hear.setChecked(bool(state.get("input_sound", False)))
        self._hear.toggled.connect(self._on_hear)
        file_form = CenteredForm()
        file_form.addRow("ファイル", file_row)
        file_form.addRow("再生", play_row)
        self._file_guide = QLabel("")
        self._file_guide.setObjectName("guide")
        self._file_guide.setWordWrap(True)
        self._file_box = QWidget()
        file_col = QVBoxLayout(self._file_box)
        file_col.setContentsMargins(0, 0, 0, 0)
        file_col.addLayout(file_form)
        file_col.addWidget(self._loop)
        file_col.addWidget(self._hear)
        file_col.addWidget(self._file_guide)

        # ---- Bluetooth の心拍計
        self._devices = MarkedComboBox()
        self._devices.setProperty(SKIP_PROP, True)
        self._scan = QPushButton("探す")
        self._scan.clicked.connect(self._start_scan)
        device_row = QHBoxLayout()
        device_row.addWidget(self._devices, 1)
        device_row.addWidget(self._scan)
        self._connect = QPushButton(CONNECT)
        self._connect.clicked.connect(self._toggle_connect)
        self._ble_status = QLabel("")
        self._ble_status.setObjectName("meta")
        self._ble_status.setWordWrap(True)
        connect_row = QHBoxLayout()
        connect_row.addWidget(self._connect)
        connect_row.addWidget(self._ble_status, 1)
        ble_form = CenteredForm()
        ble_form.addRow("心拍計", device_row)
        ble_form.addRow("", connect_row)
        self._ble_guide = QLabel(BLE_GUIDE)
        self._ble_guide.setObjectName("guide")
        self._ble_guide.setWordWrap(True)
        self._ble_box = QWidget()
        ble_col = QVBoxLayout(self._ble_box)
        ble_col.setContentsMargins(0, 0, 0, 0)
        ble_col.addLayout(ble_form)
        ble_col.addWidget(self._ble_guide)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._file_box)
        layout.addWidget(self._ble_box)

        if self._address:
            self._devices.addItem(self._device_name or self._address, self._address)
        saved_mode = _saved_mode(state.get("input_mode"))
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(saved_mode))
        self.mode_combo.currentIndexChanged.connect(self._on_mode)
        self.retranslate()
        self._show_mode()
        if self.mode == MODE_BLE:
            self._auto_connect()

    # ------------------------------------------------------------ 操作画面から呼ぶ

    @property
    def mode(self) -> str:
        return str(self.mode_combo.currentData() or MODE_MIC)

    @property
    def heart_rate(self) -> int:
        """心拍計から届いている心拍数（届いていなければ 0）。"""
        return self._beats.bpm if self._beats.beating else 0

    def pull(self, now: float) -> list[float]:
        """ファイルから、前に呼んでから流れた分の音（ファイルを使っていなければ空）。"""
        if self.mode != MODE_FILE or self._player is None:
            return []
        was_playing = self._player.playing
        samples = self._player.pull(now)
        if samples and self._hear.isChecked():
            self._sound.write_mono(samples)
        if was_playing and not self._player.playing:
            # くり返しなしで最後まで流した
            self._sound.stop()
            self._show_play()
        if abs(now - self._shown_at) >= POSITION_REFRESH_S:
            self._show_position()
        return samples

    def beats(self, now: float) -> list[float]:
        """心拍計の心拍数から刻んだ拍のうち、now までに来たもの（心拍計を使っていなければ空）。"""
        if self.mode != MODE_BLE:
            return []
        return self._beats.due(now)

    def retranslate(self) -> None:
        """表示言語が変わったとき、実行中に組み立てた文を作り直す（静的な部品は走査が付け替える）。"""
        self._file_guide.setText(tr(FILE_GUIDE, minutes=MAX_FILE_S // 60))
        self._show_file()
        self._show_play()
        self._show_position()
        self._show_link()

    def shutdown(self) -> None:
        self._sound.stop()
        self._link.shutdown()

    # ------------------------------------------------------------ 入力のしかた

    def _on_mode(self, _index: int = 0) -> None:
        mode = self.mode
        self._save(input_mode=mode)
        if mode != MODE_FILE and self._player is not None:
            self._player.pause()
            self._sound.stop()
            self._show_play()
        if mode == MODE_BLE:
            self._auto_connect()
        else:
            self._link.disconnect()
            self._beats.reset()
        self._show_mode()
        self.mode_changed.emit(mode)

    def _show_mode(self) -> None:
        self._file_box.setVisible(self.mode == MODE_FILE)
        self._ble_box.setVisible(self.mode == MODE_BLE)

    def _save(self, **values: object) -> None:
        try:
            save_app_state(self._data_dir, **values)
        except OSError:
            pass

    # ------------------------------------------------------------ ファイル

    def _choose_file(self) -> None:
        start = str(self._file.parent) if self._file is not None else ""
        path, _ok = QFileDialog.getOpenFileName(
            self, tr("心音のファイルを選ぶ"), start, tr(AUDIO_FILTER)
        )
        if not path:
            return
        self._file = Path(path)
        self._save(input_file=str(self._file))
        if self._player is not None:
            self._player.stop()
            self._sound.stop()
        self._player = None
        self._show_file()
        if self._load():
            self._start_playing()

    def _load(self) -> bool:
        """選んだファイルを読む。読めなければ知らせて False。"""
        if self._file is None:
            return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        # 読んでいる間も画面は動くので、選び直し・再生を押せないようにする
        self._file_box.setEnabled(False)
        try:
            pcm, cut = load_pcm16(self._file)
        except (OSError, ValueError, RuntimeError):
            self._notify(tr("このファイルは読めませんでした"))
            return False
        finally:
            self._file_box.setEnabled(True)
            QApplication.restoreOverrideCursor()
        self._player = FilePlayer(pcm)
        self._player.loop = self._loop.isChecked()
        if cut:
            self._notify(
                tr("長いファイルなので、最初の {minutes} 分だけ使います", minutes=MAX_FILE_S // 60)
            )
        return True

    def _toggle_play(self) -> None:
        if self._player is not None and self._player.playing:
            self._player.stop()
            self._sound.stop()
            self._show_play()
            self._show_position()
            return
        if self._file is None:
            self._choose_file()
            return
        if self._player is None and not self._load():
            return
        self._start_playing()

    def _start_playing(self) -> None:
        if self._player is None:
            return
        self._player.play(self._now())
        if self._hear.isChecked():
            self._sound.start()
        self._show_play()

    def _on_loop(self, on: bool) -> None:
        self._save(input_loop=on)
        if self._player is not None:
            self._player.loop = on

    def _on_hear(self, on: bool) -> None:
        self._save(input_sound=on)
        if on and self._player is not None and self._player.playing:
            self._sound.start()
        elif not on:
            self._sound.stop()

    def _show_file(self) -> None:
        chosen = self._file
        self._file_name.setText(chosen.name if chosen is not None else tr("（まだ選んでいません）"))
        self._file_name.setToolTip(str(chosen) if chosen is not None else "")

    def _show_play(self) -> None:
        playing = self._player is not None and self._player.playing
        self._play.setText(tr(STOP if playing else PLAY))

    def _show_position(self) -> None:
        self._shown_at = self._now()
        if self._player is None:
            self._position.setText("")
            return
        self._position.setText(
            f"{_clock(self._player.position)} / {_clock(self._player.duration)}"
        )

    # ------------------------------------------------------------ Bluetooth の心拍計

    def _start_scan(self) -> None:
        if not bluetooth_supported():
            self._notify(tr(NO_BLE_SUPPORT))
            return
        self._beats.reset()
        self._link.scan()

    def _on_found(self, devices: list) -> None:
        self._devices.clear()
        for address, name in devices:
            self._devices.addItem(name or address, address)
        if not devices:
            if self._link.state != NO_BLUETOOTH:
                self._notify(tr(NOT_FOUND))
            if self._address:
                self._devices.addItem(self._device_name or self._address, self._address)
            return
        index = self._devices.findData(self._address)
        self._devices.setCurrentIndex(max(0, index))
        # 1 台だけならすぐつなぐ
        if len(devices) == 1:
            self._connect_chosen()

    def _toggle_connect(self) -> None:
        if self._link.state in (CONNECTING, CONNECTED, RETRYING):
            self._link.disconnect()
            self._beats.reset()
            return
        self._connect_chosen()

    def _connect_chosen(self) -> None:
        address = str(self._devices.currentData() or "")
        if not address:
            self._start_scan()
            return
        if not bluetooth_supported():
            self._notify(tr(NO_BLE_SUPPORT))
            return
        self._address = address
        self._device_name = self._devices.currentText()
        self._save(ble_address=address, ble_name=self._device_name)
        self._beats.reset()
        self._link.connect_to(address)

    def _auto_connect(self) -> None:
        if self._address and bluetooth_supported() and self._link.state == IDLE:
            self._link.connect_to(self._address)

    def _on_link_state(self, state: str) -> None:
        if state != CONNECTED:
            self._beats.reset()
        self._show_link()

    def _on_reading(self, reading: HeartRateReading) -> None:
        self._beats.feed(reading, self._now())
        self._show_link()

    def _show_link(self) -> None:
        state = self._link.state
        busy = state in (CONNECTING, CONNECTED, RETRYING)
        self._connect.setText(tr(DISCONNECT if busy else CONNECT))
        self._scan.setEnabled(state != SCANNING)
        if not bluetooth_supported():
            self._ble_status.setText(tr(NO_BLE_SUPPORT))
        elif state == CONNECTED and self.heart_rate:
            self._ble_status.setText(tr("受信中  {bpm} BPM", bpm=self.heart_rate))
        else:
            self._ble_status.setText(tr(STATE_TEXTS.get(state, STATE_TEXTS[IDLE])))
