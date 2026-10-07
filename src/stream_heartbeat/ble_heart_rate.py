"""Bluetooth の心拍計につなぐ（β）。

bleak（asyncio）を別のスレッドで動かし、見つけた機器・つながり具合・届いた心拍数を
Qt のシグナルで操作画面へ知らせる（シグナルは受け手のスレッドで届く）。
bleak は使うときにそのスレッドの中で読み込む（Windows では GUI のスレッドと COM の設定が違うため）。
"""

from __future__ import annotations

import asyncio
import importlib.util
import threading
from collections.abc import Coroutine

from PySide6.QtCore import QObject, Signal

from stream_heartbeat.heart_rate import HR_MEASUREMENT, HR_SERVICE, parse_heart_rate

# 探す秒数
SCAN_S = 8.0
# つなぐのを待つ秒数と、切れたあと（つなげなかったあと）につなぎ直すまでの秒数
CONNECT_TIMEOUT_S = 20.0
RETRY_S = 3.0
# つながっているかを見回る間隔
WATCH_S = 0.5

# つながり具合（state_changed）
IDLE = "idle"
SCANNING = "scanning"
CONNECTING = "connecting"
CONNECTED = "connected"
# つなげなかった・切れた（RETRY_S 後につなぎ直す）
RETRYING = "retrying"
# Bluetooth が使えない（オフ・無い・bleak が無い）
NO_BLUETOOTH = "no_bluetooth"


def bluetooth_supported() -> bool:
    """bleak が入っているか（配布物に入っていない環境では使えない）。"""
    return importlib.util.find_spec("bleak") is not None


class HeartRateLink(QObject):
    # 見つけた心拍計 [(アドレス, 名前)]
    devices_found = Signal(list)
    state_changed = Signal(str)
    # HeartRateReading
    reading = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.state = IDLE
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        # 別スレッドの中だけで触る
        self._task: asyncio.Task | None = None
        self.state_changed.connect(self._remember_state)

    def _remember_state(self, state: str) -> None:
        self.state = state

    # ------------------------------------------------------------ 操作画面から呼ぶ

    def scan(self, seconds: float = SCAN_S) -> None:
        """心拍を送っている機器を探す。終わったら devices_found。つないでいれば切る。"""
        self._run(self._scan(seconds))

    def connect_to(self, address: str) -> None:
        """つなぐ。切れたらつなぎ直し続ける（disconnect まで）。"""
        self._run(self._keep_connected(address))

    def disconnect(self) -> None:
        if self._loop is not None:
            self._run(None)

    def shutdown(self) -> None:
        """終わるとき。つないでいれば切り、スレッドを止める。"""
        loop = self._loop
        if loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._switch(None), loop).result(timeout=3.0)
        except Exception:  # noqa: BLE001 - 終わるときは切れなくても進める
            pass
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._loop = None
        self._thread = None

    # ------------------------------------------------------------ 別スレッド

    def _run(self, job: Coroutine | None) -> None:
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._loop.run_forever, name="heart-rate-ble", daemon=True
            )
            self._thread.start()
        asyncio.run_coroutine_threadsafe(self._switch(job), self._loop)

    async def _switch(self, job: Coroutine | None) -> None:
        """前の仕事（探す・つなぐ）を止めてから、次の仕事を始める。"""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except BaseException:  # noqa: BLE001 - 止めた仕事の終わり方は問わない
                pass
            self._task = None
        if job is None:
            self.state_changed.emit(IDLE)
            return
        self._task = asyncio.ensure_future(job)

    async def _scan(self, seconds: float) -> None:
        self.state_changed.emit(SCANNING)
        try:
            from bleak import BleakScanner

            found = await BleakScanner.discover(
                timeout=seconds, return_adv=True, service_uuids=[HR_SERVICE]
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - Bluetooth がオフ・無いなど。理由は画面に出さない
            self.devices_found.emit([])
            self.state_changed.emit(NO_BLUETOOTH)
            return
        devices: list[tuple[str, str]] = []
        for address, (device, adv) in found.items():
            # 心拍のサービスを知らせていない機器は除く（OS によっては絞り込まれないことがある）
            if HR_SERVICE not in [u.lower() for u in adv.service_uuids]:
                continue
            name = adv.local_name or device.name or ""
            devices.append((address, name))
        devices.sort(key=lambda d: (not d[1], d[1].lower()))
        self.devices_found.emit(devices)
        self.state_changed.emit(IDLE)

    async def _keep_connected(self, address: str) -> None:
        try:
            from bleak import BleakClient
        except Exception:  # noqa: BLE001
            self.state_changed.emit(NO_BLUETOOTH)
            return
        while True:
            self.state_changed.emit(CONNECTING)
            try:
                async with BleakClient(
                    address, timeout=CONNECT_TIMEOUT_S, services=[HR_SERVICE]
                ) as client:
                    try:
                        await client.start_notify(HR_MEASUREMENT, self._on_notify)
                    except asyncio.CancelledError:
                        raise
                    except Exception:  # noqa: BLE001
                        # 心拍を暗号化して送る時計（Fitbit など）は、ペアリングしてから受け取る
                        # （Mac はここに来る前に OS がペアリングを聞く）
                        await client.pair()
                        await client.start_notify(HR_MEASUREMENT, self._on_notify)
                    self.state_changed.emit(CONNECTED)
                    while client.is_connected:
                        await asyncio.sleep(WATCH_S)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 見つからない・切れたなど。つなぎ直す
                pass
            self.state_changed.emit(RETRYING)
            await asyncio.sleep(RETRY_S)

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        reading = parse_heart_rate(bytes(data))
        if reading is not None:
            self.reading.emit(reading)
