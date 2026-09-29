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
    item_framerate,
)


class FakeVts(QObject):
    """必要な要求にだけ返事をする VTube Studio の代わり。"""

    def __init__(self, *, deny: bool = False) -> None:
        super().__init__()
        self.deny = deny
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
    assert write_frames(frames, folder) == len(frames)
    names = sorted(p.name for p in folder.iterdir())
    assert names[0] == f"{FRAME_PREFIX}001.png" and len(names) == len(frames)
    assert not QImage(str(folder / names[0])).isNull()


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
