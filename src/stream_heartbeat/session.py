"""検出・時計・文字を1本の tick にまとめる。"""

from __future__ import annotations

from stream_heartbeat.clock import BeatClock
from stream_heartbeat.detect import CalibrationTemplate, HeartSoundDetector
from stream_heartbeat.overlay import OverlayState
from stream_heartbeat.profile import HeartProfile


class HeartSession:
    def __init__(self, profile: HeartProfile | None = None) -> None:
        self.profile = profile if profile is not None else HeartProfile()
        self.clock = BeatClock()
        self.overlay = OverlayState()
        self.calibrating: list[float] | None = None
        self.rebuild_detector()

    def rebuild_detector(self) -> None:
        template = None
        if self.profile.calibration:
            template = CalibrationTemplate.from_sessions(self.profile.calibration)
        self.detector = HeartSoundDetector(template=template)

    def begin_calibration(self) -> None:
        self.calibrating = []

    def discard_calibration(self) -> None:
        self.calibrating = None

    def commit_calibration(self) -> None:
        if self.calibrating:
            self.profile.calibration.append(list(self.calibrating))
            self.rebuild_detector()
        self.calibrating = None

    def tick(self, t: float, samples: list[float], sample_rate: float = 16000.0) -> None:
        if self.calibrating is not None:
            self.calibrating.extend(samples)
        for beat_t in self.detector.feed(samples, t, sample_rate):
            self.clock.feed_beat(beat_t)
            self.overlay.on_beat(beat_t, self.profile.beat_text)
        self.clock.lost_if_silent(t)
        if self.clock.pop_arrhythmia(t) and self.profile.show_arrhythmia:
            self.overlay.on_arrhythmia(t)
