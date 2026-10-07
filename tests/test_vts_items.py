"""VTube Studio 連携: 「ぎゅっ」・手で体に置いた心臓・心拍数の数字のアイテム。"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from stream_heartbeat import vts
from stream_heartbeat.config import MAX_BPM, MIN_BPM
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.render.bpm_frames import bpm_frame_index, render_bpm_frames
from stream_heartbeat.render.heart_frames import render_frames, squeeze_frame_count, squeeze_grips
from stream_heartbeat.vts import ITEM_FOLDER, VtsClient
from stream_heartbeat.vts_bpm import BPM_FOLDER, VtsBpm
from test_vts import HIT, PIN, FakeVts, _ready_heart, click_event, drop_event


@pytest.fixture
def fake_vts(qapp):
    del qapp
    server = FakeVts()
    yield server
    server.close()


def _event(kind: str, file: str = ITEM_FOLDER, instance: str = "inst1") -> dict:
    return {"itemEventType": kind, "itemInstanceID": instance, "itemFileName": file,
            "itemPosition": {"x": 0.3, "y": -0.2}}


def test_squeeze_grips_close_like_a_click_and_open_again() -> None:
    grips = squeeze_grips()
    peak = grips.index(max(grips))
    # 配信用の窓で 1 回クリックしたときのように、すぐ握り込んでから緩め、休んでいる形で終わる
    assert grips[0] > 0.3 and grips[peak] > 0.9 and grips[-1] == 0.0
    assert all(a <= b for a, b in pairwise(grips[: peak + 1]))
    assert all(a >= b for a, b in pairwise(grips[peak:]))
    assert 20 <= len(grips) <= 40


def test_grip_frames_end_with_the_squeeze_frames(qapp) -> None:
    del qapp
    grip = HeartProfile(style="cute", effect="grip")
    plain = render_frames(grip, size=64)
    squeezed = render_frames(grip, size=64, squeeze=True)
    assert squeeze_frame_count(grip) == len(squeeze_grips())
    assert len(squeezed) == len(plain) + squeeze_frame_count(grip)
    # 拍のコマはそのまま。「ぎゅっ」の山のコマは休んでいる形と違う（手が握り、心臓が潰れる）
    assert all(a == b for a, b in zip(plain, squeezed, strict=False))
    peak = len(plain) + squeeze_grips().index(max(squeeze_grips()))
    assert squeezed[peak] != plain[-1]
    # 心臓わしづかみ以外は足さない
    other = HeartProfile(style="cute", effect="burst")
    assert squeeze_frame_count(other) == 0
    assert len(render_frames(other, size=64, squeeze=True)) == len(render_frames(other, size=64))


def test_click_on_the_heart_plays_the_squeeze(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts)
    heart.show_item(30, squeeze_frames=10)
    qtbot.waitUntil(lambda: heart.instance_id == "inst1", timeout=3000)
    controls = fake_vts.sent
    # 休んでいる形は拍のコマの最後（「ぎゅっ」のコマの手前）
    rest = controls("ItemAnimationControlRequest")[-1]
    assert rest["frame"] == 19 and rest["autoStopFrames"] == [19, 29]
    fake_vts.push("ItemEvent", _event("Clicked"))
    qtbot.waitUntil(lambda: len(controls("ItemAnimationControlRequest")) == 2, timeout=3000)
    squeeze = controls("ItemAnimationControlRequest")[-1]
    assert squeeze["frame"] == 20 and squeeze["autoStopFrames"] == [29]
    assert squeeze["animationPlayState"] is True and squeeze["framerate"] == 30.0
    # 「ぎゅっ」の途中に来た拍では 0 コマ目へ戻さない
    heart.beat(25.0)
    qtbot.wait(100)
    assert len(controls("ItemAnimationControlRequest")) == 2
    # 終わったら拍は休んでいる形で止まる
    heart._squeeze_until = 0.0
    heart.beat(25.0)
    qtbot.waitUntil(lambda: len(controls("ItemAnimationControlRequest")) == 3, timeout=3000)
    beat = controls("ItemAnimationControlRequest")[-1]
    assert beat["frame"] == 0 and beat["autoStopFrames"] == [19, 29]
    # ほかの演出の心臓（「ぎゅっ」のコマが無い）ではクリックしても何もしない
    heart.squeeze_frames = 0
    fake_vts.push("ItemEvent", _event("Clicked"))
    qtbot.wait(150)
    assert len(controls("ItemAnimationControlRequest")) == 3
    client.stop()


def test_heart_put_on_the_body_by_hand_is_remade_where_it_is(
    qtbot, fake_vts: FakeVts, monkeypatch
) -> None:
    # 出したときに留めた知らせを聞き流す間を待たずに、ドラッグの知らせを送る
    monkeypatch.setattr(vts, "OWN_PIN_QUIET_S", 0.0)
    client, heart = _ready_heart(qtbot, fake_vts, pins={"m1": PIN})
    moved: list[bool] = []
    heart.on_moved = lambda: moved.append(True)
    heart.show_item(20)
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemPinRequest")) == 1, timeout=3000)
    # 正式版は落とした所の ArtMesh を聞けない: 置いた所だけ覚え、手で体に置いたことを残す
    fake_vts.push("ItemEvent", drop_event("DroppedPinned", 0.1, 0.2))
    qtbot.waitUntil(lambda: moved == [True], timeout=3000)
    assert heart.hand_placed and heart.pins == {} and heart.place == (0.1, 0.2)
    # 作り直すときは、外した知らせで今の場所（体の動きでずれている）を読んで、そこに出す
    fake_vts.echo_pins = True
    fake_vts.scene = [{"instanceID": "inst1", "fileName": ITEM_FOLDER, "frameCount": 20}]
    heart.show_item(20)
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemLoadRequest")) == 2, timeout=3000)
    kinds = [k for k in fake_vts.types() if k in ("ItemPinRequest", "ItemUnloadRequest")]
    assert kinds[-2:] == ["ItemPinRequest", "ItemUnloadRequest"]
    assert fake_vts.sent("ItemPinRequest")[-1]["pin"] is False
    load = fake_vts.sent("ItemLoadRequest")[-1]
    assert (load["positionX"], load["positionY"]) == (-0.1, 0.4)
    # 外して出し直したので、もう体に置いた扱いではない（「付ける場所を選ぶ」へ進む案内になる）
    assert heart.place == (-0.1, 0.4) and not heart.hand_placed and moved == [True]
    heart.hand_placed = True
    # クリックで体に付け直したら、手で置いた扱いは消える
    picked: list[dict | None] = []
    fake_vts.echo_pins = False
    assert heart.start_pick(picked.append)
    fake_vts.push("ModelClickedEvent", click_event([{"artMeshOrder": 0, "hitInfo": HIT}]))
    qtbot.waitUntil(lambda: picked == [PIN], timeout=3000)
    assert not heart.hand_placed
    # 体の外へ置き直したときも、手で体に置いた扱いにはしない
    fake_vts.push("ItemEvent", drop_event("DroppedUnpinned", 0.6, 0.0))
    qtbot.waitUntil(lambda: heart.place == (0.6, 0.0), timeout=3000)
    assert not heart.hand_placed
    client.stop()


def test_bpm_frames_have_one_frame_per_heart_rate(qapp) -> None:
    del qapp
    frames = render_bpm_frames(HeartProfile())
    assert len(frames) == MAX_BPM - MIN_BPM + 1
    assert len({(f.width(), f.height()) for f in frames}) == 1
    assert frames[0].pixelColor(0, 0).alpha() == 0
    assert render_bpm_frames(HeartProfile(bpm_scale=2.0))[0].height() > frames[0].height()
    assert bpm_frame_index(5) == 0
    assert bpm_frame_index(72.4) == 72 - MIN_BPM
    assert bpm_frame_index(999) == MAX_BPM - MIN_BPM


def test_bpm_item_shows_the_frame_of_the_heart_rate(qtbot, fake_vts: FakeVts) -> None:
    client = VtsClient(token="tok123", port=fake_vts.port)
    bpm = VtsBpm(client, size=0.25, place=(0.5, -0.5))
    found: list[bool] = []
    bpm.on_found = found.append
    client.start()
    qtbot.waitUntil(lambda: found == [False], timeout=3000)
    shown: list[bool] = []
    bpm.show(shown.append)
    qtbot.waitUntil(lambda: shown == [True], timeout=3000)
    load = fake_vts.sent("ItemLoadRequest")[-1]
    assert load["fileName"] == BPM_FOLDER and load["size"] == 0.25
    assert (load["positionX"], load["positionY"]) == (0.5, -0.5)
    # 心拍数が変わったときだけ、そのコマを出す（流さない）
    bpm.set_bpm(72)
    bpm.set_bpm(72.2)
    bpm.set_bpm(80)
    sent = fake_vts.sent
    qtbot.waitUntil(lambda: len(sent("ItemAnimationControlRequest")) == 2, timeout=3000)
    frames = sent("ItemAnimationControlRequest")
    assert [f["frame"] for f in frames] == [72 - MIN_BPM, 80 - MIN_BPM]
    assert all(f["animationPlayState"] is False for f in frames)
    # VTube Studio の画面で動かした所を覚える（ほかのアイテムの知らせでは動かない）
    moved: list[bool] = []
    bpm.on_moved = lambda: moved.append(True)
    bpm.on_item_event(_event("DroppedUnpinned", BPM_FOLDER, instance="other"))
    bpm.on_item_event(_event("DroppedPinned", BPM_FOLDER))
    assert moved == [True] and bpm.place == (0.3, -0.2)
    bpm.set_size(0.4)
    qtbot.waitUntil(lambda: bool(sent("ItemMoveRequest")), timeout=3000)
    assert sent("ItemMoveRequest")[-1]["itemsToMove"][0]["size"] == 0.4
    client.stop()


def test_heart_passes_other_item_events_on(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts)
    others: list[dict] = []
    heart.other_item_event = others.append
    heart.show_item(20)
    qtbot.waitUntil(lambda: heart.instance_id == "inst1", timeout=3000)
    # 同じ番号でも、心拍数のアイテムの知らせは心臓の「ぎゅっ」や置き場所に使わない
    fake_vts.push("ItemEvent", _event("DroppedUnpinned", BPM_FOLDER))
    qtbot.waitUntil(lambda: len(others) == 1, timeout=3000)
    assert heart.place is None
    client.stop()


def test_panel_bpm_check_shows_and_hides_the_number(qapp, tmp_path: Path, monkeypatch) -> None:
    del qapp
    from stream_heartbeat.profile import load_app_state
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.vts_panel import VtsPanel

    panel = VtsPanel(HeartSession(), tmp_path, lambda _text: None)
    control = panel._bpm
    # 心臓の知らせのフォルダに心拍数のアイテムも入れ、知らせを心拍数のアイテムへ渡す
    assert BPM_FOLDER in panel._heart.item_files
    assert panel._heart.other_item_event == control.bpm.on_item_event
    made: list[bool] = []
    hidden: list[bool] = []
    monkeypatch.setattr(control, "make", lambda notice=False: made.append(notice))
    monkeypatch.setattr(control.bpm, "hide", lambda: hidden.append(True))
    # つながっていない間は覚えるだけ
    control.check.setChecked(True)
    assert load_app_state(tmp_path)["vts_bpm_shown"] is True and made == []
    panel._client._state = vts.READY
    control.check.setChecked(False)
    control.check.setChecked(True)
    assert hidden == [True] and made == [True]
    # つないだとき場に無ければ出し直す
    control._on_found(False)
    assert made == [True, False]
    # 数字の大きさは心臓とは別のつまみで変え、覚える（心臓の「大きさ」では変わらない）
    sizes: list[float] = []
    monkeypatch.setattr(control.bpm, "set_size", sizes.append)
    panel._size.setValue(40)
    assert sizes == []
    assert control._size_wrap.isVisibleTo(control.box)
    control.size.setValue(55)
    assert sizes == [0.55] and load_app_state(tmp_path)["vts_bpm_size"] == control.bpm.size
    # 出すのをやめている間は、数字の大きさのつまみを畳む
    control.check.setChecked(False)
    assert not control._size_wrap.isVisibleTo(control.box)
    panel._client._state = vts.OFF
    panel.shutdown()


def test_long_press_without_moving_is_a_click(qtbot, fake_vts: FakeVts, monkeypatch) -> None:
    # 選んで付けた心臓を、動かさずに長く押しても（VTube Studio が「落とした」と知らせても）、
    # ドラッグではなく「ぎゅっ」として扱い、付けた場所を忘れない
    monkeypatch.setattr(vts, "OWN_PIN_QUIET_S", 0.0)
    client, heart = _ready_heart(qtbot, fake_vts, pins={"m1": PIN})
    heart.show_item(30, squeeze_frames=10)
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemPinRequest")) == 1, timeout=3000)
    fake_vts.push("ModelClickedEvent", click_event([{"artMeshOrder": 0, "hitInfo": HIT}]))
    qtbot.waitUntil(lambda: heart._press is not None, timeout=3000)
    heart._press = (heart._press[0] - 1.5, heart._press[1])
    fake_vts.push("ItemEvent", drop_event("DroppedPinned", 0.1, 0.2))
    qtbot.waitUntil(lambda: fake_vts.sent("ItemAnimationControlRequest")[-1]["frame"] == 20,
                    timeout=3000)
    assert heart.pins == {"m1": PIN} and not heart.hand_placed and heart.place is None
    client.stop()


def test_disconnect_forgets_waiting_state(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts)
    heart._reading_place = True
    heart._press = (1.0, (0, 0))
    heart._squeeze_until = 1e9
    client.stop()
    assert not heart._reading_place and heart._press is None and heart._squeeze_until == 0.0


def test_saved_squeeze_count_must_fit_the_frames(qtbot, fake_vts: FakeVts) -> None:
    client, heart = _ready_heart(qtbot, fake_vts)
    heart.show_item(30, squeeze_frames=40)
    qtbot.waitUntil(lambda: heart.instance_id == "inst1", timeout=3000)
    # 保存した数が場のコマ数と合わなければ、全部を拍のコマとして使う（拍で心臓が止まらない）
    rest = fake_vts.sent("ItemAnimationControlRequest")[-1]
    assert rest["frame"] == 29 and rest["autoStopFrames"] == [29]
    fake_vts.push("ItemEvent", _event("Clicked"))
    qtbot.wait(150)
    assert len(fake_vts.sent("ItemAnimationControlRequest")) == 1
    client.stop()


def test_cancel_pick_of_a_hand_placed_heart(qtbot, fake_vts: FakeVts, monkeypatch) -> None:
    monkeypatch.setattr(vts, "OWN_PIN_QUIET_S", 0.0)
    client, heart = _ready_heart(qtbot, fake_vts)
    moved: list[bool] = []
    heart.on_moved = lambda: moved.append(True)
    heart.show_item(20)
    qtbot.waitUntil(lambda: heart.instance_id == "inst1", timeout=3000)
    fake_vts.push("ItemEvent", drop_event("DroppedPinned", 0.1, 0.2))
    qtbot.waitUntil(lambda: moved == [True], timeout=3000)
    # 選び始めに外した知らせで今の場所を読み、やめたらそこへ戻す。
    # 体からは外れたので、手で置いた扱いも消す
    fake_vts.echo_pins = True
    assert heart.start_pick(lambda _pin: None)
    qtbot.waitUntil(lambda: heart.place == (-0.1, 0.4), timeout=3000)
    heart.cancel_pick()
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemMoveRequest")) == 2, timeout=3000)
    back = fake_vts.sent("ItemMoveRequest")[-1]["itemsToMove"][0]
    assert (back["positionX"], back["positionY"]) == (-0.1, 0.4)
    assert not heart.hand_placed and moved == [True, True]
    client.stop()


def test_switching_to_a_model_with_a_saved_place_clears_hand_placed(
    qtbot, fake_vts: FakeVts
) -> None:
    client, heart = _ready_heart(qtbot, fake_vts, pins={"m1": PIN})
    heart.show_item(20)
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemPinRequest")) == 1, timeout=3000)
    # 別のモデルで手で体に置いたあと、場所を覚えているモデルへ切り替えた
    heart.hand_placed = True
    moved: list[bool] = []
    heart.on_moved = lambda: moved.append(True)
    fake_vts.push("ModelLoadedEvent", {"modelLoaded": True, "modelID": "m1"})
    qtbot.waitUntil(lambda: len(fake_vts.sent("ItemPinRequest")) == 2, timeout=3000)
    assert not heart.hand_placed and moved == [True]
    client.stop()


def test_bpm_item_unchecked_while_disconnected_is_put_away(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    del qapp
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui.vts_panel import VtsPanel

    panel = VtsPanel(HeartSession(), tmp_path, lambda _text: None)
    control = panel._bpm
    hidden: list[bool] = []
    made: list[bool] = []
    monkeypatch.setattr(control.bpm, "hide", lambda: hidden.append(True))
    monkeypatch.setattr(control, "make", lambda notice=False: made.append(notice))
    control.check.setChecked(False)
    control._on_found(True)
    assert hidden == [True] and made == []
    control._on_found(False)
    assert hidden == [True] and made == []
    panel.shutdown()


def test_bpm_note_tells_whether_the_number_is_shown(qapp, tmp_path: Path, monkeypatch) -> None:
    del qapp
    from stream_heartbeat.session import HeartSession
    from stream_heartbeat.ui import vts_panel
    from stream_heartbeat.ui.vts_panel import VtsPanel
    from stream_heartbeat.vts_text import BPM_SHOWN_NOTE

    monkeypatch.setattr(vts_panel, "find_items_dir", lambda: None)
    panel = VtsPanel(HeartSession(), tmp_path, lambda _text: None)
    control = panel._bpm
    chosen: list[bool] = []
    control._choose_folder = lambda: chosen.append(True)
    panel._client._state = vts.READY
    # 書き出し先が無ければフォルダを選ばせ、それでも無ければ出せなかったことを一文で残す
    control.check.setChecked(True)
    assert chosen == [True]
    assert control.note.objectName() == "warn" and "Items" in control.note.text()
    # 出せたら、出していることと次の一手（ドラッグして置く）を出す
    control._error = None
    control.bpm.instance_id = "bpm1"
    control.refresh()
    assert control.note.text() == BPM_SHOWN_NOTE and control.note.objectName() == "meta"
    # チェックを外すと消える
    monkeypatch.setattr(control.bpm, "hide", lambda: None)
    control.check.setChecked(False)
    assert control.note.text() == ""
    panel._client._state = vts.OFF
    panel.shutdown()
