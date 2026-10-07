# Windows 用の StreamHeartbeat フォルダ（exe と _internal）を作る（GitHub Actions の Windows で使う）。
#   pyinstaller --noconfirm --clean packaging/StreamHeartbeat-windows.spec
# Qt は import している部品だけを PyInstaller のフックで集める（--collect-all PySide6 だと
# 使わない Qt まで全部入り、GPL だけで配る部品や WebEngine まで同梱してしまう）。
# 一つの exe（onefile）にはしない。Qt の DLL が見える形にして、LGPL のとおり利用者が差し替えられるようにする。

import re
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821  SPECPATH は PyInstaller が渡す
SRC = ROOT / "src" / "stream_heartbeat"
INIT = (SRC / "__init__.py").read_text(encoding="utf-8")
VERSION = re.search(r'^__version__ = "([^"]+)"', INIT, re.M).group(1)
# exe の「詳細」に出る版。ひな形に __init__.py の版を埋めて、作業用のフォルダに書く
VERSION_FILE = Path(workpath) / "windows_version.txt"  # noqa: F821  workpath は PyInstaller が渡す
VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
VERSION_FILE.write_text(
    (ROOT / "packaging" / "windows_version.txt")
    .read_text(encoding="utf-8")
    .replace("@VERSION_TUPLE@", ", ".join([*VERSION.split("."), "0", "0", "0"][:4]))
    .replace("@VERSION@", VERSION),
    encoding="utf-8",
)

a = Analysis(  # noqa: F821
    [str(SRC / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(SRC / "assets"), "stream_heartbeat/assets")],
    hiddenimports=["PySide6.QtMultimedia"],
    # 使わない大きな Qt を入れない（Mac の spec と同じ）
    excludes=[
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQml",
        "PySide6.QtGraphs",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "tkinter",
    ],
)
# フックが集めるプラグインのうち、使わないのに大きな Qt を連れてくるものを外す
#   仮想キーボード（Qt Virtual Keyboard は GPL だけで配る部品。Quick と Qml も連れてくる）
#   PDF を画像として読むプラグイン（Qt Pdf）
#   Qt の OpenSSL 版の通信（使わない。PATH にある別ソフトの OpenSSL 3 を拾ってくる。
#   Python の https は Python 同梱の OpenSSL を使い、Qt の通信は Windows 標準の Schannel が残る）
DROP = {
    "qopensslbackend.dll",
    "libssl-3-x64.dll",
    "libcrypto-3-x64.dll",
    "qtvirtualkeyboardplugin.dll",
    "qt6virtualkeyboard.dll",
    "qt6quick.dll",
    "qt6qml.dll",
    "qt6qmlmeta.dll",
    "qt6qmlmodels.dll",
    "qt6qmlworkerscript.dll",
    "qpdf.dll",
    "qt6pdf.dll",
}
a.binaries = [b for b in a.binaries if Path(b[0]).name.lower() not in DROP]
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StreamHeartbeat",
    console=False,
    upx=False,
    icon=str(SRC / "assets" / "app_icon.ico"),
    version=str(VERSION_FILE),
)
coll = COLLECT(exe, a.binaries, a.datas, name="StreamHeartbeat", upx=False)  # noqa: F821
