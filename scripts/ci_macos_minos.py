"""Mac CI: 作った .app の中に、macOS 12 より新しい OS を要求する部品が無いか見る。

参考: StreamMediaViewer(ぬ) の同名スクリプト。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist" / "StreamHeartbeat.app"
MINOS_RE = re.compile(r"\bminos\s+(\d+)(?:\.(\d+))?", re.I)
VERSION_RE = re.compile(
    r"cmd LC_VERSION_MIN_MACOSX.*?version\s+(\d+)(?:\.(\d+))?",
    re.I | re.S,
)


def _macho_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        proc = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True)
        if "Mach-O" in proc.stdout:
            files.append(path)
    return files


def _parse_pair(match: re.Match[str]) -> tuple[int, int]:
    return int(match.group(1)), int(match.group(2) or 0)


def _minos(path: Path) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    proc = subprocess.run(["vtool", "-show-build", str(path)], capture_output=True, text=True)
    for match in MINOS_RE.finditer(proc.stdout):
        pair = _parse_pair(match)
        if best is None or pair > best:
            best = pair
    if best is not None:
        return best
    proc = subprocess.run(["otool", "-l", str(path)], capture_output=True, text=True)
    for match in (*MINOS_RE.finditer(proc.stdout), *VERSION_RE.finditer(proc.stdout)):
        pair = _parse_pair(match)
        if best is None or pair > best:
            best = pair
    return best


def main() -> int:
    if not APP.is_dir():
        print(f"missing app at {APP}", flush=True)
        return 1
    too_new: list[str] = []
    for path in _macho_files(APP):
        found = _minos(path)
        rel = path.relative_to(APP)
        print(f"{found} {rel}", flush=True)
        if found is not None and found[0] > 12:
            too_new.append(f"{found[0]}.{found[1]} {rel}")
    if too_new:
        detail = "macOS 12 cannot load:\n" + "\n".join(too_new)
        safe = detail.replace("%", "%25").replace("\r", " ").replace("\n", "%0A")
        print(f"::error file=scripts/ci_macos_minos.py::{safe}", flush=True)
        print(detail, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
