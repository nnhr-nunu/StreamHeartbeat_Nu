"""参照ラベルと手がかり分析で共有する信号処理（numpy / scipy。システム Python 3.10 で動く）。"""
from __future__ import annotations

import numpy as np
from files import SR, f32_path
from scipy import signal

ENV_RATE = 500  # 包絡のサンプル数/秒


def load(name: str) -> np.ndarray:
    return np.fromfile(f32_path(name), dtype=np.float32).astype(np.float64)


def bandpass(x: np.ndarray, lo: float = 25.0, hi: float = 150.0, sr: int = SR) -> np.ndarray:
    sos = signal.butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    return signal.sosfiltfilt(sos, x)


def envelope(xb: np.ndarray, sr: int = SR, rate: int = ENV_RATE, smooth_s: float = 0.03) -> np.ndarray:
    """ヒルベルト包絡を rate Hz に落として ~smooth_s 秒の窓で平滑化。"""
    env = np.abs(signal.hilbert(xb))
    step = sr // rate
    n = len(env) // step
    env = env[: n * step].reshape(n, step).mean(axis=1)
    w = max(1, int(round(smooth_s * rate)))
    k = np.hanning(2 * w + 1)
    k /= k.sum()
    return np.convolve(env, k, mode="same")


def local_level(env: np.ndarray, rate: int = ENV_RATE, win_s: float = 8.0, q: float = 90.0) -> np.ndarray:
    """局所的な山の大きさの目安（移動パーセンタイル）。"""
    from scipy.ndimage import percentile_filter

    hop = rate // 10
    sub = env[::hop]
    w = max(3, int(win_s * 10) | 1)
    lv = percentile_filter(sub, q, size=w, mode="nearest")
    lv = np.maximum(lv, 1e-6)
    return np.interp(np.arange(len(env)), np.arange(len(sub)) * hop, lv)
