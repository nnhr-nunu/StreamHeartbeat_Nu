"""心音でない音（話し声・キーボード・衣擦れ）を作って cache/noise_*.f32 に置く。

noise_eval.py が使う。

実行（numpy / scipy が要るのでシステムの Python）:
    python noise_gen.py

話し声は Windows の音声合成で作った WAV（cache/tts_*.wav）を読む。無ければ作る（PowerShell）。
  * speech_air   空気を伝わってマイクに入った声（女声と男声を交互）
  * speech_body  胸の中を伝わって聴診器に入った自分の声（高い音が落ち、基本周波数が残る）
  * typing       キーボード（カチッという広い帯域の音と、低いコトッという音）
  * rustle       衣擦れ（こすれる雑音の塊と、ときどき胸当てが擦れる低い音）
"""

from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, resample_poly, sosfilt

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
SR = 16000
SECONDS = 90.0
RNG = np.random.default_rng(7)

_TTS_TEXT = (
    "こんばんは、今日も配信に来てくれてありがとう。さっきまでゲームをしていたんだけど、"
    "ちょっと緊張しちゃって心臓がどきどきしてるんだよね。みんなは今日どんな一日だった？"
    "コメント読んでいくね。あ、それ面白い！えーと、次は何をしようかな。そうそう、昨日の夜ご飯は"
    "カレーを作ったんだけど、ちょっと辛すぎたかもしれない。明日は雑談をして、そのあとホラーゲームを"
    "やる予定です。怖いのは苦手だけど頑張るよ。では、そろそろ始めましょうか。よろしくお願いします。"
)
_VOICES = {"tts_f.wav": "Microsoft Haruka Desktop", "tts_m.wav": "Microsoft Ichiro"}


def _make_tts(path: Path, voice: str) -> None:
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SelectVoice('{voice}');"
        "$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
        " [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        " [System.Speech.AudioFormat.AudioChannel]::Mono);"
        f"$s.SetOutputToWaveFile('{path}', $f);"
        f"$s.Speak('{_TTS_TEXT * 2}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
        rate = w.getframerate()
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if rate != SR:
        x = resample_poly(x, SR, rate)
    return x


def _fit(x: np.ndarray) -> np.ndarray:
    n = int(SECONDS * SR)
    reps = int(np.ceil(n / len(x)))
    return np.tile(x, reps)[:n]


def speech() -> tuple[np.ndarray, np.ndarray]:
    parts = []
    for name, voice in _VOICES.items():
        path = CACHE / name
        if not path.is_file():
            _make_tts(path, voice)
        parts.append(_read_wav(path))
    # 女声と男声を 6 秒ずつ交互に（間に少し黙る）
    seg = int(6.0 * SR)
    gap = int(1.5 * SR)
    out = []
    for k in range(int(SECONDS / 7.5) + 1):
        src = parts[k % 2]
        start = (k // 2) * seg % max(1, len(src) - seg)
        out.append(src[start : start + seg])
        out.append(np.zeros(gap))
    air = _fit(np.concatenate(out))
    # 胸の中を伝わる声: 高い音は大きく落ち、基本周波数（100〜250 Hz）が残る
    body = sosfilt(butter(2, 450.0, "low", fs=SR, output="sos"), air)
    body = sosfilt(butter(1, 60.0, "high", fs=SR, output="sos"), body)
    return air, body


def typing() -> np.ndarray:
    n = int(SECONDS * SR)
    x = np.zeros(n)
    t = 0.5
    while t < SECONDS - 1.0:
        # 3〜10 打の塊と、その間の休み
        for _ in range(RNG.integers(3, 11)):
            t += RNG.uniform(0.09, 0.26)
            for release, gain in ((0.0, 1.0), (RNG.uniform(0.06, 0.12), 0.45)):
                i = int((t + release) * SR)
                if i + 800 >= n:
                    break
                amp = gain * RNG.uniform(0.5, 1.0)
                k = np.arange(800) / SR
                click = RNG.normal(0.0, 1.0, 800) * np.exp(-k / 0.004)
                thock = np.sin(2 * np.pi * RNG.uniform(120, 260) * k) * np.exp(-k / 0.012)
                x[i : i + 800] += amp * (0.8 * click + 0.5 * thock)
        t += RNG.uniform(0.4, 2.0)
    return x


def rustle() -> np.ndarray:
    n = int(SECONDS * SR)
    band = sosfilt(butter(2, [150.0, 5000.0], "band", fs=SR, output="sos"), RNG.normal(0, 1, n))
    env = np.zeros(n)
    t = 0.3
    while t < SECONDS - 1.5:
        dur = RNG.uniform(0.2, 1.0)
        i0, i1 = int(t * SR), int((t + dur) * SR)
        k = np.arange(i1 - i0) / SR
        shape = np.sin(np.pi * k / dur) ** 0.7
        flutter = 0.6 + 0.4 * np.sin(2 * np.pi * RNG.uniform(5, 20) * k + RNG.uniform(0, 6))
        env[i0:i1] += RNG.uniform(0.4, 1.0) * shape * flutter
        t += dur + RNG.uniform(0.2, 2.5)
    x = band * env
    # 胸当てがこすれる低い音（ときどき）
    low = sosfilt(butter(2, [25.0, 120.0], "band", fs=SR, output="sos"), RNG.normal(0, 1, n))
    return x + 0.5 * low * env * (RNG.uniform(0, 1, n) < 1.0)


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    air, body = speech()
    signals = {"speech_air": air, "speech_body": body, "typing": typing(), "rustle": rustle()}
    for name, x in signals.items():
        x = x / (np.sqrt(np.mean(x * x)) + 1e-12) * 0.05
        (CACHE / f"noise_{name}.f32").write_bytes(x.astype(np.float32).tobytes())
        print(name, f"{len(x) / SR:.0f} s")


if __name__ == "__main__":
    sys.exit(main())
