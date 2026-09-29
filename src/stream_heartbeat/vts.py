"""VTube Studio 連携（プラグイン API）。

心臓を VTube Studio の「アイテム」として出し、拍ごとにコマ送りを最初から再生する。
アイテムはモデルにピン留めすれば体と一緒に動くので、配信画面で心臓がずれない。
あわせて拍（0〜1）と心拍数をカスタムパラメータとして送り、モデル側で動きに使える。

API は ws://127.0.0.1:8001 の WebSocket（localhost と書くと名前の解決待ちで遅れることがある）。
初回は VTube Studio 側に出る確認でユーザーが「許可」を押すと、トークンがもらえる
（次からはそれで入る）。
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket

API_NAME = "VTubeStudioPublicAPI"
API_VERSION = "1.0"
DEFAULT_PORT = 8001
PLUGIN_NAME = "StreamHeartbeat"
PLUGIN_DEVELOPER = "Nunuhara"
# アイテムのフォルダ名。ANIM_ で始まるフォルダは VTube Studio がコマ送りのアイテムとして読む
ITEM_FOLDER = "ANIM_StreamHeartbeat"
PARAM_BEAT = "SHBHeartbeat"
PARAM_BPM = "SHBBpm"
RETRY_MS = 5000
# パラメータは 1 秒に 1 回以上送らないと VTube Studio が手放す。なめらかさのため 30 回/秒
PARAM_INTERVAL_S = 1.0 / 30.0

# 状態（操作画面の表示に使う）
OFF = "off"
CONNECTING = "connecting"
WAITING_USER = "waiting_user"
READY = "ready"
NO_VTS = "no_vts"
DENIED = "denied"

Reply = Callable[[dict], None]


def _steam_libraries() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                value, _kind = winreg.QueryValueEx(key, "SteamPath")
                roots.append(Path(str(value)))
        except OSError:
            pass
    roots += [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    libraries: list[Path] = []
    for root in roots:
        libraries.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(raw.replace("\\\\", "\\")))
    return libraries


def find_items_dir() -> Path | None:
    """VTube Studio のアイテムのフォルダ（Steam 版）。見つからなければ None。"""
    tail = Path("steamapps/common/VTube Studio/VTube Studio_Data/StreamingAssets/Items")
    for library in _steam_libraries():
        candidate = library / tail
        if candidate.is_dir():
            return candidate
    return None


def item_framerate(frames_per_second: float, systole: float, reference_systole: float) -> float:
    """拍が速いほど収縮が短いので、そのぶんコマ送りも速める（0.1〜120 に収める）。"""
    rate = frames_per_second * reference_systole / max(0.05, systole)
    return max(0.1, min(120.0, rate))


class VtsClient(QObject):
    """VTube Studio との接続と認証。つながらなければ数秒おきにつなぎ直す。"""

    state_changed = Signal(str)
    token_changed = Signal(str)
    ready = Signal()

    def __init__(self, token: str = "", port: int = DEFAULT_PORT, parent: QObject | None = None):
        super().__init__(parent)
        self._token = token
        self._port = port
        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self._on_message)
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self._open)
        self._enabled = False
        self._state = OFF
        self._next_id = 0
        self._waiting: dict[str, Reply | None] = {}

    @property
    def state(self) -> str:
        return self._state

    @property
    def token(self) -> str:
        return self._token

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def start(self) -> None:
        self._enabled = True
        self._open()

    def stop(self) -> None:
        self._enabled = False
        self._retry.stop()
        self._waiting.clear()
        self._socket.close()
        self._set_state(OFF)

    def _open(self) -> None:
        if not self._enabled:
            return
        self._set_state(CONNECTING)
        self._socket.abort()
        self._socket.open(QUrl(f"ws://127.0.0.1:{self._port}"))

    def _on_connected(self) -> None:
        self._authenticate()

    def _on_disconnected(self) -> None:
        self._waiting.clear()
        if not self._enabled:
            return
        if self._state != DENIED:
            self._set_state(NO_VTS)
        self._retry.start(RETRY_MS)

    def request(self, message_type: str, data: dict | None = None, on_reply: Reply | None = None):
        """要求を送る。返事（data 部分、エラーなら errorID を含む）は on_reply に渡す。"""
        if self._state not in (READY, WAITING_USER, CONNECTING) or not self._socket.isValid():
            return
        self._next_id += 1
        request_id = f"shb{self._next_id}"
        self._waiting[request_id] = on_reply
        payload = {
            "apiName": API_NAME,
            "apiVersion": API_VERSION,
            "requestID": request_id,
            "messageType": message_type,
            "data": data or {},
        }
        self._socket.sendTextMessage(json.dumps(payload, ensure_ascii=False))

    def _on_message(self, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        handler = self._waiting.pop(str(message.get("requestID", "")), None)
        data = message.get("data") if isinstance(message.get("data"), dict) else {}
        if message.get("messageType") == "APIError":
            data = {"errorID": data.get("errorID", -1), "message": data.get("message", "")}
        if handler is not None:
            handler(data)

    # ------------------------------------------------------------ 認証

    def _authenticate(self) -> None:
        if not self._token:
            self._ask_token()
            return
        self.request(
            "AuthenticationRequest",
            {
                "pluginName": PLUGIN_NAME,
                "pluginDeveloper": PLUGIN_DEVELOPER,
                "authenticationToken": self._token,
            },
            self._on_authenticated,
        )

    def _ask_token(self) -> None:
        self._set_state(WAITING_USER)
        self.request(
            "AuthenticationTokenRequest",
            {"pluginName": PLUGIN_NAME, "pluginDeveloper": PLUGIN_DEVELOPER},
            self._on_token,
        )

    def _on_token(self, data: dict) -> None:
        token = data.get("authenticationToken")
        if not isinstance(token, str) or not token:
            # 「許可しない」を押された。勝手に聞き直さない
            self._enabled = False
            self._set_state(DENIED)
            self._socket.close()
            return
        self._token = token
        self.token_changed.emit(token)
        self._authenticate()

    def _on_authenticated(self, data: dict) -> None:
        if data.get("authenticated") is True:
            self._set_state(READY)
            self.ready.emit()
            return
        # トークンが古い（VTube Studio 側で取り消された）ので、もう一度許可をもらう
        self._token = ""
        self.token_changed.emit("")
        self._ask_token()


class VtsHeart:
    """VTube Studio 上の心臓アイテムと、拍・心拍数のパラメータ。"""

    def __init__(self, client: VtsClient) -> None:
        self._client = client
        self.instance_id: str | None = None
        self.frame_count = 0
        self.last_error = ""
        self._params_ready = False
        client.ready.connect(self._on_ready)
        client.state_changed.connect(self._on_state)

    def _on_state(self, state: str) -> None:
        if state != READY:
            self._params_ready = False

    def _on_ready(self) -> None:
        # つなぎ直したときは、前に出したアイテムがまだ場にあれば使い続ける
        self._find_instance(None)

    # ------------------------------------------------------------ アイテム

    def _find_instance(self, then: Callable[[], None] | None) -> None:
        def got(data: dict) -> None:
            items = data.get("itemInstancesInScene") or []
            mine = [i for i in items if isinstance(i, dict) and i.get("fileName") == ITEM_FOLDER]
            if mine:
                self.instance_id = str(mine[0].get("instanceID"))
                count = mine[0].get("frameCount")
                if isinstance(count, int) and count > 0:
                    self.frame_count = count
            else:
                self.instance_id = None
            if then is not None:
                then()

        self._client.request(
            "ItemListRequest",
            {
                "includeAvailableSpots": False,
                "includeItemInstancesInScene": True,
                "includeAvailableItemFiles": True,
                "onlyItemsWithFileName": ITEM_FOLDER,
            },
            got,
        )

    def show_item(self, frame_count: int, done: Callable[[bool], None] | None = None) -> None:
        """心臓アイテムを出し直す（新しいコマを読ませるため、出ていれば一度しまう）。"""
        self.frame_count = frame_count

        def load() -> None:
            self._client.request(
                "ItemLoadRequest",
                {
                    "fileName": ITEM_FOLDER,
                    "positionX": 0.0,
                    "positionY": -0.15,
                    "size": 0.3,
                    "rotation": 0,
                    "fadeTime": 0.3,
                    "order": 5,
                    "failIfOrderTaken": False,
                    "smoothing": 0,
                    "censored": False,
                    "flipped": False,
                    "locked": False,
                    "unloadWhenPluginDisconnects": False,
                },
                loaded,
            )

        def loaded(data: dict) -> None:
            instance = data.get("instanceID")
            if not isinstance(instance, str):
                self.last_error = str(data.get("message") or "アイテムを出せませんでした")
                if done is not None:
                    done(False)
                return
            self.instance_id = instance
            self.last_error = ""
            self._rest()
            if done is not None:
                done(True)

        def unload_then_load() -> None:
            if self.instance_id is None:
                load()
                return
            self._client.request(
                "ItemUnloadRequest",
                {
                    "unloadAllInScene": False,
                    "unloadAllLoadedByThisPlugin": False,
                    "allowUnloadingItemsLoadedByUserOrOtherPlugins": True,
                    "instanceIDs": [self.instance_id],
                    "fileNames": [],
                },
                lambda _data: load(),
            )

        self._find_instance(unload_then_load)

    def _rest(self) -> None:
        """最後のコマ（休んでいる形）で止めておく。"""
        if self.instance_id is None or self.frame_count <= 0:
            return
        last = self.frame_count - 1
        self._client.request(
            "ItemAnimationControlRequest",
            {
                "itemInstanceID": self.instance_id,
                "framerate": -1,
                "frame": last,
                "brightness": -1,
                "opacity": -1,
                "setAutoStopFrames": True,
                "autoStopFrames": [last],
                "setAnimationPlayState": True,
                "animationPlayState": False,
            },
        )

    def beat(self, framerate: float) -> None:
        """拍。最初のコマから再生し、最後のコマ（休み）で止まる。"""
        if self._client.state != READY or self.instance_id is None or self.frame_count <= 0:
            return
        self._client.request(
            "ItemAnimationControlRequest",
            {
                "itemInstanceID": self.instance_id,
                "framerate": framerate,
                "frame": 0,
                "brightness": -1,
                "opacity": -1,
                "setAutoStopFrames": True,
                "autoStopFrames": [self.frame_count - 1],
                "setAnimationPlayState": True,
                "animationPlayState": True,
            },
        )

    # ------------------------------------------------------------ パラメータ

    def send_params(self, pulse: float, bpm: float) -> None:
        if self._client.state != READY:
            return
        if not self._params_ready:
            self._params_ready = True
            for name, explanation, top, default in (
                (PARAM_BEAT, "StreamHeartbeat: 拍（0〜1、拍の瞬間に 1）", 1.0, 0.0),
                (PARAM_BPM, "StreamHeartbeat: 心拍数", 240.0, 72.0),
            ):
                self._client.request(
                    "ParameterCreationRequest",
                    {
                        "parameterName": name,
                        "explanation": explanation,
                        "min": 0.0,
                        "max": top,
                        "defaultValue": default,
                    },
                )
        self._client.request(
            "InjectParameterDataRequest",
            {
                "faceFound": False,
                "mode": "set",
                "parameterValues": [
                    {"id": PARAM_BEAT, "value": round(max(0.0, min(1.0, pulse)), 4)},
                    {"id": PARAM_BPM, "value": round(max(0.0, min(240.0, bpm)), 1)},
                ],
            },
        )
