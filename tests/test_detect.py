from __future__ import annotations

from stream_heartbeat.detect import CalibrationTemplate, HeartSoundDetector, envelope_rms


def test_envelope_rms_is_shorter_than_samples() -> None:
    samples = [0.0] * 100 + [1.0] * 20 + [0.0] * 100
    env = envelope_rms(samples, hop=10)
    assert len(env) < len(samples)
    assert max(env) > min(env)


def test_detector_finds_periodic_peaks() -> None:
    detector = HeartSoundDetector()
    sr = 1000
    t = 0.0
    beats: list[float] = []
    for i in range(3000):
        sample = 0.9 if i % 500 < 40 else 0.01
        found = detector.feed([sample], t)
        beats.extend(found)
        t += 1 / sr
    assert len(beats) >= 4
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert all(0.4 < g < 0.6 for g in gaps)


def test_template_prefers_matching_shape() -> None:
    pulse = [0.1] * 5 + [1.0] * 8 + [0.1] * 5
    template = CalibrationTemplate.from_sessions([pulse, pulse])
    detector = HeartSoundDetector(template=template)
    t = 0.0
    hits = detector.feed(pulse, t)
    assert hits
    miss = detector.feed([0.5] * len(pulse), t + 1.0)
    assert miss == []
