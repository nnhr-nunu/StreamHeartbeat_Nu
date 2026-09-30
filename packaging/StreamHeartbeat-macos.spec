# Mac 用の StreamHeartbeat.app を作る（GitHub Actions の Mac で使う）。
#   pyinstaller --noconfirm --clean packaging/StreamHeartbeat-macos.spec
# Windows はワークフローのコマンドだけで作れるが、Mac はマイクを使う理由の文
# （NSMicrophoneUsageDescription）を Info.plist に書かないと音を取れないので spec にしている。
# アイコンの png を icns にするのに Pillow が要る（作るときだけ。アプリには入らない）。

import re
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821  SPECPATH は PyInstaller が渡す
SRC = ROOT / "src" / "stream_heartbeat"
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
VERSION = re.search(r'^version = "([^"]+)"', PYPROJECT, re.M).group(1)

a = Analysis(  # noqa: F821
    [str(SRC / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(SRC / "assets"), "stream_heartbeat/assets")],
    hiddenimports=["PySide6.QtMultimedia"],
    # 使わない大きな Qt を入れない（参考: StreamMediaViewer(ぬ) の Mac 版と同じ）
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtQuick",
        "PySide6.QtQml",
    ],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StreamHeartbeat",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="StreamHeartbeat", upx=False)  # noqa: F821
app = BUNDLE(  # noqa: F821
    coll,
    name="StreamHeartbeat.app",
    icon=str(SRC / "assets" / "app_icon.png"),
    bundle_identifier="io.github.nnhr-nunu.StreamHeartbeat",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "StreamHeartbeat(ぬ)",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "マイクで拾った心音に合わせて心臓を動かすために使います。",
    },
)
