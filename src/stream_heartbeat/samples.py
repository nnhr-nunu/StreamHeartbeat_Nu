"""wav / mp3 などをモノラル PCM にする。"""

from __future__ import annotations

from pathlib import Path

from stream_heartbeat.detect import load_wav_mono

AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".wma", ".mp4", ".mov", ".m4v"}
AUDIO_FILTER = "音声・動画 (*.wav *.mp3 *.m4a *.mp4 *.mov);;すべて (*.*)"


def load_audio_mono(path: Path) -> list[float]:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        try:
            return load_wav_mono(path)
        except ValueError:
            pass
    return _decode_with_qt(path)


def _decode_with_qt(path: Path) -> list[float]:
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

    decoder = QAudioDecoder()
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    decoder.setAudioFormat(fmt)
    decoder.setSource(QUrl.fromLocalFile(str(path.resolve())))
    chunks: list[float] = []

    def on_buffer() -> None:
        buf = decoder.read()
        data = bytes(buf.data())
        for i in range(0, len(data) - 1, 2):
            raw = int.from_bytes(data[i : i + 2], "little", signed=True)
            chunks.append(raw / 32768.0)

    loop = QEventLoop()
    decoder.bufferReady.connect(on_buffer)
    decoder.finished.connect(loop.quit)
    watchdog = QTimer()
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(loop.quit)
    watchdog.start(15000)
    decoder.start()
    loop.exec()
    err = decoder.error()
    if err != QAudioDecoder.Error.NoError and not chunks:
        raise ValueError(decoder.errorString() or str(err))
    if not chunks:
        raise ValueError("empty audio")
    return chunks
