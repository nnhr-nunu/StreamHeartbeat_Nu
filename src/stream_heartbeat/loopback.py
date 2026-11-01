"""デスクトップの音（この PC で鳴っている音）の取り込み。Windows の WASAPI ループバック。

Qt はスピーカーへ出る音を録音できないので、ctypes で COM を直接呼ぶ（配布物に部品を足さない）。
取り込みは別スレッド。COM は呼んだスレッドで初期化するので、GUI スレッドの設定に影響しない。
"""

from __future__ import annotations

import array
import ctypes
import sys
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from ctypes import POINTER, byref, c_long, c_void_p, cast

OUTPUT_RATE = 16000
# 詰まったときに溜める上限（秒）
MAX_QUEUE_S = 5.0
# 何も再生していないと WASAPI は何も渡さないので、この秒数届かなければ無音で埋める
SILENCE_AFTER_S = 0.1
POLL_S = 0.01
RETRY_S = 1.0
# 既定の出力先（スピーカー・ヘッドホン）を変えたかを見る間隔
DEVICE_CHECK_S = 1.0

_BUFFER_HNS = 2_000_000  # 200 ms（100 ns 単位）
_AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
_AUDCLNT_BUFFERFLAGS_SILENT = 0x2
_CLSCTX_ALL = 23
_E_RENDER = 0
_E_CONSOLE = 0
_TAG_PCM = 1
_TAG_FLOAT = 3
_TAG_EXTENSIBLE = 0xFFFE

_CLSID_ENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
_IID_ENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"
_IID_AUDIO_CLIENT = "1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"
_IID_CAPTURE_CLIENT = "C8ADBD64-E71E-48A0-A4DE-185C395CD317"


def loopback_supported() -> bool:
    return sys.platform == "win32"


class MonoDownsampler:
    """重なった各チャンネルの小数を 1 チャンネルの 16 kHz にする（区間の平均で間引く）。"""

    def __init__(self, rate: int, channels: int) -> None:
        if rate <= 0 or channels <= 0:
            raise ValueError("bad audio format")
        self._channels = channels
        self._step = rate / OUTPUT_RATE
        self._pos = 0.0
        self._total = 0.0
        self._count = 0
        self._held = 0.0

    def feed(self, data: Sequence[float]) -> list[float]:
        channels = self._channels
        if channels == 1:
            frames: Sequence[float] = data
        else:
            split = (data[c::channels] for c in range(channels))
            frames = [sum(frame) / channels for frame in zip(*split)]
        out: list[float] = []
        step = self._step
        pos = self._pos
        total = self._total
        count = self._count
        for value in frames:
            total += value
            count += 1
            pos += 1.0
            while pos >= step:
                pos -= step
                if count:
                    self._held = total / count
                    total = 0.0
                    count = 0
                out.append(self._held)
        self._pos = pos
        self._total = total
        self._count = count
        return out


def decode_samples(raw: bytes, bits: int, is_float: bool) -> Sequence[float]:
    """取り込んだ音のバイト列を -1〜1 の小数にする。扱えない形式は ValueError。"""
    if is_float and bits == 32:
        return array.array("f", raw)
    if not is_float and bits == 16:
        return [x / 32768.0 for x in array.array("h", raw)]
    if not is_float and bits == 32:
        return [x / 2147483648.0 for x in array.array("i", raw)]
    raise ValueError("unsupported audio format")


class _ComError(OSError):
    pass


def _check(hr: int) -> None:
    if hr < 0:
        raise _ComError(f"HRESULT {hr & 0xFFFFFFFF:#010x}")


def _guid(text: str) -> ctypes.Array:
    return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)


def _method(ptr: c_void_p, index: int, *argtypes: type) -> Callable[..., int]:
    """COM の窓口 ptr の index 番目の関数。戻り値は HRESULT。"""
    table = cast(ptr, POINTER(POINTER(c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)
    function = prototype(table[index])
    return lambda *args: function(ptr, *args)


def _release(ptr: c_void_p | None) -> None:
    if ptr:
        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(
            cast(ptr, POINTER(POINTER(c_void_p))).contents[2]
        )(ptr)


def _mix_format(pointer: c_void_p) -> tuple[int, int, int, bool]:
    """WAVEFORMATEX(TENSIBLE) の (周波数, チャンネル数, ビット数, 小数か)。"""
    head = ctypes.string_at(pointer, 18)
    tag = int.from_bytes(head[0:2], "little")
    channels = int.from_bytes(head[2:4], "little")
    rate = int.from_bytes(head[4:8], "little")
    bits = int.from_bytes(head[14:16], "little")
    if tag == _TAG_EXTENSIBLE:
        # SubFormat の GUID（24 バイト目から）の先頭 2 バイトが本当の形式
        tag = int.from_bytes(ctypes.string_at(pointer, 26)[24:26], "little")
    return rate, channels, bits, tag == _TAG_FLOAT


class LoopbackTap:
    """既定の出力先に流れている音を取り込み、16 kHz モノラルで渡す。使い方は MicTap と同じ。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[float] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._failed = False

    @property
    def failed(self) -> bool:
        """出力先を開けていない（つなぎ直しは続けている）。"""
        return self._failed

    def start(self) -> None:
        self.stop()
        if not loopback_supported():
            self._failed = True
            return
        self._stop_event = threading.Event()
        self._failed = False
        self._thread = threading.Thread(target=self._run, name="desktop-audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        with self._lock:
            self._queue = []

    def pull_mono(self) -> list[float]:
        with self._lock:
            samples, self._queue = self._queue, []
        return samples

    def _push(self, samples: list[float]) -> None:
        with self._lock:
            self._queue.extend(samples)
            limit = int(MAX_QUEUE_S * OUTPUT_RATE)
            if len(self._queue) > limit:
                del self._queue[: len(self._queue) - limit]

    def _run(self) -> None:
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0)
        try:
            while not self._stop_event.is_set():
                try:
                    self._capture_default_output()
                except (OSError, ValueError):
                    # 出力先が無い・抜けた。少し待って開き直す
                    self._failed = True
                    self._stop_event.wait(RETRY_S)
        finally:
            ole32.CoUninitialize()

    def _capture_default_output(self) -> None:
        """既定の出力先を開いて取り込む。止めるか、既定の出力先が変わると戻る。"""
        ole32 = ctypes.windll.ole32
        enumerator = c_void_p()
        device = c_void_p()
        client = c_void_p()
        capture = c_void_p()
        format_ptr = c_void_p()
        try:
            _check(
                ole32.CoCreateInstance(
                    _guid(_CLSID_ENUMERATOR),
                    None,
                    _CLSCTX_ALL,
                    _guid(_IID_ENUMERATOR),
                    byref(enumerator),
                )
            )
            device_id = _default_device(enumerator, device)
            _check(
                _method(device, 3, c_void_p, ctypes.c_uint32, c_void_p, POINTER(c_void_p))(
                    _guid(_IID_AUDIO_CLIENT), _CLSCTX_ALL, None, byref(client)
                )
            )
            _check(_method(client, 8, POINTER(c_void_p))(byref(format_ptr)))
            rate, channels, bits, is_float = _mix_format(format_ptr)
            _check(
                _method(
                    client,
                    3,
                    ctypes.c_int,
                    ctypes.c_uint32,
                    ctypes.c_int64,
                    ctypes.c_int64,
                    c_void_p,
                    c_void_p,
                )(0, _AUDCLNT_STREAMFLAGS_LOOPBACK, _BUFFER_HNS, 0, format_ptr, None)
            )
            _check(
                _method(client, 14, c_void_p, POINTER(c_void_p))(
                    _guid(_IID_CAPTURE_CLIENT), byref(capture)
                )
            )
            _check(_method(client, 10)())
            self._failed = False
            try:
                mono = MonoDownsampler(rate, channels)
                self._read_packets(enumerator, device_id, capture, mono, channels, bits, is_float)
            finally:
                _method(client, 11)()
        finally:
            if format_ptr:
                ole32.CoTaskMemFree(format_ptr)
            for pointer in (capture, client, device, enumerator):
                _release(pointer)

    def _read_packets(
        self,
        enumerator: c_void_p,
        device_id: str,
        capture: c_void_p,
        mono: MonoDownsampler,
        channels: int,
        bits: int,
        is_float: bool,
    ) -> None:
        next_packet = _method(capture, 5, POINTER(ctypes.c_uint32))
        get_buffer = _method(
            capture,
            3,
            POINTER(c_void_p),
            POINTER(ctypes.c_uint32),
            POINTER(ctypes.c_uint32),
            c_void_p,
            c_void_p,
        )
        release_buffer = _method(capture, 4, ctypes.c_uint32)
        frame_bytes = channels * bits // 8
        checked_at = heard_at = time.perf_counter()
        while not self._stop_event.is_set():
            size = ctypes.c_uint32()
            _check(next_packet(byref(size)))
            now = time.perf_counter()
            if size.value == 0:
                if now - heard_at >= SILENCE_AFTER_S:
                    self._push([0.0] * int((now - heard_at) * OUTPUT_RATE))
                    heard_at = now
                if now - checked_at >= DEVICE_CHECK_S:
                    checked_at = now
                    probe = c_void_p()
                    try:
                        if _default_device(enumerator, probe) != device_id:
                            return
                    finally:
                        _release(probe)
                self._stop_event.wait(POLL_S)
                continue
            data = c_void_p()
            frames = ctypes.c_uint32()
            flags = ctypes.c_uint32()
            _check(get_buffer(byref(data), byref(frames), byref(flags), None, None))
            if flags.value & _AUDCLNT_BUFFERFLAGS_SILENT or not data:
                values: Sequence[float] = [0.0] * (frames.value * channels)
            else:
                values = decode_samples(
                    ctypes.string_at(data, frames.value * frame_bytes), bits, is_float
                )
            _check(release_buffer(frames))
            self._push(mono.feed(values))
            heard_at = now


def _default_device(enumerator: c_void_p, device: c_void_p) -> str:
    """既定の出力先を device に入れ、その ID を返す。"""
    _check(
        _method(enumerator, 4, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
            _E_RENDER, _E_CONSOLE, byref(device)
        )
    )
    text = c_void_p()
    _check(_method(device, 5, POINTER(c_void_p))(byref(text)))
    try:
        return ctypes.wstring_at(text)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(text)
