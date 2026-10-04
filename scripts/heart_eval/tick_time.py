"""HeartSession.tick 1 回の時間（16 ms ごとの GUI スレッドで呼ばれる）。
    python tick_time.py <src ディレクトリ> [名前] [秒数]
"""
import array
import statistics
import sys
import time
from pathlib import Path

src = sys.argv[1]
name = sys.argv[2] if len(sys.argv) > 2 else "失神前後"
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 200.0
sys.path.insert(0, src)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stream_heartbeat.session as sess_mod  # noqa: E402
from files import SR, f32_path  # noqa: E402

a = array.array("f")
a.frombytes(f32_path(name).read_bytes())
x = a.tolist()[: int(secs * SR)]
chunks = [x[i : i + 256] for i in range(0, len(x), 256)]
best = None
for rep in range(3):
    s = sess_mod.HeartSession()
    ts = []
    pc = time.perf_counter
    for k, c in enumerate(chunks):
        t0 = pc()
        s.tick(k * 256 / SR, c, float(SR))
        ts.append(pc() - t0)
    ts_sorted = sorted(ts)
    res = (statistics.mean(ts) * 1000, statistics.median(ts) * 1000, ts_sorted[int(0.99 * len(ts))] * 1000, ts_sorted[-1] * 1000)
    if best is None or res[0] < best[0]:
        best = res
print(f"{Path(src).parent.name if 'work' in src else 'current src'}: mean {best[0]:.3f} ms  median {best[1]:.3f} ms  p99 {best[2]:.3f} ms  max {best[3]:.2f} ms  (256 サンプル/tick, {len(chunks)} ticks, 予算 16 ms)")
