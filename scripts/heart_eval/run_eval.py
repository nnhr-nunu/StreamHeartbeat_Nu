"""ライブ検出器（HeartSession）をオフラインで走らせて、参照ラベルに対する精度を出す。

実行（venv の Python 3.10。numpy 不要）:
    D:\\Dev\\StreamHeartbeat_Nu\\.venv\\Scripts\\python.exe run_eval.py            # 全ファイル・並列
    ... run_eval.py 失神前後 営み                                                  # 一部だけ
    ... run_eval.py --detail                                                       # 30 秒ごとの内訳も出す
    ... run_eval.py --all                                                          # 参照が怪しい区間も採点に入れる
    ... run_eval.py --tag before / --tag after                                     # results/<tag>.json に保存（比較用）
    ... run_eval.py --compare before                                               # 保存済みとの差分を出す
    ... run_eval.py --set RHYTHM_GUARD=0.7 --set PEAK_WAIT=0.05                    # detect.py の定数を一時的に差し替えて試す（src は変えない）
    ... run_eval.py --src C:\...\work\src                                        # パッチを当てた src のコピーで走らせる

前提:
  * decode_cache.py で 16 kHz モノラルにデコード済み（無ければここで自動デコード。Qt が要る）。
  * labels/*.json は reference.py（システム Python）が作る。
  * アプリと同じ入り方: 16 ms（256 サンプル）ごとに session.tick(t, samples, 16000) を呼ぶ。
    プロファイルは既定（校正・クリック拍なし）。同梱サンプルの型は corr_min=0 で使われないので読み込みを省く
    （--with-bundled で読む）。
採点:
  F1        検出拍 vs 参照 S1、許容 ±0.12 s、1 対 1 の貪欲マッチ（時間差の小さい組から）。
  BPM10     表示 BPM (clock.bpm) が参照 BPM の ±10% に入っている時間の割合（0.25 s 刻み、最初の 3 s は除く）。
            参照 BPM = 前後 5 s の S1 間隔の中央値。
  phase     検出拍のうち、参照 S2 のほうが S1 より近く、かつ S2 から ±0.12 s 以内のものの割合。
  F1@S2     参考: S1 と S2 の役を入れ替えた参照で採点した F1（S1/S2 の区別が付かない録音の目安）。
  F1best    max(F1, F1@S2)。S1/S2 の取り違えを無視した「拍の拾い方」だけの精度。
  conf      参照の S1/S2 の確かさ（reference.py の phase_conf）。low の録音は F1 / phase が当てにならない
            （高心拍で規則的、短い、雑音が多い）ので、その録音は F1best を見る。
  MEAN(hi+med) は conf が high/medium の録音だけの平均。回帰チェックの主指標はこれと F1best 平均。
"""
from __future__ import annotations

import array
import bisect
import json
import math
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_SRC = str(HERE.parents[1] / "src")
if "--src" in sys.argv:  # 別の src（パッチを当てたコピー）で走らせる
    _SRC = sys.argv[sys.argv.index("--src") + 1]
sys.path.insert(0, _SRC)

from files import FILES, SR, f32_path  # noqa: E402

CHUNK = 256  # 16 ms（操作画面のタイマーと同じ）
TOL = 0.12
WARM = 3.0
GRID = 0.25
LABELS = HERE / "labels"
RESULTS = HERE / "results"


# ---------------------------------------------------------------- 検出器を走らせる
def ensure_cache(names: list[str]) -> None:
    missing = [n for n in names if not f32_path(n).exists()]
    if not missing:
        return
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])  # noqa: F841
    from stream_heartbeat.samples import load_audio_mono

    for n in missing:
        x = load_audio_mono(Path(FILES[n]))
        f32_path(n).write_bytes(array.array("f", x).tobytes())


def apply_overrides(overrides: list[str]) -> None:
    """--set RHYTHM_GUARD=0.7 のように detect.py のモジュール定数を（プロセス内だけ）差し替える。src は変えない。"""
    import stream_heartbeat.detect as det_mod

    mods = [det_mod]
    for item in overrides:
        key, val = item.split("=", 1)
        hit = False
        for mod in mods:
            if hasattr(mod, key):
                setattr(mod, key, type(getattr(mod, key))(float(val)))
                hit = True
        if not hit:
            raise SystemExit(f"{key} という定数は無い")


def run_detector(
    name: str,
    with_bundled: bool = False,
    max_seconds: float | None = None,
    overrides: list[str] | None = None,
) -> dict:
    import stream_heartbeat.session as sess_mod

    if overrides:
        apply_overrides(overrides)
    if not with_bundled:
        sess_mod.bundled_heart_sessions = lambda: []
    a = array.array("f")
    a.frombytes(f32_path(name).read_bytes())
    x = a.tolist()
    if max_seconds:
        x = x[: int(max_seconds * SR)]
    session = sess_mod.HeartSession()
    beats: list[float] = []
    orig = session.clock.feed_beat

    def spy(t: float) -> None:
        beats.append(t)
        orig(t)

    session.clock.feed_beat = spy  # type: ignore[method-assign]
    trace: list[tuple[float, int, bool]] = []
    t0 = time.time()
    for i in range(0, len(x), CHUNK):
        chunk = x[i : i + CHUNK]
        session.tick(i / SR, chunk, float(SR))
        trace.append((session.now, session.clock.bpm, session.clock.detected))
    return dict(name=name, beats=beats, trace=trace, seconds=time.time() - t0, duration=len(x) / SR)


# ---------------------------------------------------------------- 採点
def load_ref(name: str) -> dict:
    r = json.loads((LABELS / f"{name}.json").read_text(encoding="utf-8"))
    r["s2"] = [v for v in r["s2"] if v is not None]
    r.setdefault("bad", [])
    r.setdefault("phase_conf", "low")
    return r


def in_bad(t: float, bad: list[list[float]]) -> bool:
    return any(a <= t <= b for a, b in bad)


def match(ref: list[float], det: list[float], tol: float = TOL) -> int:
    pairs = []
    j0 = 0
    for i, r in enumerate(ref):
        while j0 < len(det) and det[j0] < r - tol:
            j0 += 1
        j = j0
        while j < len(det) and det[j] <= r + tol:
            pairs.append((abs(det[j] - r), i, j))
            j += 1
    pairs.sort()
    used_r, used_d = set(), set()
    for _, i, j in pairs:
        if i not in used_r and j not in used_d:
            used_r.add(i)
            used_d.add(j)
    return len(used_r)


def f1(ref: list[float], det: list[float]) -> tuple[float, float, float]:
    tp = match(ref, det)
    p = tp / len(det) if det else 0.0
    r = tp / len(ref) if ref else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return f, p, r


def nearest(sorted_list: list[float], t: float) -> float:
    k = bisect.bisect_left(sorted_list, t)
    best = math.inf
    for m in (k - 1, k):
        if 0 <= m < len(sorted_list):
            best = min(best, abs(sorted_list[m] - t))
    return best


def ref_bpm_at(s1: list[float], t: float, half: float = 5.0) -> float | None:
    gaps = [b - a for a, b in zip(s1[:-1], s1[1:]) if t - half <= 0.5 * (a + b) <= t + half]
    if not gaps:
        return None
    return 60.0 / statistics.median(gaps)


def score(run: dict, ref: dict, use_bad: bool = True) -> dict:
    bad = ref["bad"] if use_bad else []
    s1 = [t for t in ref["s1"] if not in_bad(t, bad)]
    s2 = [t for t in ref["s2"] if not in_bad(t, bad)]
    det = [t for t in run["beats"] if not in_bad(t, bad)]
    if not s1:
        return {}
    lo, hi = s1[0] - 0.3, s1[-1] + 0.3
    det = [t for t in det if lo <= t <= hi]
    f, p, r = f1(s1, det)
    f_swap = f1(s2, det)[0] if s2 else 0.0
    ph = 0
    s1_all, s2_all = sorted(ref["s1"]), sorted(ref["s2"])
    for t in det:
        a, b = nearest(s1_all, t), nearest(s2_all, t)
        if b < a and b <= TOL:
            ph += 1
    phase = ph / len(det) if det else 0.0
    ok = tot = 0
    ratios = []
    trace = run["trace"]
    step = max(1, int(round(GRID / (CHUNK / SR))))
    for k in range(0, len(trace), step):
        t, bpm, _ = trace[k]
        if t < WARM or in_bad(t, bad) or t < lo or t > hi:
            continue
        rb = ref_bpm_at(ref["s1"], t)
        if rb is None:
            continue
        tot += 1
        ratios.append(bpm / rb)
        if abs(bpm - rb) <= 0.10 * rb:
            ok += 1
    bpm10 = ok / tot if tot else float("nan")
    return dict(
        f1=f,
        p=p,
        r=r,
        f1_s2=f_swap,
        f1_best=max(f, f_swap),
        conf=ref["phase_conf"],
        bpm10=bpm10,
        phase=phase,
        n_ref=len(s1),
        n_det=len(det),
        bpm_ratio_med=statistics.median(ratios) if ratios else float("nan"),
        excluded_s=sum(b - a for a, b in bad),
    )


def detail_rows(run: dict, ref: dict, width: float = 30.0) -> list[str]:
    rows = []
    s1_all, s2_all = sorted(ref["s1"]), sorted(ref["s2"])
    det = run["beats"]
    trace = run["trace"]
    step = max(1, int(round(GRID / (CHUNK / SR))))
    a = 0.0
    while a < run["duration"]:
        b = a + width
        d = [t for t in det if a <= t < b]
        r = [t for t in s1_all if a <= t < b]
        if not r:
            a = b
            continue
        f, p, rc = f1(r, d)
        ph = sum(1 for t in d if nearest(s2_all, t) < nearest(s1_all, t) and nearest(s2_all, t) <= TOL)
        ok = tot = 0
        bb = []
        for k in range(0, len(trace), step):
            t, bpm, _ = trace[k]
            if not (a <= t < b) or t < WARM:
                continue
            rb = ref_bpm_at(ref["s1"], t)
            if rb is None:
                continue
            tot += 1
            bb.append(bpm)
            ok += abs(bpm - rb) <= 0.1 * rb
        refb = 60 / statistics.median([y - x for x, y in zip(r[:-1], r[1:])]) if len(r) > 2 else float("nan")
        bad = "  [ref unreliable]" if in_bad(a + width / 2, ref["bad"]) else ""
        rows.append(
            f"  {a:5.0f}-{b:4.0f}s  ref {refb:5.1f} BPM  disp {statistics.median(bb) if bb else float('nan'):5.1f}  "
            f"F1 {f:.2f} (P {p:.2f} R {rc:.2f})  phase {ph/len(d) if d else 0:.2f}  "
            f"BPM10 {ok/tot if tot else float('nan'):.2f}{bad}"
        )
        a = b
    return rows


# ---------------------------------------------------------------- main
def _work(args: tuple) -> dict:
    name, with_bundled, max_seconds, overrides = args
    return run_detector(name, with_bundled, max_seconds, overrides)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    flags = {a for a in argv if a.startswith("--")}
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else None
    cmp_tag = argv[argv.index("--compare") + 1] if "--compare" in argv else None
    ms = float(argv[argv.index("--seconds") + 1]) if "--seconds" in argv else None
    overrides = [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]
    src_arg = argv[argv.index("--src") + 1] if "--src" in argv else None
    skip = {tag, cmp_tag, str(ms) if ms else None, src_arg, *overrides}
    names = [a for a in argv if not a.startswith("--") and a not in skip] or list(FILES)
    for n in names:
        if n not in FILES:
            sys.exit(f"unknown file {n}; choose from {list(FILES)}")
    ensure_cache(names)
    import stream_heartbeat

    print(f"[detector from {Path(stream_heartbeat.__file__).parent}]")
    t0 = time.time()
    jobs = [(n, "--with-bundled" in flags, ms, overrides) for n in names]
    if "--serial" in flags or len(jobs) == 1:
        runs = [_work(j) for j in jobs]
    else:
        with Pool(min(len(jobs), 8)) as pool:
            runs = pool.map(_work, jobs, chunksize=1)
    RESULTS.mkdir(exist_ok=True)
    rows, out = [], {}
    for run in sorted(runs, key=lambda r: names.index(r["name"])):
        ref = load_ref(run["name"])
        sc = score(run, ref, use_bad="--all" not in flags)
        out[run["name"]] = dict(score=sc, beats=run["beats"], seconds=run["seconds"])
        rows.append((run["name"], sc, run, ref))
    hdr = (
        f"{'file':<10}{'dur':>5}{'conf':>7}{'F1':>7}{'P':>6}{'R':>6}{'F1@S2':>7}{'F1best':>7}{'BPM10':>7}{'phase':>7}"
        f"{'dispBPM/ref':>12}{'run s':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    keys = ["f1", "p", "r", "bpm10", "phase", "f1_s2", "f1_best"]
    for name, sc, run, ref in rows:
        if not sc:
            print(f"{name:<10} (no reference)")
            continue
        print(
            f"{name:<10}{run['duration']:5.0f}{sc['conf']:>7}{sc['f1']:7.3f}{sc['p']:6.2f}{sc['r']:6.2f}"
            f"{sc['f1_s2']:7.3f}{sc['f1_best']:7.3f}{sc['bpm10']:7.2f}"
            f"{('(%.2f)' if sc['conf'] == 'low' else '%.2f') % sc['phase']:>7}"
            f"{sc['bpm_ratio_med']:12.2f}{run['seconds']:6.0f}"
        )
    good = [sc for _, sc, _, _ in rows if sc]
    mean = {k: statistics.mean(s[k] for s in good if not math.isnan(s[k])) for k in keys}
    print("-" * len(hdr))
    print(
        f"{'MEAN all':<10}{'':5}{'':>7}{mean['f1']:7.3f}{mean['p']:6.2f}{mean['r']:6.2f}"
        f"{mean['f1_s2']:7.3f}{mean['f1_best']:7.3f}{mean['bpm10']:7.2f}{mean['phase']:7.2f}"
    )
    hm = [sc for sc in good if sc["conf"] in ("high", "medium")]
    if hm:
        mh = {k: statistics.mean(s[k] for s in hm if not math.isnan(s[k])) for k in keys}
        print(
            f"{'MEAN hi+med':<10}{'':5}{'':>7}{mh['f1']:7.3f}{mh['p']:6.2f}{mh['r']:6.2f}"
            f"{mh['f1_s2']:7.3f}{mh['f1_best']:7.3f}{mh['bpm10']:7.2f}{mh['phase']:7.2f}   (conf high/medium only)"
        )
        out["_mean_hm"] = mh
    excl = {n: sc.get("excluded_s", 0) for n, sc, _, _ in rows if sc and sc.get("excluded_s")}
    print("(conf=low: F1 and phase depend on an arbitrary S1/S2 choice -> read F1best; phase shown in parentheses)")
    print(f"(wall {time.time()-t0:.0f}s; scoring excludes reference-unreliable spans {excl or 'none'}; --all includes them)")
    out["_mean"] = mean
    if "--detail" in flags:
        for name, sc, run, ref in rows:
            print(f"\n[{name}]")
            print("\n".join(detail_rows(run, ref)))
    if tag:
        (RESULTS / f"{tag}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"saved results/{tag}.json")
    if cmp_tag:
        old = json.loads((RESULTS / f"{cmp_tag}.json").read_text(encoding="utf-8"))
        print(f"\nvs {cmp_tag}:  (F1 / BPM10 / phase)")
        for name, sc, _, _ in rows:
            o = old.get(name, {}).get("score")
            if o and sc:
                print(
                    f"  {name:<10} F1 {o['f1']:.3f}->{sc['f1']:.3f}  BPM10 {o['bpm10']:.3f}->{sc['bpm10']:.3f}"
                    f"  phase {o['phase']:.2f}->{sc['phase']:.2f}"
                )
        om = old.get("_mean", {})
        print(
            f"  {'MEAN':<10} F1 {om.get('f1', float('nan')):.3f}->{mean['f1']:.3f}"
            f"  BPM10 {om.get('bpm10', float('nan')):.2f}->{mean['bpm10']:.2f}"
            f"  phase {om.get('phase', float('nan')):.2f}->{mean['phase']:.2f}"
        )


if __name__ == "__main__":
    main()
