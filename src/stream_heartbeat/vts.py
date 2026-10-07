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
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWebSockets import QWebSocket

from stream_heartbeat.vts_support import (  # noqa: F401  （ほかのファイルはここから読む）
    PIN_KEYS,
    POSITION_LIMIT,
    clean_pin,
    clean_place,
    clicked_pin,
    find_items_dir,
    hit_pin,
    item_framerate,
)

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
# ItemAnimationControlRequest で「そのアイテムは場に無い」
ERROR_ITEM_NOT_FOUND = 850
# ItemEvent の種類: VTube Studio の画面でアイテムをドラッグして、モデルの上に落とした（留まった）／
# モデルの外に落とした
DROPPED_PINNED = "DroppedPinned"
DROPPED_UNPINNED = "DroppedUnpinned"
# ItemEvent の種類: VTube Studio の画面でアイテムをクリックした
# （実物は Clicked。仕様書の例は ItemClicked）
CLICKED = frozenset({"Clicked", "ItemClicked"})
# 「ぎゅっ」のコマを流す速さ（コマを描いた速さ。heart_frames.FRAME_FPS と同じ）
SQUEEZE_FPS = 30.0
# VTube Studio は、アイテムを押したままマウスが少し動くと、クリック（Clicked）ではなく「落とした」
# （DroppedPinned など）と知らせてくる（2026-10-08 に正式版で確認）。押してから離すまでにマウスが
# この画素より動かなかったものは、長く押していてもドラッグではなくクリックとして扱う
# （付ける場所を選んで覚えた場所を、握るつもりのクリックで忘れないように）。
# CLICK_MAX_S は、離した知らせと結び付ける押した記録の古さの上限
CLICK_MAX_S = 5.0
CLICK_MOVE_PX = 12
# 続けて届いたクリックで「ぎゅっ」を最初からやり直さない間（秒）
SQUEEZE_REPEAT_S = 0.25
# こちらから留めた・外したときにも VTube Studio は DroppedPinned などを知らせてくる
# （留め直しでは返事のあとにも来る）。そのあいだの知らせは、手で置いたものとして扱わない秒数
OWN_PIN_QUIET_S = 1.5

# 状態（操作画面の表示に使う）
OFF = "off"
CONNECTING = "connecting"
WAITING_USER = "waiting_user"
READY = "ready"
NO_VTS = "no_vts"
DENIED = "denied"

Reply = Callable[[dict], None]


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
    心臓をクリックしたときは、心臓わしづかみの「ぎゅっ」のコマ（休んでいる形のあとに足したコマ）を流す。
    """

    def __init__(
        self,
        client: VtsClient,
        size: float = ITEM_SIZE,
        pins: dict[str, dict] | None = None,
        place: tuple[float, float] | None = None,
        squeeze_frames: int = 0,
        hand_placed: bool = False,
    ) -> None:
        self._client = client
        self.instance_id: str | None = None
        self.frame_count = 0
        self.last_error = ""
        # VTube Studio は絵の画素数に size を掛けた大きさで出す。コマを広く描いても
        # 心臓の画素の大きさは同じなので、心臓の見かけの大きさは size のまま変わらない
        self.size = size
        self.pins: dict[str, dict] = dict(pins or {})
        # VTube Studio の画面でドラッグして置いた所（留める場所が分からないとき、ここに出す）
        self.place = place
        # 休んでいる形のあとに足した「ぎゅっ」のコマの数（無ければ 0）
        self.squeeze_frames = squeeze_frames
        # VTube Studio の画面で手で体に置いた。VTube Studio が付けた場所（三角形）は正式版では
        # 聞けないので、作り直すと体から外れる（操作画面で知らせる）
        self.hand_placed = hand_placed
        # ItemEvent のうち心臓のもの以外（心拍数のアイテム）を渡す先と、知らせを受けるフォルダ
        self.item_files: list[str] = [ITEM_FOLDER]
        self.other_item_event: Callable[[dict], None] | None = None
        # 作り直す前に外して、その知らせで今の場所を読んでいる間は真
        self._reading_place = False
        # この時刻までは「ぎゅっ」のコマを流している（拍で 0 コマ目へ戻さない）と、流し始めた時刻
        self._squeeze_until = 0.0
        self._squeeze_at = -1.0
        # VTube Studio の画面で左ボタンを押した時刻とマウスの位置（クリックかドラッグかを見分ける）
        self._press: tuple[float, tuple[int, int]] | None = None
        self.model_id = ""
        # つないだ直後に場を調べ終えたら、心臓が場にあったかを渡す
        self.on_found: Callable[[bool], None] | None = None
        # VTube Studio の画面で心臓を動かし、覚えている場所（pins・place）が変わった
        self.on_moved: Callable[[], None] | None = None
        self._params_ready = False
        # この時刻まで、アイテムを落とした知らせは自分で留めた・外したもの（OWN_PIN_QUIET_S）
        self._quiet_until = 0.0
        self._pick_done: Callable[[dict | None], None] | None = None
        client.ready.connect(self._on_ready)
        client.state_changed.connect(self._on_state)

    @property
    def picking(self) -> bool:
        return self._pick_done is not None

    @property
    def _squeeze_count(self) -> int:
        """使える「ぎゅっ」のコマの数。保存した数が場のコマ数と合わなければ 0（拍のコマを守る）。"""
        count = self.squeeze_frames
        return count if 0 < count < self.frame_count - 1 else 0

    @property
    def rest_frame(self) -> int:
        """休んでいる形のコマ（拍のコマの最後。そのあとに「ぎゅっ」のコマが続く）。"""
        return max(0, self.frame_count - self._squeeze_count - 1)

    def _on_state(self, state: str) -> None:
        if state != READY:
            # 切れると、待っていた返事や知らせは来ない
            self._params_ready = False
            self._pick_done = None
            self._reading_place = False
            self._press = None
            self._squeeze_until = 0.0

    def _on_ready(self) -> None:
        self._client.subscribe("ModelLoadedEvent", {}, self._on_model)
        self._client.subscribe("ItemEvent", {"itemFileNames": self.item_files}, self._on_item_event)
        # 押した瞬間を知るため、モデルの外を押したときも受ける
        # （留める場所を選ぶクリックもこれで受ける）
        self._client.subscribe(
            "ModelClickedEvent", {"onlyClicksOnModel": False}, self._on_model_clicked
        )
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
        """VTube Studio の画面で心臓をクリックした・ドラッグして置いた。

        クリックは「ぎゅっ」。置いた所は覚え、見た目を変えて出し直しても同じ所に出す。
        モデルの上に落とすと VTube Studio が留めるが、留めた場所（ArtMesh の三角形）は知らせて
        こない。落とした所にある ArtMesh を聞いて覚える。聞けない版（正式版）では置いた所だけ覚え、
        手で体に置いたこと（hand_placed）を残す。
        """
        if data.get("itemFileName") not in (None, ITEM_FOLDER):
            if self.other_item_event is not None:
                self.other_item_event(data)
            return
        kind = data.get("itemEventType")
        if self.instance_id is None or data.get("itemInstanceID") != self.instance_id:
            return
        place = clean_place(data.get("itemPosition"))
        if self._reading_place and kind == DROPPED_UNPINNED:
            # 作り直す前に外したときの知らせ（今の心臓の場所）
            self._reading_place = False
            if place is not None:
                self.place = place
            return
        if kind in CLICKED:
            self.squeeze()
            return
        if kind not in (DROPPED_PINNED, DROPPED_UNPINNED) or place is None:
            return
        if time.monotonic() < self._quiet_until:
            return
        if self._was_click():
            # 心臓をクリックしただけ。VTube Studio は同じ所に留め直すので、覚えた場所はそのまま
            self.squeeze()
            return
        self.place = place
        # 前に覚えた場所へは戻さない（置き直した所が新しい場所）
        model = self.model_id
        self.pins.pop(model, None)
        self.hand_placed = kind == DROPPED_PINNED and bool(model)
        if not self.hand_placed:
            self._moved()
            return

        def got(reply: dict) -> None:
            pin = hit_pin(reply.get("artMeshHits"))
            if pin is not None and pin["modelID"] == model == self.model_id:
                self.pins[model] = pin
                self.hand_placed = False
            self._moved()

        self._client.request(
            "ArtMeshAtPositionRequest", {"x": place[0], "y": place[1], "visualize": 0}, got
        )

    def _on_model_clicked(self, data: dict) -> None:
        """VTube Studio の画面で押した（アイテム越しでも来る）。"""
        if self.picking:
            self._on_click(data)
        elif data.get("mouseButtonID") == 0:
            pos = QCursor.pos()
            self._press = (time.monotonic(), (pos.x(), pos.y()))

    def _was_click(self) -> bool:
        """今届いた「落とした」知らせが、ドラッグではなくクリック（押して、動かさずに離した）か。"""
        press, self._press = self._press, None
        if press is None:
            return False
        at, (x, y) = press
        pos = QCursor.pos()
        moved = abs(pos.x() - x) + abs(pos.y() - y)
        return time.monotonic() - at < CLICK_MAX_S and moved <= CLICK_MOVE_PX

    def _moved(self) -> None:
        if self.on_moved is not None:
            self.on_moved()

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

    def show_item(
        self,
        frame_count: int,
        done: Callable[[bool], None] | None = None,
        squeeze_frames: int = 0,
    ) -> None:
        """心臓アイテムを出し直す（新しいコマを読ませるため、出ていれば一度しまう）。

        squeeze_frames はコマの最後に足した「ぎゅっ」のコマの数。
        """
        self.frame_count = frame_count
        self.squeeze_frames = squeeze_frames
        self._squeeze_until = 0.0
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
                    "size": self.size,
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
            if not self.hand_placed:
                self._unload(lambda _data: load())
                return
            # 手で体に置いた心臓は、VTube Studio が付けた場所へは付け直せない。外したときの
            # 知らせで今の場所を読み（体の動きで、落とした所からずれていることがある）、
            # 新しい心臓をそこへ出す
            self._reading_place = True

            def unpinned(_reply: dict) -> None:
                self._reading_place = False
                self._unload(lambda _data: load())

            self._pin_request({"pin": False, "itemInstanceID": self.instance_id}, unpinned)

        self._find_instance(unload_then_load, rescan=True)

    def hide_item(self) -> None:
        """心臓アイテムをしまう。"""
        self._stop_pick()
        self._unload(None)
        self.instance_id = None
        self.hand_placed = False

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

    def _stops(self) -> list[int]:
        """止めるコマ: 休んでいる形（拍のコマの最後）と、「ぎゅっ」のコマの最後。"""
        return sorted({self.rest_frame, self.frame_count - 1})

    def _rest(self) -> None:
        """休んでいる形のコマで止めておく。"""
        if self.instance_id is None or self.frame_count <= 0:
            return
        self._client.request(
            "ItemAnimationControlRequest",
            {
                "itemInstanceID": self.instance_id,
                "framerate": -1,
                "frame": self.rest_frame,
                "brightness": -1,
                "opacity": -1,
                "setAutoStopFrames": True,
                "autoStopFrames": self._stops(),
                "setAnimationPlayState": True,
                "animationPlayState": False,
            },
        )

    def beat(self, framerate: float) -> None:
        """拍。最初のコマから再生し、休んでいる形のコマで止まる。「ぎゅっ」の途中は流さない。"""
        if self._client.state != READY or self.instance_id is None or self.frame_count <= 0:
            return
        if time.monotonic() < self._squeeze_until:
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
                "autoStopFrames": self._stops(),
                "setAnimationPlayState": True,
                "animationPlayState": True,
            },
            replied,
        )

    def squeeze(self) -> None:
        """心臓わしづかみの「ぎゅっ」のコマを流す（ほかの演出の心臓では何もしない）。"""
        count = self._squeeze_count
        if self._client.state != READY or self.instance_id is None or count <= 0:
            return
        last = self.frame_count - 1
        first = last - count + 1
        now = time.monotonic()
        if first <= 0 or now - self._squeeze_at < SQUEEZE_REPEAT_S:
            return
        self._squeeze_at = now
        self._squeeze_until = now + self.squeeze_frames / SQUEEZE_FPS
        self._client.request(
            "ItemAnimationControlRequest",
            {
                "itemInstanceID": self.instance_id,
                "framerate": SQUEEZE_FPS,
                "frame": first,
                "brightness": -1,
                "opacity": -1,
                "setAutoStopFrames": True,
                "autoStopFrames": [last],
                "setAnimationPlayState": True,
                "animationPlayState": True,
            },
        )

    # ------------------------------------------------------------ 留める・大きさ

    def _pin_saved(self) -> None:
        pin = self.pins.get(self.model_id)
        if pin is not None and self.instance_id is not None and not self.picking:
            self._pin(pin)
            if self.hand_placed:
                # 別のモデルへ切り替えて、そのモデルで覚えた場所に付けた
                self.hand_placed = False
                self._moved()

    def _pin(self, pin: dict, then: Reply | None = None) -> None:
        self._pin_request(
            {
                "pin": True,
                "itemInstanceID": self.instance_id,
                "angleRelativeTo": "RelativeToModel",
                "sizeRelativeTo": "RelativeToWorld",
                "vertexPinType": "Provided",
                "pinInfo": {**pin, "angle": 0, "size": self.size},
            },
            then,
        )

    def _pin_request(self, data: dict, then: Reply | None = None) -> None:
        """留める・外す。返ってくる「落とした」知らせを、手で置いたものと取り違えないようにする。"""
        self._quiet_until = time.monotonic() + OWN_PIN_QUIET_S

        def replied(reply: dict) -> None:
            self._quiet_until = max(self._quiet_until, time.monotonic() + OWN_PIN_QUIET_S)
            if then is not None:
                then(reply)

        self._client.request("ItemPinRequest", data, replied)

    def start_pick(self, done: Callable[[dict | None], None]) -> bool:
        """モデルをクリックした所へ心臓を留める。クリックを待ち、留めたら done(場所)。"""
        if self._client.state != READY or self.instance_id is None:
            return False
        self._pick_done = done
        # 手で体に置いた心臓は、外したときの知らせで今の場所を読む（やめたらそこへ戻す）
        self._reading_place = self.hand_placed

        def unpinned(_reply: dict) -> None:
            self._reading_place = False

        # 心臓がモデルに重なっているとクリックが心臓に当たるので、外して脇へ寄せる
        self._pin_request({"pin": False, "itemInstanceID": self.instance_id}, unpinned)
        self._move(x=PICK_ASIDE_X, y=0.0, seconds=0.3)
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
            if self.hand_placed:
                # 選ぶために外したので、もう体には付いていない（置いてあった所へ戻しただけ）
                self.hand_placed = False
                self._moved()

    def _stop_pick(self) -> None:
        self._pick_done = None

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
            self.hand_placed = False
            done(pin)

        self._pin(pin, pinned)

    def set_size(self, size: float) -> None:
        self.size = max(ITEM_SIZE_MIN, min(ITEM_SIZE_MAX, size))
        if self._client.state != READY or self.instance_id is None:
            return
        # 留めてあるときは、留め直しで大きさを渡す（覚えた場所に付け直すときと同じ値にそろえる）
        if self.pins.get(self.model_id) is not None and not self.picking:
            self._pin_saved()
        else:
            self._move(size=self.size)

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
