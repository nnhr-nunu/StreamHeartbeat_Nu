from __future__ import annotations

from stream_heartbeat.motion import ejection_blobs


def test_no_blood_when_not_ejecting() -> None:
    assert ejection_blobs(eject=0.0, dt=0.1) == []


def test_blood_travels_outward_during_ejection() -> None:
    early = ejection_blobs(eject=1.0, dt=0.06)
    later = ejection_blobs(eject=0.7, dt=0.16)
    assert early
    assert later
    assert max(x for x, _y, _r, _a in later) > max(x for x, _y, _r, _a in early)
    assert all(a > 0 for _x, _y, _r, a in early)
