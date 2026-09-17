"""マイク入力。独占モードは使わない。"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices


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
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        chosen = QMediaDevices.defaultAudioInput()
        for device in QMediaDevices.audioInputs():
            ident = bytes(device.id()).decode("utf-8", "replace")
            if ident == mic_id:
                chosen = device
                break
        self._source = QAudioSource(chosen, fmt)
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
