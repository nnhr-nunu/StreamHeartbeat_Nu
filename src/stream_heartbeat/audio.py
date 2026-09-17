"""マイク入力。独占モードは使わない。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices


def _mono16k() -> QAudioFormat:
    fmt = QAudioFormat()
    fmt.setSampleRate(16000)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return fmt


@dataclass(frozen=True)
class MicDevice:
    id: str
    name: str


def list_mics() -> list[MicDevice]:
    out: list[MicDevice] = []
    for device in QMediaDevices.audioInputs():
        ident = bytes(device.id()).decode("utf-8", "replace")
        out.append(MicDevice(id=ident, name=device.description()))
    return out


class MicTap:
    def __init__(self) -> None:
        self._source: QAudioSource | None = None
        self._io = None

    def start(self, mic_id: str) -> None:
        self.stop()
        chosen = QMediaDevices.defaultAudioInput()
        for device in QMediaDevices.audioInputs():
            ident = bytes(device.id()).decode("utf-8", "replace")
            if ident == mic_id:
                chosen = device
                break
        self._source = QAudioSource(chosen, _mono16k())
        self._io = self._source.start()

    def stop(self) -> None:
        if self._source is not None:
            self._source.stop()
        self._source = None
        self._io = None

    def pull_mono(self) -> list[float]:
        if self._io is None:
            return []
        data = bytes(self._io.readAll())
        if len(data) < 2:
            return []
        samples: list[float] = []
        for i in range(0, len(data) - 1, 2):
            raw = int.from_bytes(data[i : i + 2], "little", signed=True)
            samples.append(raw / 32768.0)
        return samples


class MicMonitor:
    """操作画面だけに入力を返す。配信出力には出さない。"""

    def __init__(self) -> None:
        self._sink = None
        self._io = None

    def start(self) -> None:
        self.stop()
        try:
            from PySide6.QtMultimedia import QAudioSink

            self._sink = QAudioSink(QMediaDevices.defaultAudioOutput(), _mono16k())
            self._io = self._sink.start()
        except Exception:
            self.stop()

    def stop(self) -> None:
        if self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                pass
        self._sink = None
        self._io = None

    def write_mono(self, samples: list[float]) -> None:
        if self._io is None or self._sink is None or not samples:
            return
        payload = bytearray()
        for sample in samples:
            raw = int(max(-1.0, min(1.0, sample * 0.4)) * 32767)
            payload.extend(raw.to_bytes(2, "little", signed=True))
        data = bytes(payload)
        try:
            free = int(self._sink.bytesFree())
            if free <= 0:
                return
            self._io.write(data[:free])
        except Exception:
            return
