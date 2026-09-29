"""アプリと同じ経路 (samples.load_audio_mono) で全録音をデコードし、生 float32 で保存する。
venv の Python で実行: .venv\Scripts\python.exe decode_cache.py
"""
import array
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from files import FILES, SR, f32_path  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

app = QCoreApplication([])
from stream_heartbeat.samples import load_audio_mono  # noqa: E402

for name, p in FILES.items():
    out = f32_path(name)
    if out.exists() and "--force" not in sys.argv:
        print(name, "cached")
        continue
    x = load_audio_mono(Path(p))
    out.write_bytes(array.array("f", x).tobytes())
    print(f"{name}: {len(x)/SR:.1f} s, peak {max(abs(v) for v in x):.3f}")
