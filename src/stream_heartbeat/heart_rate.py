"""Bluetooth の心拍計（標準の Heart Rate Service）から届く値と、心拍数から拍を作る部分。

心拍計が送ってくるのは 1 秒に 1 回ほどの心拍数（機種によっては拍と拍の間の長さ＝RR 間隔も）で、
拍の瞬間そのものは届かない。そこで、届いた心拍数の間隔で拍を刻んで心臓を動かす
（心拍数は合うが、拍の瞬間は本物の鼓動とずれる）。RR 間隔が届く機種では、その長さで刻む。

Qt も bleak も読み込まない（テストしやすいように）。つなぐ部分は ble_heart_rate.py。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

# 標準の心拍サービスと、心拍数の知らせ（Heart Rate Measurement）
HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
# 心拍計の値として信じる範囲（肌から離れると 0 を送ってくる機種がある）
MIN_HR_BPM = 30
MAX_HR_BPM = 230
# RR 間隔を使う範囲（心拍数から決まる間隔に対する割合）。外れたものは測り損ないとみなす
RR_LOW = 0.6
RR_HIGH = 1.6
# 覚えておく RR 間隔の数（届く速さと使う速さはほぼ同じ。たまり過ぎないように）
RR_KEEP = 8
# この秒数、心拍計から値が来なければ拍を止める（切れた・腕から外したなど）
STALE_S = 5.0
# 操作画面が止まっていた間の拍は出さず、この秒数より遅れていたら今から刻み直す
CATCH_UP_S = 2.0


@dataclass(frozen=True)
class HeartRateReading:
    bpm: int
    # 拍と拍の間（秒）。送ってこない機種は空
    rr: tuple[float, ...] = ()
    # 肌に触れているか（知らせない機種は None）
    contact: bool | None = None


def parse_heart_rate(data: bytes) -> HeartRateReading | None:
    """Heart Rate Measurement（0x2A37）の中身を読む。短すぎて読めなければ None。"""
    if len(data) < 2:
        return None
    flags = data[0]
    if flags & 0x01:
        if len(data) < 3:
            return None
        bpm = int.from_bytes(data[1:3], "little")
        pos = 3
    else:
        bpm = data[1]
        pos = 2
    # bit2 が立っていれば、bit1 が肌に触れているか
    contact = bool(flags & 0x02) if flags & 0x04 else None
    if flags & 0x08:
        # 消費エネルギー（使わない）
        pos += 2
    rr: list[float] = []
    if flags & 0x10:
        while pos + 2 <= len(data):
            rr.append(int.from_bytes(data[pos : pos + 2], "little") / 1024.0)
            pos += 2
    return HeartRateReading(bpm=bpm, rr=tuple(rr), contact=contact)


class BeatsFromRate:
    """心拍計の心拍数（と RR 間隔）から、拍の時刻を刻む。"""

    def __init__(self) -> None:
        # 最後に届いた、信じられる心拍数（まだ無ければ 0）
        self.bpm = 0
        self._rr: deque[float] = deque(maxlen=RR_KEEP)
        self._next: float | None = None
        self._heard = 0.0

    @property
    def beating(self) -> bool:
        return self._next is not None

    def feed(self, reading: HeartRateReading, now: float) -> None:
        """心拍計から値が届いた。肌から離れている・あり得ない値は使わない。"""
        if reading.contact is False or not MIN_HR_BPM <= reading.bpm <= MAX_HR_BPM:
            return
        self.bpm = reading.bpm
        self._heard = now
        self._rr.extend(rr for rr in reading.rr if self._usable(rr))
        if self._next is None:
            self._next = now

    def due(self, now: float) -> list[float]:
        """now までに来た拍の時刻。"""
        if self._next is None:
            return []
        if now - self._heard > STALE_S:
            self.reset()
            return []
        if now - self._next > CATCH_UP_S:
            self._next = now
        beats: list[float] = []
        while self._next <= now:
            beats.append(self._next)
            self._next += self._interval()
        return beats

    def reset(self) -> None:
        self._next = None
        self._rr.clear()

    def _usable(self, rr: float) -> bool:
        base = 60.0 / self.bpm
        return RR_LOW * base <= rr <= RR_HIGH * base

    def _interval(self) -> float:
        while self._rr:
            rr = self._rr.popleft()
            # 届いたあとに心拍数が大きく変わっていれば、古い RR は使わない
            if self._usable(rr):
                return rr
        return 60.0 / self.bpm
