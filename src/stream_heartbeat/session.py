"""検出・時計・文字を1本の tick にまとめる。"""

from __future__ import annotations

from stream_heartbeat.bundled import bundled_heart_sessions
from stream_heartbeat.clock import BeatClock
from stream_heartbeat.detect import BUNDLED_CORR_MIN, CalibrationTemplate, HeartSoundDetector
from stream_heartbeat.overlay import OverlayState
from stream_heartbeat.profile import HeartProfile
from stream_heartbeat.tap import chunks_near_taps, tap_interval


class HeartSession:
    def __init__(self, profile: HeartProfile | None = None) -> None:
        self.profile = profile if profile is not None else HeartProfile()
        self.clock = BeatClock()
        self.overlay = OverlayState()
        self.calibrating: list[float] | None = None
        self._cal_t0 = 0.0
        self._cal_sr = 16000.0
        self.taps: list[float] = []
        self.rebuild_detector()

    def rebuild_detector(self) -> None:
        tap = self.profile.tap_interval
        if self.profile.calibration:
            template = CalibrationTemplate.from_sessions(self.profile.calibration)
            self.detector = HeartSoundDetector(template=template, tap_interval=tap)
            return
        sessions = bundled_heart_sessions()
        template = CalibrationTemplate.from_sessions(sessions) if sessions else None
        self.detector = HeartSoundDetector(
            template=template,
            corr_min=BUNDLED_CORR_MIN,
            tap_interval=tap,
        )

    def begin_calibration(self, t: float = 0.0) -> None:
        self.calibrating = []
        self._cal_t0 = t
        self._cal_sr = 16000.0
        self.taps = []

    def tap(self, t: float) -> None:
        if self.calibrating is None:
            return
        if self.taps and t - self.taps[-1] < 0.2:
            return
        self.taps.append(t)

    def tap_label(self) -> str:
        count = len(self.taps)
        interval = tap_interval(self.taps)
        if count == 0:
            return "クリックなし（任意）"
        if interval <= 0:
            return f"クリック {count} 回"
        bpm = int(round(60.0 / interval))
        return f"クリック {count} 回  約 {bpm} BPM"

    def discard_calibration(self) -> None:
        self.calibrating = None
        self.taps = []

    def commit_calibration(self) -> None:
        if self.calibrating:
            audio = list(self.calibrating)
            self.profile.calibration.append(audio)
            near = chunks_near_taps(audio, self._cal_sr, self._cal_t0, self.taps)
            self.profile.calibration.extend(near)
            interval = tap_interval(self.taps)
            if interval > 0:
                self.profile.tap_interval = interval
            self.rebuild_detector()
        self.calibrating = None
        self.taps = []

    def tick(self, t: float, samples: list[float], sample_rate: float = 16000.0) -> None:
        if self.calibrating is not None:
            self.calibrating.extend(samples)
            self._cal_sr = sample_rate
        for beat_t in self.detector.feed(samples, t, sample_rate):
            self.clock.feed_beat(beat_t)
            self.overlay.on_beat(beat_t, self.profile.beat_text)
        self.clock.lost_if_silent(t)
        if self.clock.pop_arrhythmia(t) and self.profile.show_arrhythmia:
            self.overlay.on_arrhythmia(t)
