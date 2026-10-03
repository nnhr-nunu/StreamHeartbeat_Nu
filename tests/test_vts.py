"""VTube Studio 連携。偽の VTube Studio（WebSocket サーバー）を立てて手順を確かめる。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocket, QWebSocketServer

from stream_heartbeat import vts
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
    find_items_dir,
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
        # 場に出ているアイテム（ItemListRequest の返事）
        self.scene: list[dict] = []
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
            data = {"itemInstancesInScene": self.scene, "availableItemFiles": []}
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


def test_mac_steam_items_folder_inside_app_is_found(tmp_path: Path, monkeypatch) -> None:
    """Mac の Steam 版は、アイテムのフォルダが VTube Studio のアプリ（.app）の中にある。"""
    steam = tmp_path / "Library" / "Application Support" / "Steam"
    items = (
        steam
        / "steamapps/common/VTube Studio/VTube Studio.app/Contents/Resources/Data"
        / "StreamingAssets/Items"
    )
    items.mkdir(parents=True)
    monkeypatch.setattr(vts.sys, "platform", "darwin")
    monkeypatch.setattr(vts.Path, "home", lambda: tmp_path)
    assert find_items_dir() == items


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
    from stream_heartbeat.ui.vts_panel import VtsPanel, look_key

    items = tmp_path / "Items"
    write_frames(render_frames(HeartProfile(style="cute"), size=64)[:4], items / ITEM_FOLDER)
    monkeypatch.setattr(vts_panel, "find_items_dir", lambda: items)
    session = HeartSession()
    session.profile.style = "cute"
    save_app_state(tmp_path, vts_item_shown=True, vts_item_size=5.0,
                   vts_pins={"m1": PIN, "bad": {"modelID": "bad"}},
                   vts_item_look=list(look_key(session.profile)))
    panel = VtsPanel(session, tmp_path, lambda _text: None)
    assert panel._heart.pins == {"m1": PIN} and panel._heart.size == 0.8
    shows: list[int] = []
    panel._heart.show_item = lambda count, done=None: shows.append(count)  # type: ignore[method-assign]
    panel._on_found(True)
    assert shows == []
    panel._on_found(False)
    assert shows == [4]
    # 書き出してあるコマと見た目が違えば、前の絵を出さずに今の見た目で作り直して出す
    made: list[bool] = []
    panel._make_item = lambda auto=False: made.append(auto)  # type: ignore[method-assign]
    session.profile.effect = "grip"
    panel._on_found(False)
    assert shows == [4] and made == [True]
    # 「しまう」を押したら、次につないでも出さない
    panel._hide_item()
    panel._on_found(False)
    assert shows == [4] and made == [True]
    assert load_app_state(tmp_path)["vts_item_shown"] is False
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


def test_cancel_pick_without_saved_place_returns_home(qtbot, fake_vts: FakeVts) -> None:
    from stream_heartbeat.vts import ITEM_HOME

    client, heart = _ready_heart(qtbot, fake_vts)
    shown: list[bool] = []
    heart.show_item(20, shown.append)
    qtbot.waitUntil(lambda: shown == [True], timeout=3000)
    assert heart.start_pick(lambda _pin: None)
    heart.cancel_pick()
    # 脇へ寄せたままにせず、出したときの位置へ戻す（覚えた場所が無いので留めない）
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemMoveRequest")) == 2, timeout=3000)
    back = fake_vts.sent("ItemMoveRequest")[-1]["itemsToMove"][0]
    assert (back["positionX"], back["positionY"]) == ITEM_HOME
    assert not any(pin["pin"] for pin in fake_vts.sent("ItemPinRequest"))
    client.stop()


def test_panel_denied_unchecks_and_is_remembered(qapp, tmp_path: Path) -> None:
    del qapp
    from stream_heartbeat.profile import load_app_state
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.vts_panel import STATE_LABELS, VtsPanel

    panel = VtsPanel(HeartSession(), tmp_path, lambda _text: None)
    panel._enable.blockSignals(True)
    panel._enable.setChecked(True)
    panel._enable.blockSignals(False)
    panel._on_state(DENIED)
    # 次に起動したときに勝手に聞き直さないよう、外したことを覚える。理由は見えるように残す
    assert not panel._enable.isChecked()
    assert load_app_state(tmp_path)["vts_enabled"] is False
    assert not panel._status.isHidden() and panel._status.text() == STATE_LABELS[DENIED]
    assert panel._status.objectName() == "warn"
    panel.shutdown()


def test_panel_buttons_and_note_follow_connection_and_look(qapp, tmp_path: Path) -> None:
    del qapp
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import VtsPanel, look_key

    session = HeartSession()
    profile = session.profile
    profile.style = "realistic"
    panel = VtsPanel(session, tmp_path, lambda _text: None)
    # つながるまでは押せない
    assert not panel._item_btn.isEnabled() and not panel._pin_btn.isEnabled()
    panel._client._state = READY
    panel._refresh()
    assert panel._item_btn.isEnabled() and panel._item_btn.text() == vts_panel.SHOW_BUTTON
    assert not panel._pin_btn.isEnabled() and not panel._hide_btn.isEnabled()
    assert panel._note.text() == vts_panel.NOTE_NOT_SHOWN
    # 出したら作り直し・留める・しまうを押せる
    panel._heart.instance_id = "inst1"
    panel._made_key = look_key(profile)
    panel._refresh()
    assert panel._item_btn.text() == vts_panel.REMAKE_BUTTON
    assert panel._pin_btn.isEnabled() and panel._hide_btn.isEnabled()
    assert panel._note.text() == vts_panel.NOTE_UNPINNED
    # 向きを変えたら、少し待って作り直すことを知らせる。自動で作り直せなければ押してもらう
    profile.heart_yaw_deg += 20.0
    panel._refresh()
    assert panel._note.text() == vts_panel.NOTE_STALE and panel._note.objectName() == "meta"
    panel._failed_key = look_key(profile)
    panel._refresh()
    assert panel._note.text() == vts_panel.NOTE_STALE_FAILED and panel._note.objectName() == "warn"
    # アイテムにできないスタイルでは出せない
    profile.style = "echo"
    panel._refresh()
    assert panel._note.text() == vts_panel.NOTE_BAD_STYLE and not panel._item_btn.isEnabled()
    profile.style = "realistic"
    panel._made_key = look_key(profile)
    panel._heart.model_id = "m1"
    panel._heart.pins = {"m1": PIN}
    panel._refresh()
    assert panel._note.text() == vts_panel.NOTE_PINNED and panel._note.objectName() == "meta"
    panel.shutdown()


def test_panel_folder_must_be_items(qapp, tmp_path: Path, monkeypatch) -> None:
    del qapp
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import NOT_ITEMS_NOTICE, VtsPanel

    notices: list[str] = []
    panel = VtsPanel(HeartSession(), tmp_path, notices.append)
    assets = tmp_path / "StreamingAssets"
    (assets / "Items").mkdir(parents=True)
    other = tmp_path / "Desktop"
    other.mkdir()
    picks = iter([str(assets), str(other)])
    monkeypatch.setattr(
        vts_panel.QFileDialog, "getExistingDirectory", lambda *_args, **_kw: next(picks)
    )
    # 一つ上を選んだら中の Items を使う
    panel._choose_folder()
    assert panel._items_dir == assets / "Items"
    # 関係ないフォルダは受け付けない
    panel._choose_folder()
    assert panel._items_dir == assets / "Items" and notices == [NOT_ITEMS_NOTICE]
    panel.shutdown()


def test_panel_guides_are_side_by_side_and_open_one_at_a_time(qapp, tmp_path: Path) -> None:
    del qapp
    from PySide6.QtWidgets import QToolButton

    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.vts_panel import API_SWITCH, HOW_TO, TROUBLE, VtsPanel

    panel = VtsPanel(HeartSession(), tmp_path, lambda _text: None)
    how_to, trouble = panel.findChildren(QToolButton)
    assert "使い方" in how_to.text() and "上手くいかない時" in trouble.text()
    assert how_to.parentWidget() is trouble.parentWidget()
    # VTube Studio の画面にあるスイッチの名前どおりに案内する
    assert API_SWITCH in HOW_TO and API_SWITCH in TROUBLE and "【次からは】" in HOW_TO
    # 押すボタンの名前は、画面のボタンと同じ文字で案内する
    for button in (panel._item_btn, panel._pin_btn, panel._hide_btn, panel._params):
        assert f"「{button.text()}」" in HOW_TO
    how_to.setChecked(True)
    trouble.setChecked(True)
    assert trouble.isChecked() and not how_to.isChecked()
    panel.shutdown()


def test_panel_explains_where_to_click_while_waiting(qapp, tmp_path: Path) -> None:
    del qapp
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import VtsPanel

    session = HeartSession()
    session.profile.style = "realistic"
    panel = VtsPanel(session, tmp_path, lambda _text: None)
    panel._client._state = READY
    panel._heart.instance_id = "inst1"
    panel._heart._pick_done = lambda _pin: None
    panel._refresh()
    # 知らせはすぐ消えるので、クリックを待つあいだはどこを押すかを出し続ける
    assert panel._note.text() == vts_panel.NOTE_PICKING
    assert "VTube Studio の画面" in panel._note.text() and "左クリック" in panel._note.text()
    assert panel._pin_btn.text() == vts_panel.PICKING_BUTTON
    panel._heart._pick_done = None
    panel.shutdown()


def test_item_style_names_follow_the_style_list() -> None:
    from stream_heartbeat.render.heart_frames import ITEM_STYLES
    from stream_heartbeat.ui.vts_panel import ITEM_STYLE_NAMES, style_names

    # オシャレ1・2 も出せるのに案内から漏れていたので、一覧から作る
    assert ITEM_STYLE_NAMES == style_names(ITEM_STYLES)
    assert ITEM_STYLE_NAMES == "リアル1〜3、レントゲン3、かわいい1・2、オシャレ1・2、機械"


def test_look_key_follows_effect_and_stethoscope_place() -> None:
    from stream_heartbeat.ui.vts_panel import look_key

    profile = HeartProfile(style="realistic", heart_yaw_deg=30.0)
    plain = look_key(profile)
    profile.effect = "burst"
    assert look_key(profile) != plain
    # 掴んでいる間は正面から描くので、向きを変えても作り直さない
    profile.effect = "grip"
    held = look_key(profile)
    profile.heart_yaw_deg = -40.0
    assert look_key(profile) == held
    # 聴診器は当てる所が変われば作り直す（小さなずれでは作り直さない）
    profile.effect = "stethoscope"
    assert look_key(profile, (0.3, 0.2)) != look_key(profile, (-0.5, 0.2))
    assert look_key(profile, (0.3, 0.2)) == look_key(profile, (0.31, 0.21))
    assert look_key(HeartProfile(style="cute"), (0.3, 0.2)) == look_key(HeartProfile(style="cute"))
    # 演出が選べないスタイルの演出は、絵に入らない
    assert look_key(HeartProfile(style="realistic", effect="doppler")) == look_key(
        HeartProfile(style="realistic")
    )
    # 保存して読み直しても同じ
    key = look_key(profile, (0.3, 0.2))
    assert tuple(json.loads(json.dumps(list(key)))) == key


def test_frames_carry_the_effect(qapp) -> None:
    del qapp
    from stream_heartbeat.render.heart_frames import FRAME_SECONDS

    plain = render_frames(HeartProfile(style="cute"), size=128)
    gripped = render_frames(HeartProfile(style="cute", effect="grip"), size=128)
    assert len(gripped) == len(plain)
    assert gripped[0] != plain[0] and gripped[-1] != plain[-1]
    # 聴診器は当てる所に描く
    left = render_frames(HeartProfile(style="cute", effect="stethoscope"), 128, (-0.5, 0.0))
    right = render_frames(HeartProfile(style="cute", effect="stethoscope"), 128, (0.5, 0.0))
    assert left[0] != right[0]
    # はじけるハートは消えきるまでコマにし、休んでいる形には残さない
    burst = render_frames(HeartProfile(style="cute", effect="burst"), size=128)
    assert len(burst) > len(plain) > int(FRAME_SECONDS * 30)
    assert burst[-1] == plain[-1]
    # 手や管は下端へ向けて薄くし、コマの下端で切れて見えないようにする
    bottom = gripped[0].height() - 1
    assert all(gripped[0].pixelColor(x, bottom).alpha() < 30 for x in range(0, 128, 4))


def test_heart_offset_round_trip_and_reach(qapp) -> None:
    del qapp
    from PySide6.QtCore import QPointF

    from stream_heartbeat.ui.effects import HeartFrame, heart_offset, point_from_heart

    frame = HeartFrame(center=QPointF(100.0, 80.0), half_w=40.0, half_h=60.0)
    offset = heart_offset(frame, QPointF(125.0, 30.0))
    assert offset == pytest.approx((0.5, -1.0))
    back = point_from_heart(frame, offset)
    assert (back.x(), back.y()) == pytest.approx((125.0, 30.0))
    # 遠すぎる所は心臓の方へ寄せる
    near = point_from_heart(frame, (3.0, 4.0), reach=1.0)
    assert (near.x(), near.y()) == pytest.approx((130.0, 120.0))


def test_panel_remakes_after_the_look_settles(qtbot, tmp_path: Path, monkeypatch) -> None:
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import REMAKE_WAIT_S, VtsPanel, look_key

    now = [100.0]
    monkeypatch.setattr(vts_panel.time, "monotonic", lambda: now[0])
    session = HeartSession()
    profile = session.profile
    profile.style = "cute"
    panel = VtsPanel(session, tmp_path, lambda _text: None, lambda: (0.4, 0.1))
    qtbot.addWidget(panel)
    made: list[bool] = []
    panel._make_item = lambda auto=False: made.append(auto)  # type: ignore[method-assign]
    panel._client._state = READY
    panel._heart.instance_id = "inst1"
    panel._made_key = look_key(profile)
    panel._auto_remake()
    assert made == []
    # 見た目を変えても、続けて変えている間は待つ
    profile.effect = "stethoscope"
    panel._auto_remake()
    now[0] += REMAKE_WAIT_S * 0.5
    profile.style = "chic"
    panel._auto_remake()
    now[0] += REMAKE_WAIT_S * 0.8
    panel._auto_remake()
    assert made == []
    now[0] += REMAKE_WAIT_S * 0.5
    panel._auto_remake()
    assert made == [True]
    # 聴診器の所は配信用の窓に聞く
    assert look_key(profile, (0.4, 0.1)) == panel._look_key() != look_key(profile)
    # 作り直している間・失敗した見た目・出していないときは作り直さない
    panel._busy = True
    now[0] += REMAKE_WAIT_S * 2
    panel._auto_remake()
    now[0] += REMAKE_WAIT_S * 2
    panel._auto_remake()
    panel._busy = False
    panel._failed_key = panel._look_key()
    panel._auto_remake()
    now[0] += REMAKE_WAIT_S * 2
    panel._auto_remake()
    panel._failed_key = None
    panel._heart.instance_id = None
    panel._auto_remake()
    now[0] += REMAKE_WAIT_S * 2
    panel._auto_remake()
    assert made == [True]
    panel.shutdown()


def test_panel_remakes_item_in_vts_when_the_effect_changes(
    qtbot, fake_vts: FakeVts, tmp_path: Path, monkeypatch
) -> None:
    from functools import partial

    from stream_heartbeat.profile import load_app_state, save_app_state
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import VtsPanel, look_key

    items = tmp_path / "Items"
    items.mkdir()
    monkeypatch.setattr(vts_panel, "find_items_dir", lambda: items)
    monkeypatch.setattr(vts_panel, "VtsClient", partial(VtsClient, port=fake_vts.port))
    monkeypatch.setattr(vts_panel, "REMAKE_WAIT_S", 0.0)
    save_app_state(tmp_path, vts_token="tok123")
    session = HeartSession()
    session.profile.style = "cute"
    notices: list[str] = []
    panel = VtsPanel(session, tmp_path, notices.append)
    qtbot.addWidget(panel)
    panel._enable.setChecked(True)
    qtbot.waitUntil(lambda: panel._client.state == READY, timeout=3000)
    panel._make_item()
    qtbot.waitUntil(lambda: panel._heart.instance_id == "inst1" and not panel._busy, timeout=3000)
    first = sorted(path.name for path in (items / ITEM_FOLDER).glob("*.png"))
    # 演出を変えたら、押さなくても今の見た目で書き直して出し直す
    session.profile.effect = "grip"
    panel.tick(0.0)
    panel.tick(0.0)
    qtbot.waitUntil(
        lambda: len(fake_vts.sent("ItemLoadRequest")) == 2 and not panel._busy, timeout=3000
    )
    assert sorted(path.name for path in (items / ITEM_FOLDER).glob("*.png")) != first
    assert panel._made_key == look_key(session.profile)
    assert load_app_state(tmp_path)["vts_item_look"] == list(look_key(session.profile))
    assert notices[-1] == vts_panel.REMADE_NOTICE
    panel.shutdown()


def test_show_item_keeps_the_new_frame_count(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts)
    # 前に出した（コマ数の違う）アイテムが場にある
    fake_vts.scene = [{"instanceID": "old1", "fileName": ITEM_FOLDER, "frameCount": 20}]
    shown: list[bool] = []
    heart.show_item(28, shown.append)
    qtbot.waitUntil(lambda: shown == [True], timeout=3000)
    # しまう前のコマ数ではなく、新しいコマの最後（休んでいる形）で止める
    assert heart.frame_count == 28
    rest = fake_vts.sent("ItemAnimationControlRequest")[-1]
    assert rest["frame"] == 27 and rest["autoStopFrames"] == [27]
    client.stop()
