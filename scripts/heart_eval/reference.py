"""オフライン（非因果）の S1 ラベラー。検出器の正解として使う。

システム Python 3.10（numpy / scipy あり）で実行:
    python reference.py [名前 ...] [--force]
結果は labels/<名前>.json にキャッシュ（S1/S2 の時刻・山の大きさ・信頼度）。
run_eval.py は JSON だけ読むので numpy は要らない。

方法
  1. 25-150 Hz のバンドパス（ゼロ位相）→ ヒルベルト包絡 → 30 ms 平滑 → 500 Hz。
  2. 包絡の山を候補にする（局所 90 パーセンタイルに対する強さ z で選別）。
  3. 動的計画法。状態 = (前の S1, いまの S1, いまの S2 または無し)。コスト:
       - 山を説明する報酬（S1・S2 に選んだ山はどれも同じ式。大きさで S1/S2 は区別しない）
       - S2 なし: 一定のペナルティ
       - 収縮期 s = t(S2) - t(S1) の事前分布（中心 0.28 s、対数で σ 0.45）
       - 収縮期の一定さ: (log s_new - log s_old) を σ 0.08 で罰する（上限あり）
         → 収縮期は拍ごとの変動が小さい、拡張期は大きい、という手がかり
       - 拍の長さの滑らかさ: (log T_new - log T_old) を σ 0.15 で罰する（上限あり。休止・期外収縮を許す）
  振幅・幅・周波数などの「音色」は S1/S2 の判定に使っていない（手がかり分析が循環しないように）。
  ただし収縮期が拡張期と区別できない場合（高心拍で規則的）は時間の手がかりだけでは決まらないので、
  信頼度（timing_margin）を出し、低いところは「参考程度」と明記する。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from dsp import ENV_RATE, bandpass, envelope, load, local_level
from files import FILES, SR
from scipy import signal

LABELS = Path(__file__).resolve().parent / "labels"
LABELS.mkdir(exist_ok=True)

P = dict(
    z_min=2.0,         # 候補として使う最小の SNR（雑音の床に対する山の比）
    reward=1.5,        # 強い山を説明する報酬（コストから引く）
    z_lo=2.5, z_hi=7.5,
    c_nos=2.0,         # S2 なし
    sys_k=0.36, sys_sigma=0.25, T_eff_max=1.0,   # 収縮期の事前分布: s ~ 0.36*sqrt(T) (対数 σ 0.25)
    sc_sigma=0.10, sc_cap=3.0, c_unk=0.6,
    T_sigma=0.15, T_cap=3.0, c_start=1.0,
    T_min=0.27, T_max=6.0,
    s_min=0.10, s_max=0.60, d_min=0.08,
)


def noise_floor(env: np.ndarray, rate: int = ENV_RATE, win_s: float = 6.0, q: float = 12.0) -> np.ndarray:
    from scipy.ndimage import percentile_filter

    hop = rate // 10
    sub = env[::hop]
    fl = percentile_filter(sub, q, size=max(3, int(win_s * 10) | 1), mode="nearest")
    fl = np.maximum(fl, 1e-6)
    return np.interp(np.arange(len(env)), np.arange(len(sub)) * hop, fl)


def candidates(env: np.ndarray, rate: int = ENV_RATE):
    """包絡の山。z は雑音の床に対する強さ（SNR）。"""
    level = local_level(env, rate)
    floor = noise_floor(env, rate)
    pk, _ = signal.find_peaks(env, distance=int(0.07 * rate), prominence=0.03 * level)
    z = env[pk] / floor[pk]
    keep = z >= P["z_min"]
    return pk[keep], env[pk[keep]], z[keep]


def _reward(z: np.ndarray) -> np.ndarray:
    """SNR が z_lo 以下なら 0、z_hi 以上なら満額。"""
    return P["reward"] * np.clip(np.log(np.maximum(z, 1e-9) / P["z_lo"]) / np.log(P["z_hi"] / P["z_lo"]), 0.0, 1.0)


def _c_sys(s: np.ndarray, T: float) -> np.ndarray:
    """収縮期 s の事前コスト。拍の長さ T が短いほど収縮期も短い（s ≈ 0.36√T）。S2 なし(nan)は c_nos。"""
    te = min(T, P["T_eff_max"])
    with np.errstate(invalid="ignore", divide="ignore"):
        c = 0.5 * (np.log(s / (P["sys_k"] * np.sqrt(te))) / P["sys_sigma"]) ** 2
    return np.where(np.isnan(s), P["c_nos"], c)


def solve_segment(t: np.ndarray, z: np.ndarray):
    """1 区間の DP。戻り値: [(S1 の index, S2 の index or -1), ...]。"""
    n = len(t)
    R = _reward(z)
    INF = 1e9
    O = []          # 各ノードの S2 選択肢 [-1, k, ...]
    Pr = []         # 各ノードの前の S1 選択肢 [-1(start), i, ...]
    V = []
    BK = []
    BI = []
    lo_idx = np.searchsorted(t, t + P["T_min"], side="left")
    hi_idx = np.searchsorted(t, t + P["T_max"], side="right")
    s_lo = np.searchsorted(t, t + P["s_min"], side="left")
    s_hi = np.searchsorted(t, t + P["s_max"], side="right")
    # 前の S1 の選択肢（j から見て）
    preds_of = [[] for _ in range(n)]
    for i in range(n):
        for j in range(lo_idx[i], hi_idx[i]):
            preds_of[j].append(i)
    for j in range(n):
        ks = list(range(s_lo[j], s_hi[j]))
        O.append([-1] + ks)
        Pr.append([-1] + preds_of[j])
    for j in range(n):
        ol = O[j]
        s_new = np.array([np.nan] + [t[k] - t[j] for k in ol[1:]])
        own = np.empty(len(ol))
        own[0] = -R[j]
        if len(ol) > 1:
            own[1:] = -R[j] - R[ol[1:]]
        pj = Pr[j]
        Vj = np.full((len(pj), len(ol)), INF)
        BKj = np.zeros((len(pj), len(ol)), dtype=np.int32)
        BIj = np.zeros((len(pj), len(ol)), dtype=np.int32)
        Vj[0, :] = own + P["c_start"]
        for pi in range(1, len(pj)):
            i = pj[pi]
            Vi = V[i]
            Ti = t[j] - t[i]
            pri = Pr[i]
            Told = np.array([t[i] - t[ip] if ip >= 0 else np.nan for ip in pri])
            B = np.where(
                np.isnan(Told),
                P["c_start"] * 0.5,
                np.minimum(0.5 * (np.log(Ti / np.where(np.isnan(Told), 1.0, Told)) / P["T_sigma"]) ** 2, P["T_cap"]),
            )
            tot = Vi + B[:, None]
            best_ip = tot.argmin(0)
            M = tot[best_ip, np.arange(tot.shape[1])]
            oi = O[i]
            s_old = np.array([np.nan] + [t[k] - t[i] for k in oi[1:]])
            with np.errstate(invalid="ignore", divide="ignore"):
                dl = np.log(s_new[None, :] / s_old[:, None])
                A = np.minimum(0.5 * (dl / P["sc_sigma"]) ** 2, P["sc_cap"])
            A = np.where(np.isnan(A), P["c_unk"], A)
            # S2(k) は次の S1(j) より前でなければならない
            tk = np.array([-1e9] + [t[k] for k in oi[1:]])
            bad = (t[j] - tk) < P["d_min"]
            A = np.where(bad[:, None] & (np.arange(len(oi))[:, None] > 0), INF, A)
            tot2 = (M + _c_sys(s_old, Ti))[:, None] + A
            bk = tot2.argmin(0)
            Vj[pi, :] = tot2[bk, np.arange(tot2.shape[1])] + own
            BKj[pi, :] = bk
            BIj[pi, :] = best_ip[bk]
        V.append(Vj)
        BK.append(BKj)
        BI.append(BIj)
    # 終端: 全状態の最小
    best = (INF, None)
    for j in range(n):
        sj = np.array([np.nan] + [t[k] - t[j] for k in O[j][1:]])
        Tj = np.array([t[j] - t[ip] if ip >= 0 else 0.6 for ip in Pr[j]])
        term = np.array([_c_sys(sj, T) for T in Tj])
        tot = V[j] + term
        idx = np.unravel_index(np.argmin(tot), tot.shape)
        if tot[idx] < best[0]:
            best = (tot[idx], (j, idx[0], idx[1]))
    j, pi, li = best[1]
    path = []
    while True:
        path.append((j, O[j][li]))
        i = Pr[j][pi]
        if i == -1:
            break
        k_idx = BK[j][pi, li]
        ip_idx = BI[j][pi, li]
        j, pi, li = i, ip_idx, k_idx
    path.reverse()
    return path, best[0]


def _sc_term(a: float, b: float) -> float:
    return min(0.5 * (np.log(b / a) / P["sc_sigma"]) ** 2, P["sc_cap"])


def timing_margin(t1: np.ndarray, t2: np.ndarray, half: int = 8):
    """拍ごとの「時間の手がかりだけで見た S1/S2 の確からしさ」（nat）を 2 種類返す。

    選んだ S1/S2 と、役を入れ替えた場合（S2 を S1 とみなす）のコストの差を、前後 half 拍で足したもの。
      margin_sc    ... 収縮期の一定さ（拍ごとの変動が小さいほうが収縮期）だけ。事前分布を含まない、頑健なほう
      margin_prior ... 収縮期の長さの事前分布（s ≈ 0.36√T）だけ
    正で大きいほど今のラベルを支持する。0 付近なら時間の手がかりでは決まらない。
    """
    n = len(t1)
    d_sc = np.zeros(n)
    d_pr = np.zeros(n)
    for b in range(n - 2):
        if np.isnan(t2[b]) or np.isnan(t2[b + 1]):
            continue
        s_b, s_n = t2[b] - t1[b], t2[b + 1] - t1[b + 1]
        d_b, d_n = t1[b + 1] - t2[b], t1[b + 2] - t2[b + 1]
        if d_b <= 0.02 or d_n <= 0.02:
            continue
        Ta, Tb = t1[b + 1] - t1[b], t2[b + 1] - t2[b]
        d_sc[b] = _sc_term(d_b, d_n) - _sc_term(s_b, s_n)
        d_pr[b] = float(_c_sys(np.array([d_b]), Tb)[0]) - float(_c_sys(np.array([s_b]), Ta)[0])
    k = np.ones(2 * half + 1)
    return np.convolve(d_sc, k, mode="same"), np.convolve(d_pr, k, mode="same")


def phase_confidence(t1: np.ndarray, t2: np.ndarray) -> dict:
    """S1/S2 の取り違えの起こりにくさ。心拍数が拍ごとに揺れているとき、収縮期（S1→S2）は動かず拡張期が動く。
    隣り合う拍どうしの間隔の差の中央値で比べる: |Δ拡張期| / |Δ収縮期| が大きく、拡張期の揺れが測定の
    ゆらぎ（~10 ms）より十分大きいほど、時間の手がかりだけで S1/S2 が決まる。
      high   比 >= 2.5 かつ |Δ拡張期| >= 15 ms
      medium 比 >= 1.8
      low    それ以外（高心拍で規則的・短い/雑音の多い録音）。この場合 F1 は S1/S2 どちらとも取れる。"""
    ok = ~np.isnan(t2)
    s = (t2 - t1)[:-1]
    d = t1[1:] - t2[:-1]
    m = ok[:-1] & ok[1:]
    s, d = s[m], d[m]
    if len(s) < 6:
        return dict(ds_med=float("nan"), dd_med=float("nan"), ratio=float("nan"), phase_conf="low")
    ds = float(np.median(np.abs(np.diff(s))))
    dd = float(np.median(np.abs(np.diff(d))))
    ratio = dd / max(ds, 1e-3)
    conf = "high" if (ratio >= 2.5 and dd >= 0.015) else ("medium" if ratio >= 1.8 else "low")
    return dict(ds_med=ds, dd_med=dd, ratio=ratio, phase_conf=conf)


def unreliable_spans(res: dict) -> list[list[float]]:
    """参照が怪しい区間。(1) 心音より 2 倍以上大きい非ラベルの山（擦れ・体動）の前後 1 s、
    (2) 10 s 窓で「強いのに使われなかった山」が 35% 以上（呼吸音などで山だらけ）。"""
    t = np.array(res["cand_t"])
    a = np.array(res["cand_amp"])
    lab = np.zeros(len(t), bool)
    for i, k in zip(res["s1_idx"], res["s2_idx"]):
        lab[i] = True
        if k >= 0:
            lab[k] = True
    spans: list[list[float]] = []
    for idx in np.where(~lab)[0]:
        m = lab & (np.abs(t - t[idx]) <= 5.0)
        if not m.any():
            continue
        if a[idx] >= 2.0 * np.median(a[m]):
            spans.append([float(t[idx] - 1.0), float(t[idx] + 1.0)])
    dur = res["duration"]
    for w0 in np.arange(0, dur, 10.0):
        m = (t >= w0) & (t < w0 + 10.0)
        if (m & lab).sum() < 3:
            continue
        med = np.median(a[m & lab])
        strong = m & (a >= 0.6 * med)
        if strong.sum() and (strong & ~lab).sum() / strong.sum() >= 0.35:
            spans.append([float(w0), float(min(dur, w0 + 10.0))])
    spans.sort()
    merged: list[list[float]] = []
    for a0, b0 in spans:
        if merged and a0 <= merged[-1][1] + 2.0:
            merged[-1][1] = max(merged[-1][1], b0)
        else:
            merged.append([a0, b0])
    return [[round(max(0.0, a0), 2), round(b0, 2)] for a0, b0 in merged]


def finalize(res: dict) -> None:
    """s1_idx / s2_idx から、時刻・時間の手がかりの確かさ・怪しい区間を作る。"""
    t = np.array(res["cand_t"])
    res["s1"] = [float(t[i]) for i in res["s1_idx"]]
    res["s2"] = [float(t[k]) if k >= 0 else None for k in res["s2_idx"]]
    t1 = np.array(res["s1"])
    t2 = np.array([np.nan if v is None else v for v in res["s2"]])
    m_sc, m_pr = timing_margin(t1, t2)
    res["margin_sc"] = m_sc.tolist()
    res["margin_prior"] = m_pr.tolist()
    res["margin"] = (m_sc + m_pr).tolist()
    res["decisive_frac"] = float(np.mean(m_sc >= 4.0))
    res.update(phase_confidence(t1, t2))
    res["bad"] = unreliable_spans(res)


def hf_pair_agree(x: np.ndarray, res: dict, fc: float = 300.0) -> float:
    """各拍で「S2 のほうが S1 より高域の割合が高い」対の割合（怪しい区間は除く）。
    高域の割合 = log( E[生波形を 2 次の高域通過(fc)] / E[検出器と同じ 18-180 Hz の 1 次帯域] )、山の [-20, +40] ms。"""
    lp_a = 1.0 - np.exp(-2 * np.pi * 180.0 / SR)
    hp_a = 1.0 - np.exp(-2 * np.pi * 18.0 / SR)
    lp = signal.lfilter([lp_a], [1, -(1 - lp_a)], x)
    band = lp - signal.lfilter([hp_a], [1, -(1 - hp_a)], lp)
    hp = signal.sosfilt(signal.butter(2, fc, btype="highpass", fs=SR, output="sos"), x)
    cb = np.concatenate([[0.0], np.cumsum(band * band)])
    ch = np.concatenate([[0.0], np.cumsum(hp * hp)])
    t = np.array(res["cand_t"])
    a0, a1 = int(0.02 * SR), int(0.04 * SR)

    def ratio(idx: int) -> float:
        c = int(t[idx] * SR)
        lo, hi = max(0, c - a0), min(len(x), c + a1)
        return float(np.log((ch[hi] - ch[lo] + 1e-18) / (cb[hi] - cb[lo] + 1e-18)))

    ok = []
    for i, k in zip(res["s1_idx"], res["s2_idx"]):
        if k < 0 or any(a <= t[i] <= b for a, b in res["bad"]):
            continue
        ok.append(ratio(k) > ratio(i))
    return float(np.mean(ok)) if ok else float("nan")


def label(name: str, force: bool = False) -> dict:
    out = LABELS / f"{name}.json"
    if out.exists() and not force:
        return json.loads(out.read_text(encoding="utf-8"))
    x = load(name)
    xb = bandpass(x)
    env = envelope(xb)
    pk, amp, z = candidates(env)
    t = pk / ENV_RATE
    # 6 秒以上候補が無いところで区間に分ける
    cuts = np.where(np.diff(t) > P["T_max"])[0] + 1
    segs = np.split(np.arange(len(t)), cuts)
    s1, s2 = [], []
    total = 0.0
    for seg in segs:
        if len(seg) < 3:
            continue
        path, cost = solve_segment(t[seg], z[seg])
        total += cost
        for a, b in path:
            s1.append(int(seg[a]))
            s2.append(int(seg[b]) if b >= 0 else -1)
    res = dict(
        name=name,
        duration=len(x) / SR,
        cand_t=t.tolist(),
        cand_amp=amp.tolist(),
        cand_z=z.tolist(),
        s1_idx=s1,
        s2_idx=s2,
        cost=total,
    )
    finalize(res)
    # 音色による確認: 「S1 は S2 より高域（300 Hz~）の割合が低い」向きは、時間の手がかりが決定的な録音
    # （失神前後・不安定・緊張）で一貫して成り立つ。時間の手がかりが high/medium でも、この対の 35% 以下でしか
    # 成り立たない（ほぼ逆）なら、時間と音色が食い違っているので low に下げる。役の入れ替えは自動ではしない
    # （run_eval の F1@S2 / F1best で影響を見る）。
    res["hf_agree"] = hf_pair_agree(x, res)
    res["conflict"] = False
    if res["phase_conf"] != "low" and res["hf_agree"] <= 0.35:
        res["phase_conf"] = "low"
        res["conflict"] = True
    out.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(FILES)
    for nm in names:
        r = label(nm, force="--force" in sys.argv)
        s1 = np.array(r["s1"])
        d = np.diff(s1)
        bad_s = sum(b - a for a, b in r["bad"])
        print(
            f"{nm}: dur {r['duration']:.0f}s beats {len(s1)} median BPM {60/np.median(d):.0f} "
            f"S2 found {sum(v is not None for v in r['s2'])}  |d dia|/|d sys| = {r['ratio']:.1f} ({r['dd_med']*1000:.0f}/{r['ds_med']*1000:.0f} ms) "
            f"-> phase_conf={r['phase_conf']} hf_agree={r['hf_agree']:.0%}"
            f"{' (timing vs acoustics CONFLICT)' if r['conflict'] else ''}  unreliable {bad_s:.0f}s {r['bad']}"
        )
