"""クリック拍から間隔と心音の切り出し。"""

from __future__ import annotations

import statistics

from stream_heartbeat.detect import THUD_SECONDS, _rms


def tap_interval(times: list[float]) -> float:
    if len(times) < 4:
        return 0.0
    gaps = [b - a for a, b in zip(times, times[1:]) if 0.22 < (b - a) < 2.8]
    if len(gaps) < 3:
        return 0.0
    return float(statistics.median(gaps))


def chunks_near_taps(
    samples: list[float],
    sample_rate: float,
    start_t: float,
    tap_times: list[float],
    pre: float = 0.32,
    post: float = 0.04,
) -> list[list[float]]:
    if not samples or sample_rate <= 0 or not tap_times:
        return []
    width = max(8, int(THUD_SECONDS * sample_rate))
    hop = max(1, int(0.01 * sample_rate))
    out: list[list[float]] = []
    for tap in tap_times:
        rel = tap - start_t
        begin = int((rel - pre) * sample_rate)
        end = int((rel - post) * sample_rate)
        begin = max(0, begin)
        end = min(len(samples), max(begin + width, end))
        region = samples[begin:end]
        if len(region) < width:
            continue
        best: list[float] = region[:width]
        best_rms = _rms(best)
        i = hop
        while i + width <= len(region):
            chunk = region[i : i + width]
            value = _rms(chunk)
            if value > best_rms:
                best = chunk
                best_rms = value
            i += hop
        if best_rms >= 0.008:
            out.append(best)
    return out
