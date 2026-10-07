"""VTube Studio に心拍数の数字を出す（コマ送りのアイテム。心拍数ごとに 1 コマ、bpm_frames）。

コマは流さず、心拍数が変わったらそのコマを出す。置き場所は VTube Studio の画面でドラッグして
決める。落とした所は知らせ（ItemEvent。心臓の VtsHeart が受けてこちらへ渡す）で覚え、
出し直しても同じ所に出す。大きさは操作画面の「数字の大きさ」（心臓とは別）。
"""

from __future__ import annotations

from collections.abc import Callable

from stream_heartbeat.render.bpm_frames import bpm_frame_index
from stream_heartbeat.vts import (
    DROPPED_PINNED,
    DROPPED_UNPINNED,
    ERROR_ITEM_NOT_FOUND,
    ITEM_SIZE,
    ITEM_SIZE_MAX,
    ITEM_SIZE_MIN,
    READY,
    VtsClient,
)
from stream_heartbeat.vts_support import clean_place

# アイテムのフォルダ名。心臓の ITEM_FOLDER（ANIM_StreamHeartbeat）を含まない名前にする
# （VTube Studio はファイル名を「含む」で選ぶので、心臓をしまうときに一緒にしまわれないように）
BPM_FOLDER = "ANIM_HeartRate_StreamHeartbeat"
# はじめて出すときの位置（心臓を出す所の下）
BPM_HOME = (0.0, -0.55)
# 重なりの順（心臓より手前）
BPM_ORDER = 8


class VtsBpm:
    def __init__(
        self, client: VtsClient, size: float = ITEM_SIZE, place: tuple[float, float] | None = None
    ) -> None:
        self._client = client
        self.instance_id: str | None = None
        self.size = size
        # VTube Studio の画面でドラッグして置いた所
        self.place = place
        self.last_error = ""
        # つないだ直後に場を調べ終えたら、数字が場にあったかを渡す
        self.on_found: Callable[[bool], None] | None = None
        # VTube Studio の画面で数字を動かし、place が変わった
        self.on_moved: Callable[[], None] | None = None
        # 出しているコマ（-1 は分からない）
        self._frame = -1
        client.ready.connect(self._on_ready)

    def _on_ready(self) -> None:
        self._frame = -1

        def found() -> None:
            if self.on_found is not None:
                self.on_found(self.instance_id is not None)

        self._find(found)

    def _find(self, then: Callable[[], None], rescan: bool = False) -> None:
        def got(data: dict) -> None:
            items = data.get("itemInstancesInScene") or []
            mine = [i for i in items if isinstance(i, dict) and i.get("fileName") == BPM_FOLDER]
            self.instance_id = str(mine[0].get("instanceID")) if mine else None
            then()

        self._client.request(
            "ItemListRequest",
            {
                "includeAvailableSpots": False,
                "includeItemInstancesInScene": True,
                # 新しく書いたコマを読ませるには、ファイルの一覧を読み直させる
                "includeAvailableItemFiles": rescan,
                "onlyItemsWithFileName": BPM_FOLDER,
            },
            got,
        )

    def show(self, done: Callable[[bool], None] | None = None) -> None:
        """数字のアイテムを出し直す（新しいコマを読ませるため、出ていれば一度しまう）。"""

        def load() -> None:
            x, y = self.place or BPM_HOME
            self._client.request(
                "ItemLoadRequest",
                {
                    "fileName": BPM_FOLDER,
                    "positionX": x,
                    "positionY": y,
                    "size": self.size,
                    "rotation": 0,
                    "fadeTime": 0.3,
                    "order": BPM_ORDER,
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
            ok = isinstance(instance, str)
            self.instance_id = instance if ok else None
            self._frame = -1
            self.last_error = "" if ok else str(data.get("message") or "アイテムを出せませんでした")
            if done is not None:
                done(ok)

        def unload_then_load() -> None:
            if self.instance_id is None:
                load()
            else:
                self._unload(lambda _data: load())

        self._find(unload_then_load, rescan=True)

    def hide(self) -> None:
        self._unload(None)
        self.instance_id = None

    def _unload(self, then: Callable[[dict], None] | None) -> None:
        self._client.request(
            "ItemUnloadRequest",
            {
                "unloadAllInScene": False,
                "unloadAllLoadedByThisPlugin": False,
                "allowUnloadingItemsLoadedByUserOrOtherPlugins": True,
                "instanceIDs": [],
                "fileNames": [BPM_FOLDER],
            },
            then,
        )

    def set_bpm(self, bpm: float) -> None:
        """心拍数のコマを出す（変わったときだけ送る）。"""
        if self._client.state != READY or self.instance_id is None:
            return
        frame = bpm_frame_index(bpm)
        if frame == self._frame:
            return
        self._frame = frame
        instance = self.instance_id

        def replied(data: dict) -> None:
            # VTube Studio 側で消された。心拍数が変わるたびにエラーを返させない
            if data.get("errorID") == ERROR_ITEM_NOT_FOUND and self.instance_id == instance:
                self.instance_id = None

        self._client.request(
            "ItemAnimationControlRequest",
            {
                "itemInstanceID": instance,
                "framerate": -1,
                "frame": frame,
                "brightness": -1,
                "opacity": -1,
                "setAutoStopFrames": True,
                "autoStopFrames": [frame],
                "setAnimationPlayState": True,
                "animationPlayState": False,
            },
            replied,
        )

    def set_size(self, size: float) -> None:
        self.size = max(ITEM_SIZE_MIN, min(ITEM_SIZE_MAX, size))
        size = self.size
        if self._client.state != READY or self.instance_id is None:
            return
        self._client.request(
            "ItemMoveRequest",
            {
                "itemsToMove": [
                    {
                        "itemInstanceID": self.instance_id,
                        "timeInSeconds": 0.0,
                        "fadeMode": "easeOut",
                        "positionX": -1000.0,
                        "positionY": -1000.0,
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

    def on_item_event(self, data: dict) -> None:
        """VTube Studio の画面で数字を動かした（心臓の VtsHeart から渡される）。"""
        if data.get("itemEventType") not in (DROPPED_PINNED, DROPPED_UNPINNED):
            return
        place = clean_place(data.get("itemPosition"))
        if self.instance_id is None or data.get("itemInstanceID") != self.instance_id:
            return
        if place is None:
            return
        self.place = place
        if self.on_moved is not None:
            self.on_moved()
