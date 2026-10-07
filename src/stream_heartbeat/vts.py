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
import math
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
# アイテムの大きさ（0〜1。VTube Studio で手で出したときがおよそ 0.32）
ITEM_SIZE = 0.3
ITEM_SIZE_MIN = 0.05
ITEM_SIZE_MAX = 0.8
# 出したときの位置（画面の真ん中の少し下）
ITEM_HOME = (0.0, -0.15)
# 留める場所を選ぶあいだ、心臓がクリックの邪魔をしないよう寄せておく位置（左端寄り）
PICK_ASIDE_X = -0.75
# モデル上の場所（ArtMesh の三角形と、その中の重み）。ItemPinRequest の pinInfo に使う
PIN_KEYS = (
    "modelID",
    "artMeshID",
    "vertexID1",
    "vertexID2",
    "vertexID3",
    "vertexWeight1",
    "vertexWeight2",
    "vertexWeight3",
)
# ItemAnimationControlRequest で「そのアイテムは場に無い」
ERROR_ITEM_NOT_FOUND = 850
# ItemEvent の種類: VTube Studio の画面でアイテムをドラッグして、モデルの上に落とした（留まった）／
# モデルの外に落とした
DROPPED_PINNED = "DroppedPinned"
DROPPED_UNPINNED = "DroppedUnpinned"
# アイテムを置ける位置の範囲（ItemLoadRequest。画面の端は ±1）
POSITION_LIMIT = 1000.0

# 状態（操作画面の表示に使う）
OFF = "off"
CONNECTING = "connecting"
WAITING_USER = "waiting_user"
READY = "ready"
NO_VTS = "no_vts"
DENIED = "denied"

Reply = Callable[[dict], None]


def _steam_roots() -> list[Path]:
    """Steam 本体の場所の候補。"""
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / "Steam"]
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
    return roots


def _steam_libraries() -> list[Path]:
    libraries: list[Path] = []
    for root in _steam_roots():
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
    """VTube Studio のアイテムのフォルダ（Steam 版）。見つからなければ None。

    Windows 版は VTube Studio_Data の中、Mac 版はアプリ（.app）の中にある。
    """
    items = Path("StreamingAssets/Items")
    for library in _steam_libraries():
        game = library / "steamapps/common/VTube Studio"
        candidates = [game / "VTube Studio_Data" / items]
        bundles = sorted(game.glob("*.app"))
        candidates += [app / "Contents/Resources/Data" / items for app in bundles]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
    return None


def item_framerate(frames_per_second: float, systole: float, reference_systole: float) -> float:
    """拍が速いほど収縮が短いので、そのぶんコマ送りも速める（0.1〜120 に収める）。"""
    rate = frames_per_second * reference_systole / max(0.05, systole)
    return max(0.1, min(120.0, rate))


def clean_pin(raw: object) -> dict | None:
    """保存・受信したピンの場所を確かめる。形が崩れていれば None。"""
    if not isinstance(raw, dict):
        return None
    pin = {key: raw.get(key) for key in PIN_KEYS}
    if not all(isinstance(pin[key], str) and pin[key] for key in PIN_KEYS[:2]):
        return None
    for key in PIN_KEYS[2:5]:
        if not isinstance(pin[key], int) or isinstance(pin[key], bool):
            return None
    for key in PIN_KEYS[5:]:
        if not isinstance(pin[key], (int, float)) or isinstance(pin[key], bool):
            return None
        pin[key] = float(pin[key])
    return pin


def clicked_pin(event: dict) -> dict | None:
    """ModelClickedEvent から、いちばん手前の ArtMesh 上の場所を取り出す（左クリックだけ）。"""
    if event.get("modelWasClicked") is not True or event.get("mouseButtonID") != 0:
        return None
    return hit_pin(event.get("artMeshHits"))


def hit_pin(raw: object) -> dict | None:
    """ArtMesh に当たった所の一覧（artMeshHits）から、いちばん手前の場所を取り出す。"""
    hits = [h for h in raw if isinstance(h, dict)] if isinstance(raw, list) else []
    hits.sort(key=lambda h: o if isinstance(o := h.get("artMeshOrder"), int) else 999)
    for hit in hits:
        pin = clean_pin(hit.get("hitInfo"))
        if pin is not None:
            return pin
    return None


def clean_place(raw: object) -> tuple[float, float] | None:
    """保存・受信した画面の位置（x, y）を確かめる。形が崩れていれば None。"""
    if isinstance(raw, dict):
        raw = (raw.get("x"), raw.get("y"))
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    if not all(
        isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in raw
    ):
        return None
    x, y = (max(-POSITION_LIMIT, min(POSITION_LIMIT, float(v))) for v in raw)
    return x, y


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
        self._events: dict[str, Reply] = {}

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
        self._events.clear()
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
        # 切れると VTube Studio 側のイベント購読も消える。つなぎ直したら購読し直す
        self._waiting.clear()
        self._events.clear()
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

    def subscribe(self, event: str, config: dict, handler: Reply) -> None:
        """イベントを購読する。届いたイベントの data を handler に渡す。"""
        self._events[event] = handler
        self.request(
            "EventSubscriptionRequest", {"eventName": event, "subscribe": True, "config": config}
        )

    def unsubscribe(self, event: str) -> None:
        if self._events.pop(event, None) is not None:
            self.request(
                "EventSubscriptionRequest", {"eventName": event, "subscribe": False, "config": {}}
            )

    def _on_message(self, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        data = message.get("data") if isinstance(message.get("data"), dict) else {}
        event = self._events.get(str(message.get("messageType", "")))
        if event is not None:
            event(data)
            return
        handler = self._waiting.pop(str(message.get("requestID", "")), None)
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
    """VTube Studio 上の心臓アイテムと、拍・心拍数のパラメータ。

    モデルに留める場所（pins、モデル ID ごと）と大きさ（size）はこちらで覚え、
    出し直したとき・モデルを読み込み直したときに同じ場所へ留め直す。
    VTube Studio の API からは、手で留めた場所も今の位置も読み出せないため。
    VTube Studio の画面で心臓をドラッグして置いたときは、知らせ（ItemEvent）で置いた所を覚える。
    """

    def __init__(
        self,
        client: VtsClient,
        size: float = ITEM_SIZE,
        pins: dict[str, dict] | None = None,
        place: tuple[float, float] | None = None,
    ) -> None:
        self._client = client
        self.instance_id: str | None = None
        self.frame_count = 0
        self.last_error = ""
        self.size = size
        # コマの絵が、心臓のまわりをふつうの何倍の広さまで描いてあるか（肋骨・拍の文字の余白）。
        # VTube Studio へ渡す大きさに掛けて、心臓そのものの見かけの大きさは size のまま保つ
        self.zoom = 1.0
        self.pins: dict[str, dict] = dict(pins or {})
        # VTube Studio の画面でドラッグして置いた所（留める場所が分からないとき、ここに出す）
        self.place = place
        self.model_id = ""
        # つないだ直後に場を調べ終えたら、心臓が場にあったかを渡す
        self.on_found: Callable[[bool], None] | None = None
        # VTube Studio の画面で心臓を動かし、覚えている場所（pins・place）が変わった
        self.on_moved: Callable[[], None] | None = None
        self._params_ready = False
        self._pick_done: Callable[[dict | None], None] | None = None
        client.ready.connect(self._on_ready)
        client.state_changed.connect(self._on_state)

    @property
    def picking(self) -> bool:
        return self._pick_done is not None

    def _on_state(self, state: str) -> None:
        if state != READY:
            self._params_ready = False
            self._pick_done = None

    def _on_ready(self) -> None:
        self._client.subscribe("ModelLoadedEvent", {}, self._on_model)
        self._client.subscribe("ItemEvent", {"itemFileNames": [ITEM_FOLDER]}, self._on_item_event)
        self._client.request("CurrentModelRequest", {}, self._on_model)
        # つなぎ直したときは、前に出したアイテムがまだ場にあれば使い続ける
        self._find_instance(self._report_found)

    def _report_found(self) -> None:
        if self.on_found is not None:
            self.on_found(self.instance_id is not None)

    def _on_model(self, data: dict) -> None:
        loaded = data.get("modelLoaded") is True
        self.model_id = str(data.get("modelID") or "") if loaded else ""
        if loaded:
            self._pin_saved()

    def _on_item_event(self, data: dict) -> None:
        """VTube Studio の画面で心臓をドラッグして置いた。見た目を変えて出し直しても同じ所に出す。

        モデルの上に落とすと VTube Studio が留めるが、留めた場所（ArtMesh の三角形）は知らせて
        こない。落とした所にある ArtMesh を聞いて覚える（聞けない版では置いた所だけ覚える）。
        """
        kind = data.get("itemEventType")
        if kind not in (DROPPED_PINNED, DROPPED_UNPINNED) or self.instance_id is None:
            return
        place = clean_place(data.get("itemPosition"))
        if data.get("itemInstanceID") != self.instance_id or place is None:
            return
        self.place = place
        # 前に覚えた場所へは戻さない（置き直した所が新しい場所）
        model = self.model_id
        self.pins.pop(model, None)
        if kind == DROPPED_UNPINNED or not model:
            self._moved()
            return

        def got(reply: dict) -> None:
            pin = hit_pin(reply.get("artMeshHits"))
            if pin is not None and pin["modelID"] == model == self.model_id:
                self.pins[model] = pin
            self._moved()

        self._client.request(
            "ArtMeshAtPositionRequest", {"x": place[0], "y": place[1], "visualize": 0}, got
        )

    def _moved(self) -> None:
        if self.on_moved is not None:
            self.on_moved()

    def _vts_size(self) -> float:
        """VTube Studio へ渡す大きさ（コマを広く描いたぶん大きくする。0〜1 に収める）。"""
        return min(1.0, self.size * max(1.0, self.zoom))

    # ------------------------------------------------------------ アイテム

    def _find_instance(self, then: Callable[[], None] | None, rescan: bool = False) -> None:
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
                # 新しく書いたコマを読ませるには、ファイルの一覧を読み直させる
                # （少し重いので出すときだけ）
                "includeAvailableItemFiles": rescan,
                "onlyItemsWithFileName": ITEM_FOLDER,
            },
            got,
        )

    def show_item(self, frame_count: int, done: Callable[[bool], None] | None = None) -> None:
        """心臓アイテムを出し直す（新しいコマを読ませるため、出ていれば一度しまう）。"""
        self.frame_count = frame_count
        self._stop_pick()

        def load() -> None:
            # VTube Studio の画面で置いた所があればそこへ（覚えた場所があれば、出したあと留める）
            x, y = self.place or ITEM_HOME
            self._client.request(
                "ItemLoadRequest",
                {
                    "fileName": ITEM_FOLDER,
                    "positionX": x,
                    "positionY": y,
                    "size": self._vts_size(),
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
            # 場を調べたときに、しまう前のアイテムのコマ数で上書きされている
            self.frame_count = frame_count
            self.last_error = ""
            self._rest()
            self._pin_saved()
            if done is not None:
                done(True)

        def unload_then_load() -> None:
            if self.instance_id is None:
                load()
                return
            self._unload(lambda _data: load())

        self._find_instance(unload_then_load, rescan=True)

    def hide_item(self) -> None:
        """心臓アイテムをしまう。"""
        self._stop_pick()
        self._unload(None)
        self.instance_id = None

    def _unload(self, then: Reply | None) -> None:
        # 同じフォルダから出したものは（重複していても）まとめてしまう
        self._client.request(
            "ItemUnloadRequest",
            {
                "unloadAllInScene": False,
                "unloadAllLoadedByThisPlugin": False,
                "allowUnloadingItemsLoadedByUserOrOtherPlugins": True,
                "instanceIDs": [],
                "fileNames": [ITEM_FOLDER],
            },
            then,
        )

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
        instance = self.instance_id

        def replied(data: dict) -> None:
            # VTube Studio 側で消された。拍ごとにエラーを返させない
            if data.get("errorID") == ERROR_ITEM_NOT_FOUND and self.instance_id == instance:
                self.instance_id = None

        self._client.request(
            "ItemAnimationControlRequest",
            {
                "itemInstanceID": instance,
                "framerate": framerate,
                "frame": 0,
                "brightness": -1,
                "opacity": -1,
                "setAutoStopFrames": True,
                "autoStopFrames": [self.frame_count - 1],
                "setAnimationPlayState": True,
                "animationPlayState": True,
            },
            replied,
        )

    # ------------------------------------------------------------ 留める・大きさ

    def _pin_saved(self) -> None:
        pin = self.pins.get(self.model_id)
        if pin is not None and self.instance_id is not None and not self.picking:
            self._pin(pin)

    def _pin(self, pin: dict, then: Reply | None = None) -> None:
        self._client.request(
            "ItemPinRequest",
            {
                "pin": True,
                "itemInstanceID": self.instance_id,
                "angleRelativeTo": "RelativeToModel",
                "sizeRelativeTo": "RelativeToWorld",
                "vertexPinType": "Provided",
                "pinInfo": {**pin, "angle": 0, "size": self._vts_size()},
            },
            then,
        )

    def start_pick(self, done: Callable[[dict | None], None]) -> bool:
        """モデルをクリックした所へ心臓を留める。クリックを待ち、留めたら done(場所)。"""
        if self._client.state != READY or self.instance_id is None:
            return False
        self._pick_done = done
        # 心臓がモデルに重なっているとクリックが心臓に当たるので、外して脇へ寄せる
        self._client.request("ItemPinRequest", {"pin": False, "itemInstanceID": self.instance_id})
        self._move(x=PICK_ASIDE_X, y=0.0, seconds=0.3)
        self._client.subscribe("ModelClickedEvent", {"onlyClicksOnModel": True}, self._on_click)
        return True

    def cancel_pick(self) -> None:
        """クリック待ちをやめ、覚えている場所があればそこへ、無ければ出したときの位置へ戻す。"""
        if not self.picking:
            return
        self._stop_pick()
        if self.pins.get(self.model_id) is not None:
            self._pin_saved()
        elif self.instance_id is not None:
            x, y = self.place or ITEM_HOME
            self._move(x=x, y=y, seconds=0.3)

    def _stop_pick(self) -> None:
        if self._pick_done is not None:
            self._pick_done = None
            self._client.unsubscribe("ModelClickedEvent")

    def _on_click(self, data: dict) -> None:
        done = self._pick_done
        pin = clicked_pin(data)
        if done is None or pin is None or self.instance_id is None:
            return
        self._stop_pick()

        def pinned(reply: dict) -> None:
            if "errorID" in reply:
                self.last_error = str(reply.get("message") or "留められませんでした")
                done(None)
                return
            self.pins[pin["modelID"]] = pin
            done(pin)

        self._pin(pin, pinned)

    def set_size(self, size: float) -> None:
        self.size = max(ITEM_SIZE_MIN, min(ITEM_SIZE_MAX, size))
        if self._client.state != READY or self.instance_id is None:
            return
        # 留めてあるアイテムは移動の要求では大きさが変わらない。留め直しで大きさを渡す
        if self.pins.get(self.model_id) is not None and not self.picking:
            self._pin_saved()
        else:
            self._move(size=self._vts_size())

    def _move(
        self, *, x: float = -1000.0, y: float = -1000.0, size: float = -1000.0, seconds: float = 0.0
    ) -> None:
        """動かす・大きさを変える（-1000 以下の項目は今のまま）。"""
        self._client.request(
            "ItemMoveRequest",
            {
                "itemsToMove": [
                    {
                        "itemInstanceID": self.instance_id,
                        "timeInSeconds": seconds,
                        "fadeMode": "easeOut",
                        "positionX": x,
                        "positionY": y,
                        "size": size,
                        "rotation": -1000,
                        "order": -1000,
                        "setFlip": False,
                        "flip": False,
                        "userCanStop": True,
                    }
                ]
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
