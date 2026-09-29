"""VTube Studio 連携。偽の VTube Studio（WebSocket サーバー）を立てて手順を確かめる。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocket, QWebSocketServer

from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.heart_frames import (
    FRAME_PREFIX,
    beat_cycles,
    count_frames,
    render_frames,
    write_frames,
)
from stream_heartbeat.vts import (
    DENIED,
    ITEM_FOLDER,
    PARAM_BEAT,
    READY,
    VtsClient,
    VtsHeart,
    clicked_pin,
    item_framerate,
)

HIT = {
    "modelID": "m1",
    "artMeshID": "D_BODY_00",
    "angle": 12.0,
    "size": 1.0,
    "vertexID1": 3,
    "vertexID2": 4,
    "vertexID3": 5,
    "vertexWeight1": 0.2,
    "vertexWeight2": 0.3,
    "vertexWeight3": 0.5,
}
PIN = {k: v for k, v in HIT.items() if k not in ("angle", "size")}


def click_event(hits: list[dict], button: int = 0) -> dict:
    return {"modelLoaded": True, "modelWasClicked": bool(hits), "mouseButtonID": button,
            "artMeshHits": hits}


class FakeVts(QObject):
    """必要な要求にだけ返事をする VTube Studio の代わり。"""

    def __init__(self, *, deny: bool = False) -> None:
        super().__init__()
        self.deny = deny
        # True なら、アイテムは VTube Studio 側で消された扱い
        self.item_gone = False
        self.received: list[dict] = []
        self._server = QWebSocketServer("fake-vts", QWebSocketServer.SslMode.NonSecureMode)
        assert self._server.listen(QHostAddress.SpecialAddress.LocalHost, 0)
        self._server.newConnection.connect(self._accept)
        self._sockets: list[QWebSocket] = []

    @property
    def port(self) -> int:
        return self._server.serverPort()

    def close(self) -> None:
        for socket in self._sockets:
            socket.close()
        self._server.close()

    def _accept(self) -> None:
        socket = self._server.nextPendingConnection()
        self._sockets.append(socket)
        socket.textMessageReceived.connect(lambda text, s=socket: self._reply(s, text))

    def types(self) -> list[str]:
        return [m["messageType"] for m in self.received]

    def sent(self, kind: str) -> list[dict]:
        return [m["data"] for m in self.received if m["messageType"] == kind]

    def push(self, kind: str, data: dict) -> None:
        """イベントを送る。"""
        payload = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
                   "requestID": "event", "messageType": kind, "data": data}
        for socket in self._sockets:
            socket.sendTextMessage(json.dumps(payload))

    def _reply(self, socket: QWebSocket, text: str) -> None:
        message = json.loads(text)
        self.received.append(message)
        kind = message["messageType"]
        data: dict = {}
        answer = kind.replace("Request", "Response")
        if kind == "AuthenticationTokenRequest":
            if self.deny:
                answer, data = "APIError", {"errorID": 50, "message": "User denied"}
            else:
                data = {"authenticationToken": "tok123"}
        elif kind == "AuthenticationRequest":
            ok = message["data"]["authenticationToken"] == "tok123"
            data = {"authenticated": ok, "reason": "" if ok else "bad token"}
        elif kind == "ItemListRequest":
            data = {"itemInstancesInScene": [], "availableItemFiles": []}
        elif kind == "ItemLoadRequest":
            data = {"instanceID": "inst1", "fileName": message["data"]["fileName"]}
        elif kind == "CurrentModelRequest":
            data = {"modelLoaded": True, "modelName": "Model", "modelID": "m1"}
        elif kind == "ItemPinRequest":
            data = {"isPinned": message["data"]["pin"], "itemInstanceID": "inst1"}
        elif kind == "ItemAnimationControlRequest" and self.item_gone:
            answer, data = "APIError", {"errorID": 850, "message": "not found"}
        payload = {"apiName": "VTubeStudioPublicAPI", "apiVersion": "1.0",
                   "requestID": message["requestID"], "messageType": answer, "data": data}
        socket.sendTextMessage(json.dumps(payload))


@pytest.fixture
def fake_vts(qapp):
    del qapp
    server = FakeVts()
    yield server
    server.close()


def test_client_asks_permission_then_authenticates(qtbot, fake_vts: FakeVts) -> None:
    client = VtsClient(port=fake_vts.port)
    tokens: list[str] = []
    client.token_changed.connect(tokens.append)
    client.start()
    qtbot.waitUntil(lambda: client.state == READY, timeout=3000)
    assert tokens == ["tok123"]
    assert fake_vts.types()[:2] == ["AuthenticationTokenRequest", "AuthenticationRequest"]
    client.stop()


def test_saved_token_skips_permission(qtbot, fake_vts: FakeVts) -> None:
    client = VtsClient(token="tok123", port=fake_vts.port)
    client.start()
    qtbot.waitUntil(lambda: client.state == READY, timeout=3000)
    assert "AuthenticationTokenRequest" not in fake_vts.types()
    client.stop()


def test_denied_permission_stops_asking(qtbot, qapp) -> None:
    del qapp
    server = FakeVts(deny=True)
    client = VtsClient(port=server.port)
    client.start()
    qtbot.waitUntil(lambda: client.state == DENIED, timeout=3000)
    qtbot.wait(200)
    assert server.types().count("AuthenticationTokenRequest") == 1
    client.stop()
    server.close()


def test_item_is_loaded_and_replayed_on_each_beat(qtbot, fake_vts: FakeVts) -> None:
    client = VtsClient(token="tok123", port=fake_vts.port)
    heart = VtsHeart(client)
    client.start()
    qtbot.waitUntil(lambda: client.state == READY, timeout=3000)
    shown: list[bool] = []
    heart.show_item(21, shown.append)
    qtbot.waitUntil(lambda: shown == [True], timeout=3000)
    load = next(m for m in fake_vts.received if m["messageType"] == "ItemLoadRequest")
    assert load["data"]["fileName"] == ITEM_FOLDER
    assert heart.instance_id == "inst1"
    heart.beat(36.0)
    heart.send_params(0.8, 88.0)
    qtbot.waitUntil(lambda: "InjectParameterDataRequest" in fake_vts.types(), timeout=3000)
    control = "ItemAnimationControlRequest"
    plays = [m["data"] for m in fake_vts.received if m["messageType"] == control]
    # 出した直後は休みのコマで止め、拍で 0 コマ目から流して最後のコマで止める
    assert plays[0]["frame"] == 20 and plays[0]["animationPlayState"] is False
    assert plays[-1]["frame"] == 0 and plays[-1]["animationPlayState"] is True
    assert plays[-1]["autoStopFrames"] == [20] and plays[-1]["framerate"] == 36.0
    inject = next(m for m in fake_vts.received if m["messageType"] == "InjectParameterDataRequest")
    assert inject["data"]["parameterValues"][0] == {"id": PARAM_BEAT, "value": 0.8}
    assert "ParameterCreationRequest" in fake_vts.types()
    client.stop()


def test_framerate_follows_systole_and_is_clamped() -> None:
    assert item_framerate(30.0, 0.30, 0.30) == pytest.approx(30.0)
    assert item_framerate(30.0, 0.20, 0.30) == pytest.approx(45.0)
    assert item_framerate(300.0, 0.05, 0.30) == 120.0


def test_frames_are_transparent_and_numbered(qapp, tmp_path: Path) -> None:
    del qapp
    frames = render_frames(HeartProfile(style="cute"), size=128)
    assert len(frames) == len(beat_cycles()) >= 15
    assert frames[0].pixelColor(1, 1).alpha() == 0
    assert frames[0].pixelColor(64, 70).alpha() > 200
    # 最初のコマは拍の瞬間、最後のコマは休んでいる形
    assert beat_cycles()[-1].squeeze == 0.0 and beat_cycles()[2].squeeze > 0.5
    assert render_frames(HeartProfile(style="echo")) == []
    folder = tmp_path / ITEM_FOLDER
    folder.mkdir()
    (folder / f"{FRAME_PREFIX}999.png").write_bytes(b"old")
    (folder / "leftover_001.png").write_bytes(b"old")
    assert write_frames(frames, folder, tag="t1") == len(frames)
    names = sorted(p.name for p in folder.iterdir())
    assert names[0] == f"{FRAME_PREFIX}t1_001.png" and len(names) == len(frames)
    assert not QImage(str(folder / names[0])).isNull()
    # 書き直すたびに名前を変える（VTube Studio は同じ名前なら前の絵を出し続けるため）
    write_frames(frames[:3], folder, tag="t2")
    assert sorted(p.name for p in folder.iterdir())[0] == f"{FRAME_PREFIX}t2_001.png"
    assert count_frames(folder) == 3 and count_frames(tmp_path / "none") == 0
    write_frames(frames[:2], folder)
    assert count_frames(folder) == 2
    assert not (folder / f"{FRAME_PREFIX}t2_001.png").exists()


def test_panel_plays_item_once_per_beat(qapp, tmp_path: Path) -> None:
    del qapp
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.vts_panel import VtsPanel

    session = HeartSession()
    for i in range(6):
        session.clock.feed_beat(i * 0.8)
    notices: list[str] = []
    panel = VtsPanel(session, tmp_path, notices.append)
    rates: list[float] = []
    panel._heart.beat = rates.append  # type: ignore[method-assign]
    panel._client._state = READY
    t = 4.0
    upcoming = [4.8, 5.6]
    while t < 6.0:
        if upcoming and t >= upcoming[0]:
            session.clock.feed_beat(upcoming.pop(0))
        panel.tick(t)
        t += 0.016
    # 4.0 秒の拍は既に始まっているので数えず、4.8・5.6 秒の 2 回だけ流す
    assert len(rates) == 2
    assert all(20.0 < r < 40.0 for r in rates)
    panel.shutdown()


def _ready_heart(qtbot, fake_vts: FakeVts, **kwargs) -> tuple[VtsClient, VtsHeart]:
    client = VtsClient(token="tok123", port=fake_vts.port)
    heart = VtsHeart(client, **kwargs)
    found: list[bool] = []
    heart.on_found = found.append
    client.start()
    qtbot.waitUntil(lambda: found == [False] and heart.model_id == "m1", timeout=3000)
    return client, heart


def test_clicked_place_pins_item_and_is_remembered(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts, size=0.25)
    shown: list[bool] = []
    heart.show_item(20, shown.append)
    qtbot.waitUntil(lambda: shown == [True], timeout=3000)
    # 覚えた場所が無いうちは、出しても留めない
    assert fake_vts.sent("ItemPinRequest") == []
    picked: list[dict | None] = []
    assert heart.start_pick(picked.append)
    qtbot.waitUntil(lambda: [s["eventName"] for s in fake_vts.sent("EventSubscriptionRequest")][-1:]
                    == ["ModelClickedEvent"], timeout=3000)
    # 選ぶあいだは外して脇へ寄せる。右クリックやモデルの外では決めない
    assert fake_vts.sent("ItemPinRequest")[0]["pin"] is False
    assert fake_vts.sent("ItemMoveRequest")[0]["itemsToMove"][0]["positionX"] < -0.5
    fake_vts.push("ModelClickedEvent", click_event([{"artMeshOrder": 0, "hitInfo": HIT}], button=1))
    fake_vts.push("ModelClickedEvent", click_event([]))
    fake_vts.push("ModelClickedEvent", click_event([
        {"artMeshOrder": 1, "hitInfo": {**HIT, "artMeshID": "D_BACK"}},
        {"artMeshOrder": 0, "hitInfo": HIT},
    ]))
    qtbot.waitUntil(lambda: picked == [PIN], timeout=3000)
    assert not heart.picking and heart.pins == {"m1": PIN}
    pin = fake_vts.sent("ItemPinRequest")[-1]
    assert pin["pin"] is True and pin["vertexPinType"] == "Provided"
    assert pin["pinInfo"] == {**PIN, "angle": 0, "size": 0.25}
    assert fake_vts.sent("EventSubscriptionRequest")[-1]["subscribe"] is False
    # 留めたあとの大きさは留め直しで変える（移動の要求では変わらない）
    heart.set_size(0.4)
    qtbot.waitUntil(lambda: fake_vts.sent("ItemPinRequest")[-1]["pinInfo"]["size"] == 0.4,
                    timeout=3000)
    client.stop()


def test_saved_place_is_used_when_item_is_shown_again(qtbot, fake_vts: FakeVts) -> None:
    pins = {"m1": PIN, "other": {**PIN, "modelID": "other"}}
    client, heart = _ready_heart(qtbot, fake_vts, size=0.2, pins=pins)
    shown: list[bool] = []
    heart.show_item(20, shown.append)
    qtbot.waitUntil(lambda: shown == [True] and bool(fake_vts.sent("ItemPinRequest")), timeout=3000)
    assert fake_vts.sent("ItemLoadRequest")[0]["size"] == 0.2
    assert fake_vts.sent("ItemPinRequest")[0]["pinInfo"]["artMeshID"] == "D_BODY_00"
    assert fake_vts.sent("ItemPinRequest")[0]["pinInfo"]["modelID"] == "m1"
    # モデルを読み込み直したら、そのモデル用の場所へ留め直す
    fake_vts.push("ModelLoadedEvent", {"modelLoaded": True, "modelName": "O", "modelID": "other"})
    qtbot.waitUntil(lambda: fake_vts.sent("ItemPinRequest")[-1]["pinInfo"]["modelID"] == "other",
                    timeout=3000)
    client.stop()


def test_item_removed_in_vts_is_forgotten(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts)
    heart.show_item(20)
    qtbot.waitUntil(lambda: heart.instance_id == "inst1", timeout=3000)
    fake_vts.item_gone = True
    heart.beat(30.0)
    qtbot.waitUntil(lambda: heart.instance_id is None, timeout=3000)
    client.stop()


def test_clicked_pin_rejects_broken_hits() -> None:
    assert clicked_pin(click_event([{"artMeshOrder": 0, "hitInfo": HIT}])) == PIN
    broken = {**HIT, "vertexID1": "x"}
    assert clicked_pin(click_event([{"artMeshOrder": 0, "hitInfo": broken}])) is None
    assert clicked_pin(click_event([{"artMeshOrder": 0, "hitInfo": HIT}], button=2)) is None
    assert clicked_pin({"modelWasClicked": True, "mouseButtonID": 0, "artMeshHits": None}) is None


def test_panel_restores_item_after_vts_restart(qapp, tmp_path: Path, monkeypatch) -> None:
    del qapp
    from stream_heartbeat.profile import load_app_state, save_app_state
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import VtsPanel

    items = tmp_path / "Items"
    write_frames(render_frames(HeartProfile(style="cute"), size=64)[:4], items / ITEM_FOLDER)
    monkeypatch.setattr(vts_panel, "find_items_dir", lambda: items)
    save_app_state(tmp_path, vts_item_shown=True, vts_item_size=5.0,
                   vts_pins={"m1": PIN, "bad": {"modelID": "bad"}})
    panel = VtsPanel(HeartSession(), tmp_path, lambda _text: None)
    assert panel._heart.pins == {"m1": PIN} and panel._heart.size == 0.8
    shows: list[int] = []
    panel._heart.show_item = lambda count, done=None: shows.append(count)  # type: ignore[method-assign]
    panel._on_found(True)
    assert shows == []
    panel._on_found(False)
    assert shows == [4]
    # 「しまう」を押したら、次につないでも出さない
    panel._hide_item()
    panel._on_found(False)
    assert shows == [4] and load_app_state(tmp_path)["vts_item_shown"] is False
    panel.shutdown()


def test_events_reach_subscriber_not_reply_handlers(qtbot, fake_vts: FakeVts) -> None:
    client = VtsClient(token="tok123", port=fake_vts.port)
    client.start()
    qtbot.waitUntil(lambda: client.state == READY, timeout=3000)
    events: list[dict] = []
    client.subscribe("TestEvent", {}, events.append)
    fake_vts.push("TestEvent", {"counter": 1})
    qtbot.waitUntil(lambda: events == [{"counter": 1}], timeout=3000)
    client.unsubscribe("TestEvent")
    fake_vts.push("TestEvent", {"counter": 2})
    qtbot.wait(100)
    assert events == [{"counter": 1}]
    client.stop()
