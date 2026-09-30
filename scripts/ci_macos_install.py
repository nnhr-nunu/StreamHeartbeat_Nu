"""Mac CI: macOS 12 でも動く wheel だけを集めてから入れる。

CI の Mac は新しい OS なので、そのまま pip で入れると macOS 13 以降向けの部品が混ざる。
2016 年の MacBook Pro など macOS 12 までの Mac でも開けるよう、macOS 12 向けの wheel に限る。
参考: StreamMediaViewer(ぬ) の同名スクリプト。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = Path.home() / "macos12-wheels"
# pyproject に無いが CI で要るもの（Pillow はアイコンを icns にするときだけ使う）
EXTRA = ["setuptools", "wheel", "Pillow"]


def _platforms() -> list[str]:
    arch = subprocess.check_output(["uname", "-m"], text=True).strip()
    plats = ["macosx_12_0_universal2"]
    if arch == "x86_64":
        plats.append("macosx_12_0_x86_64")
    else:
        plats.append("macosx_12_0_arm64")
    return plats


def _requirements_from_pyproject() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    reqs: list[str] = []
    collecting = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("dependencies") or stripped.startswith("dev ="):
            collecting = True
            continue
        if collecting and stripped.startswith("]"):
            collecting = False
            continue
        if not collecting:
            continue
        match = re.search(r'"([^"]+)"', stripped)
        if match is None:
            continue
        req = match.group(1)
        if "sys_platform != 'darwin'" in req:
            continue
        reqs.append(req.split(";")[0].strip())
    return reqs


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    WHEELHOUSE.mkdir(parents=True, exist_ok=True)
    plat_args: list[str] = []
    for plat in _platforms():
        plat_args.extend(["--platform", plat])
    pip = [sys.executable, "-m", "pip"]
    _run(
        [
            *pip,
            "download",
            "-d",
            str(WHEELHOUSE),
            "--python-version",
            "310",
            *plat_args,
            "--only-binary=:all:",
            *_requirements_from_pyproject(),
            *EXTRA,
        ]
    )
    offline = ["install", "--no-index", "--find-links", str(WHEELHOUSE)]
    _run([*pip, *offline, *EXTRA])
    _run([*pip, *offline, "-e", f"{ROOT}[dev]"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
