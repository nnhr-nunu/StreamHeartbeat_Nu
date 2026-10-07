"""音声・動画ファイルを、マイクの代わりに少しずつ流す（β）。

ファイルは最初にまとめてモノラル 16 kHz の 16bit にしておき、時計に合わせて少しずつ取り出す。
長い録音でもメモリを使いすぎないよう、16bit のまま持つ（1 時間でおよそ 110 MB）。
"""

from __future__ import annotations

import array
import wave
from collections.abc import Sequence
from pathlib import Path

from stream_heartbeat.samples import TARGET_RATE, _buffer_floats

RATE = TARGET_RATE
# 読むのは最初のこの秒数まで
MAX_FILE_S = 60 * 60
# 読み終わらないまま、この秒数なにも届かなければやめる（16 kHz への変換だけ黙って止まる mp3 が
# あり、そのときは変換なしで読み直す）
DECODE_IDLE_MS = 3000
# 操作画面が止まっていた間の音は、この秒数ぶんまでしか一度に流さない
MAX_PULL_S = 5.0


def _to16(value: float) -> int:
    return int(max(-1.0, min(1.0, value)) * 32767)


class _ToMono16k:
    """インターリーブの音を少しずつモノラル 16 kHz の 16bit にする（区間平均で間引く）。

    区切りをまたいでも音の長さがずれないよう、使い残した分と読み位置を持ち越す。
    """

    def __init__(self, channels: int, rate: int) -> None:
        self._channels = max(1, channels)
        self._step = rate / RATE if rate > 0 else 1.0
        self._rest: list[float] = []
        self._pos = 0.0

    def feed(self, frames: Sequence[float]) -> array.array:
        ch = self._channels
        if ch == 1:
            mono = list(frames)
        else:
            mono = [sum(frames[i : i + ch]) / ch for i in range(0, len(frames) - ch + 1, ch)]
        buf = self._rest + mono
        out = array.array("h")
        pos = self._pos
        while True:
            a = int(pos)
            b = max(a + 1, int(pos + self._step))
            if b > len(buf):
                break
            chunk = buf[a:b]
            out.append(_to16(sum(chunk) / len(chunk)))
            pos += self._step
        keep = min(int(pos), len(buf))
        self._rest = buf[keep:]
        self._pos = pos - keep
        return out


def load_pcm16(path: Path, max_seconds: float = MAX_FILE_S) -> tuple[array.array, bool]:
    """ファイルをモノラル 16 kHz の 16bit にする。(音, 長すぎて途中で切ったか)。

    読めなければ ValueError。
    """
    limit = int(max_seconds * RATE)
    if path.suffix.lower() == ".wav":
        try:
            return _wav_pcm16(path, limit, fast_only=True)
        except ValueError:
            pass
    try:
        return _qt_pcm16(path, limit, convert=True)
    except ValueError:
        pass
    try:
        # 一部の mp3 は Qt 側の 16 kHz 変換だけ失敗する。元の形式で読んで自前で変換する
        return _qt_pcm16(path, limit, convert=False)
    except ValueError:
        if path.suffix.lower() != ".wav":
            raise
    return _wav_pcm16(path, limit, fast_only=False)


def _wav_pcm16(path: Path, limit: int, *, fast_only: bool) -> tuple[array.array, bool]:
    """16bit の WAV を読む。fast_only ならモノラル 16 kHz のものだけ（ほかは ValueError）。"""
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            if width != 2:
                raise ValueError("16bit WAV only")
            direct = channels == 1 and rate == RATE
            if fast_only and not direct:
                raise ValueError("not mono 16 kHz")
            out = array.array("h")
            convert = None if direct else _ToMono16k(channels, rate)
            while len(out) < limit:
                frames = wav.readframes(rate)
                if not frames:
                    break
                pcm = array.array("h")
                pcm.frombytes(frames[: len(frames) // 2 * 2])
                if convert is None:
                    out.extend(pcm)
                else:
                    out.extend(convert.feed([v / 32768.0 for v in pcm]))
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV を読めません: {exc}") from exc
    if not out:
        raise ValueError("empty audio")
    return _cut(out, limit)


def _cut(pcm: array.array, limit: int) -> tuple[array.array, bool]:
    if len(pcm) > limit:
        del pcm[limit:]
        return pcm, True
    return pcm, False


def _qt_pcm16(path: Path, limit: int, *, convert: bool) -> tuple[array.array, bool]:
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

    decoder = QAudioDecoder()
    if convert:
        fmt = QAudioFormat()
        fmt.setSampleRate(RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        decoder.setAudioFormat(fmt)
    decoder.setSource(QUrl.fromLocalFile(str(path.resolve())))
    out = array.array("h")
    converters: dict[tuple[int, int], _ToMono16k] = {}
    loop = QEventLoop()
    # 読めないファイルは start() の中でエラーが来て終わる（そのときは待たない）
    done = [False]

    def finish() -> None:
        done[0] = True
        loop.quit()

    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(finish)

    def on_buffer() -> None:
        buf = decoder.read()
        if not buf.isValid() or len(out) >= limit:
            return
        watchdog.start(DECODE_IDLE_MS)
        fmt = buf.format()
        if (
            fmt.sampleFormat() == QAudioFormat.SampleFormat.Int16
            and fmt.channelCount() == 1
            and fmt.sampleRate() == RATE
        ):
            data = buf.constData()
            if data is not None:
                raw = bytes(data)
                out.frombytes(raw[: len(raw) // 2 * 2])
        else:
            floats, channels, rate = _buffer_floats(buf)
            key = (channels or 1, rate or RATE)
            if key not in converters:
                converters[key] = _ToMono16k(*key)
            out.extend(converters[key].feed(floats))
        if len(out) >= limit:
            finish()

    decoder.bufferReady.connect(on_buffer)
    decoder.finished.connect(finish)
    decoder.error.connect(lambda _e: finish())
    watchdog.start(DECODE_IDLE_MS)
    decoder.start()
    if not done[0]:
        loop.exec()
    decoder.stop()
    watchdog.stop()
    if not out:
        raise ValueError(decoder.errorString() or "empty audio")
    return _cut(out, limit)


class FilePlayer:
    """読んだ音を、時計に合わせて少しずつ取り出す。くり返し再生もできる。"""

    def __init__(self, pcm: array.array, rate: int = RATE) -> None:
        self._pcm = pcm
        self.rate = rate
        self.loop = True
        self.playing = False
        self._pos = 0
        self._last = 0.0
        self._carry = 0.0

    @property
    def duration(self) -> float:
        return len(self._pcm) / self.rate

    @property
    def position(self) -> float:
        return self._pos / self.rate

    def play(self, now: float) -> None:
        if self._pos >= len(self._pcm):
            self._pos = 0
        self.playing = bool(self._pcm)
        self._last = now
        self._carry = 0.0

    def pause(self) -> None:
        self.playing = False

    def stop(self) -> None:
        self.playing = False
        self._pos = 0

    def pull(self, now: float) -> list[float]:
        """前に取り出してから now までに流れた分の音。"""
        if not self.playing:
            return []
        want = max(0.0, now - self._last) * self.rate + self._carry
        self._last = now
        count = int(want)
        self._carry = want - count
        count = min(count, int(MAX_PULL_S * self.rate))
        out: list[float] = []
        while count > 0:
            take = min(count, len(self._pcm) - self._pos)
            out.extend(v / 32768.0 for v in self._pcm[self._pos : self._pos + take])
            self._pos += take
            count -= take
            if self._pos >= len(self._pcm):
                if not self.loop:
                    self.playing = False
                    break
                self._pos = 0
        return out
