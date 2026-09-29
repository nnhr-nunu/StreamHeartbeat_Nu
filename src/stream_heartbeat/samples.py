"""wav / mp3 などをモノラル PCM にする。"""

from __future__ import annotations

import array
import wave
from pathlib import Path

AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wma", ".mp4", ".mov", ".m4v"}
AUDIO_FILTER = "音声・動画 (*.wav *.mp3 *.m4a *.mp4 *.mov);;すべて (*.*)"
TARGET_RATE = 16000


def load_audio_mono(path: Path) -> list[float]:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        try:
            return load_wav_mono(path)
        except ValueError:
            pass
    try:
        return _decode_with_qt(path, convert=True)
    except ValueError:
        # 一部の mp3 は Qt 側の 16 kHz 変換だけ失敗する。元の形式で読んで自前で変換する
        return _decode_with_qt(path, convert=False)


def load_wav_mono(path: Path) -> list[float]:
    """16bit の WAV をモノラル 16 kHz にする。それ以外の形式は ValueError。"""
    try:
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            width = wav.getsampwidth()
            rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"WAV を読めません: {exc}") from exc
    if width != 2:
        raise ValueError("16bit WAV only")
    pcm = array.array("h")
    pcm.frombytes(frames[: len(frames) // 2 * 2])
    values = [x / 32768.0 for x in pcm]
    return to_mono_16k(values, channels, rate)


def to_mono_16k(frames: list[float], channels: int, rate: int) -> list[float]:
    """インターリーブされた音をモノラル 16 kHz に。間引きは区間平均（高い音の折り返しを抑える）。"""
    channels = max(1, channels)
    mono = [
        sum(frames[i : i + channels]) / channels
        for i in range(0, len(frames) - channels + 1, channels)
    ]
    if rate <= 0 or rate == TARGET_RATE or not mono:
        return mono
    step = rate / TARGET_RATE
    out: list[float] = []
    pos = 0.0
    while True:
        a = int(pos)
        b = max(a + 1, int(pos + step))
        if b > len(mono):
            break
        chunk = mono[a:b]
        out.append(sum(chunk) / len(chunk))
        pos += step
    return out


def _buffer_floats(buf) -> tuple[list[float], int, int]:
    from PySide6.QtMultimedia import QAudioFormat

    fmt = buf.format()
    data = buf.constData()
    if data is None:
        return [], 0, 0
    raw = bytes(data)
    kind = fmt.sampleFormat()
    if kind == QAudioFormat.SampleFormat.Float:
        values = array.array("f")
        values.frombytes(raw[: len(raw) // 4 * 4])
        floats = list(values)
    elif kind == QAudioFormat.SampleFormat.Int32:
        values = array.array("i")
        values.frombytes(raw[: len(raw) // 4 * 4])
        floats = [v / 2147483648.0 for v in values]
    elif kind == QAudioFormat.SampleFormat.UInt8:
        floats = [(v - 128) / 128.0 for v in raw]
    else:
        values = array.array("h")
        values.frombytes(raw[: len(raw) // 2 * 2])
        floats = [v / 32768.0 for v in values]
    return floats, fmt.channelCount(), fmt.sampleRate()


def _decode_with_qt(path: Path, *, convert: bool) -> list[float]:
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

    decoder = QAudioDecoder()
    if convert:
        fmt = QAudioFormat()
        fmt.setSampleRate(TARGET_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        decoder.setAudioFormat(fmt)
    decoder.setSource(QUrl.fromLocalFile(str(path.resolve())))
    frames: list[float] = []
    layout = [1, TARGET_RATE]

    def on_buffer() -> None:
        buf = decoder.read()
        if not buf.isValid():
            return
        floats, channels, rate = _buffer_floats(buf)
        if not floats:
            return
        layout[0] = channels or 1
        layout[1] = rate or TARGET_RATE
        frames.extend(floats)

    loop = QEventLoop()
    decoder.bufferReady.connect(on_buffer)
    decoder.finished.connect(loop.quit)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(60000)
    decoder.start()
    loop.exec()
    decoder.stop()
    err = decoder.error()
    if err != QAudioDecoder.Error.NoError and not frames:
        raise ValueError(decoder.errorString() or str(err))
    if not frames:
        raise ValueError("empty audio")
    if convert:
        return frames
    return to_mono_16k(frames, layout[0], layout[1])
