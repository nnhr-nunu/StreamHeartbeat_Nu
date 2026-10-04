"""心音に雑音（話し声・キーボード・衣擦れ）を重ねて、検出がどれだけ崩れるかを測る。

実行（venv の Python。先に noise_gen.py でシステムの Python から雑音を作っておく）:
    D:\\Dev\\StreamHeartbeat_Nu\\.venv\\Scripts\\python.exe noise_eval.py
    ... noise_eval.py --level 0.3 --level 0.6        # 雑音の強さ（下記）
    ... noise_eval.py --tag before / --compare before
    ... noise_eval.py --set NOISE_TONE_MARGIN=3.0    # detect.py の定数を差し替えて試す

雑音の強さ: 心音の帯域（18〜180 Hz）での雑音の RMS が、S1 の鳴り始めから 0.1 秒の RMS（中央値）の
何倍か。雑音は 5 秒目から録音の終わりまで重ねる（足りなければ繰り返す）。
出力:
  F1b / BPM10  run_eval と同じ採点（F1b は S1/S2 の取り違えを無視した F1、--rows で録音ごと）
  心音なし     ごく小さな下地の雑音に雑音だけを重ねたときの、1 分あたりの誤検出の拍数と、
               心拍数を出してしまった時間の割合
"""

from __future__ import annotations

import array
import json
import math
import statistics
import sys
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

from files import CACHE, SR, f32_path  # noqa: E402
from run_eval import CHUNK, RESULTS, apply_overrides, load_ref, score  # noqa: E402

NOISES = ["speech_air", "speech_body", "typing", "rustle"]
NAMES = ["失神前後", "不安定", "緊張", "営み", "心尖部", "LMSB", "バクバク", "走った後"]
START = 5.0
MAX_SECONDS = 150.0
ALONE_SECONDS = 60.0


def _load(path: Path) -> list[float]:
    a = array.array("f")
    a.frombytes(path.read_bytes())
    return a.tolist()


def band_pass(x: list[float]) -> list[float]:
    """強さを測る帯域（18〜180 Hz の 1 次）。検出器の帯域を変えて試しても、雑音の強さは変えない。"""
    lp_a = 1.0 - math.exp(-2.0 * math.pi * 180.0 / SR)
    hp_a = 1.0 - math.exp(-2.0 * math.pi * 18.0 / SR)
    lp = hp = 0.0
    out = []
    for v in x:
        lp += lp_a * (v - lp)
        hp += hp_a * (lp - hp)
        out.append(lp - hp)
    return out


def _band_rms(x: list[float]) -> float:
    y = band_pass(x)
    return math.sqrt(sum(v * v for v in y) / max(1, len(y)))


def heart_level(x: list[float], s1: list[float]) -> float:
    y = band_pass(x)
    levels = []
    for t in s1:
        i = int(t * SR)
        seg = y[i : i + int(0.1 * SR)]
        if len(seg) > 10:
            levels.append(math.sqrt(sum(v * v for v in seg) / len(seg)))
    return statistics.median(levels) if levels else 0.01


def mix(clean: list[float], noise: list[float], gain: float) -> list[float]:
    out = list(clean)
    start = int(START * SR)
    n = len(noise)
    for i in range(start, len(out)):
        out[i] += gain * noise[(i - start) % n]
    return out


def run(x: list[float], overrides: list[str]) -> dict:
    import stream_heartbeat.session as sess_mod

    if overrides:
        apply_overrides(overrides)
    session = sess_mod.HeartSession()
    beats: list[float] = []
    orig = session.clock.feed_beat

    def spy(t: float) -> None:
        beats.append(t)
        orig(t)

    session.clock.feed_beat = spy  # type: ignore[method-assign]
    trace = []
    for i in range(0, len(x), CHUNK):
        session.tick(i / SR, x[i : i + CHUNK], float(SR))
        trace.append((session.now, session.clock.bpm, session.clock.detected))
    return dict(beats=beats, trace=trace, duration=len(x) / SR)


def _work(args: tuple) -> tuple:
    name, noise, level, overrides = args
    ref = load_ref(name)
    clean = _load(f32_path(name))[: int(MAX_SECONDS * SR)]
    ref["s1"] = [t for t in ref["s1"] if t < len(clean) / SR]
    ref["s2"] = [t for t in ref["s2"] if t < len(clean) / SR]
    if noise == "clean":
        x = clean
    else:
        nz = _load(CACHE / f"noise_{noise}.f32")
        gain = level * heart_level(clean, ref["s1"]) / max(_band_rms(nz), 1e-9)
        x = mix(clean, nz, gain)
    s = score(run(x, overrides), ref)
    bpm10 = s.get("bpm10", 0.0)
    return (name, noise, level, s.get("f1_best", 0.0), s.get("p", 0.0), s.get("r", 0.0),
            0.0 if math.isnan(bpm10) else bpm10)


def _alone(args: tuple) -> tuple:
    noise, level, overrides = args
    import random

    rnd = random.Random(3)
    nz = _load(CACHE / f"noise_{noise}.f32")[: int(ALONE_SECONDS * SR)]
    # 心音の代わりの基準: 帯域の RMS 0.02 を「心音の大きさ」とみなす
    gain = level * 0.02 / max(_band_rms(nz), 1e-9)
    x = [gain * v + rnd.gauss(0.0, 0.0005) for v in nz]
    r = run(x, overrides)
    shown = sum(1 for t, _bpm, det in r["trace"] if det and t > 3.0)
    return noise, level, len(r["beats"]) * 60.0 / ALONE_SECONDS, shown / max(1, len(r["trace"]))


def main() -> None:
    argv = sys.argv[1:]
    levels = [float(argv[i + 1]) for i, a in enumerate(argv) if a == "--level"] or [0.3, 0.6]
    overrides = [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else None
    cmp = argv[argv.index("--compare") + 1] if "--compare" in argv else None
    names = [a for a in argv if a in NAMES] or NAMES
    jobs = [(n, "clean", 0.0, overrides) for n in names]
    jobs += [(n, z, lv, overrides) for n in names for z in NOISES for lv in levels]
    alone_jobs = [(z, lv, overrides) for z in NOISES for lv in levels]
    with Pool() as pool:
        rows = pool.map(_work, jobs)
        alone = pool.map(_alone, alone_jobs)
    result = {"rows": rows, "alone": alone}
    old = None
    if cmp:
        old = json.loads((RESULTS / f"noise_{cmp}.json").read_text(encoding="utf-8"))
    old_rows = {(r[0], r[1], r[2]): r for r in old["rows"]} if old else {}
    old_alone = {(r[0], r[1]): r for r in old["alone"]} if old else {}
    verbose = "--rows" in argv
    if verbose:
        print(f"{'録音':<8}{'雑音':<12}{'強さ':>5}{'F1b':>7}{'P':>7}{'R':>7}{'BPM10':>7}")
    for name, noise, level, f, p, r, b in rows if verbose else []:
        diff = ""
        prev = old_rows.get((name, noise, level))
        if prev:
            diff = f"  ({f - prev[3]:+.3f} / {b - prev[6]:+.2f})"
        print(f"{name:<8}{noise:<12}{level:>5.1f}{f:>7.3f}{p:>7.3f}{r:>7.3f}{b:>7.2f}{diff}")
    print(f"{'平均':<5}{'雑音':<12}{'強さ':>5}{'F1b':>7}{'BPM10':>7}")
    for noise in ["clean", *NOISES]:
        for level in [0.0] if noise == "clean" else levels:
            sel = [row for row in rows if row[1] == noise and row[2] == level]
            fs = statistics.mean(row[3] for row in sel)
            bs = statistics.mean(row[6] for row in sel)
            prev = [old_rows[(row[0], noise, level)] for row in sel
                    if (row[0], noise, level) in old_rows]
            diff = ""
            if prev:
                pf = statistics.mean(p[3] for p in prev)
                pb = statistics.mean(p[6] if len(p) > 6 else 0.0 for p in prev)
                diff = f"  ({fs - pf:+.3f} / {bs - pb:+.2f})"
            print(f"MEAN {noise:<12}{level:>5.1f}{fs:>7.3f}{bs:>7.2f}{diff}")
    print("心音なし: 1 分あたりの誤検出 / 心拍数を出した割合")
    for noise, level, per_min, shown in alone:
        prev = old_alone.get((noise, level))
        diff = f"  (前 {prev[2]:.1f} / {prev[3]:.2f})" if prev else ""
        print(f"  {noise:<12}{level:>5.1f}{per_min:>7.1f}{shown:>7.2f}{diff}")
    if tag:
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / f"noise_{tag}.json").write_text(json.dumps(result, ensure_ascii=False),
                                                   encoding="utf-8")


if __name__ == "__main__":
    main()
