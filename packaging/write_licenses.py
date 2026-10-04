"""配布 zip に入れる利用規約とライセンスの文書を書き出す（GitHub Actions のビルドで使う）。

  python packaging/write_licenses.py <配布フォルダ>

<配布フォルダ> に 利用規約.txt と ライセンス フォルダを作る。ライセンス フォルダには、同梱している
ソフトの一覧（版とソースコードの入手先つき）・GPL/LGPL の全文・Python のライセンスを入れる。
版は、ビルドに使った Python と PySide6 から読む（zip の中身と食い違わないように）。
"""

from __future__ import annotations

import ctypes
import shutil
import sys
import sysconfig
from pathlib import Path

HERE = Path(__file__).resolve().parent
LICENSES = HERE / "licenses"
TEXTS = ("LGPL-3.0.txt", "GPL-3.0.txt", "LGPL-2.1.txt")

TERMS = """\
StreamHeartbeat(ぬ) 利用規約

1. 無料で使えます。個人・法人を問わず、収益化している配信や動画でも使えます。
2. クレジットの表記は任意です。ただ、配信や動画で使っていただいたときは、
   概要欄などに次の表記をしていただけるととても嬉しいです。

     StreamHeartbeat(ぬ)
     開発者：ぬぬはら - 催眠音声制作者
     YouTube：https://www.youtube.com/@nnhr_nunu
     X(Twitter)：https://x.com/nnhr_nunu
     使い方など：https://github.com/nnhr-nunu/StreamHeartbeat_Nu

3. 応援用の購入は任意です。購入しても機能は変わりません。
4. この zip と中のファイルを、ほかの場所で再配布・販売しないでください。
   紹介するときは配布ページへのリンクでお願いします。
5. 動作の保証はしていません。このアプリを使って起きた問題や損害について、作者は責任を負いません。
6. 同梱しているほかの人のソフト（Qt など）は、それぞれのライセンスに従います
   （ライセンス フォルダ）。それらのライセンスで認められていること
   （Qt を差し替える、そのために調べる など）は、この規約で禁止しません。
7. この規約は予告なく変えることがあります。

作者: Nunuhara
"""

NOTICES = """\
StreamHeartbeat(ぬ) が同梱しているソフトと素材

このアプリは次のソフトを同梱しています。どれもそれぞれのライセンスで配布されています。
アプリ本体の利用条件は 利用規約.txt を見てください。

■ Qt {qt} / Qt for Python（PySide6 {pyside}・Shiboken6）
  Copyright (C) The Qt Company Ltd. and other contributors.
  ライセンス: GNU Lesser General Public License v3（LGPL-3.0.txt）
    LGPL v3 は GPL v3 に許可を足したものなので、GPL-3.0.txt も同梱しています。
  ソースコード:
    Qt      https://download.qt.io/archive/qt/{qt_minor}/{qt}/single/
    PySide6 https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{pyside}-src/
  Qt は改変していません。Qt はアプリの中の PySide6 フォルダ（Windows は _internal\\PySide6）に
  共有ライブラリのまま入っているので、互換のある Qt に差し替えて動かせます。
  Qt が中で使っているソフトのライセンス: https://doc.qt.io/qt-6/licenses-used-in-qt.html

■ FFmpeg {ffmpeg}（Qt Multimedia が音のファイルを読むのに使います）
  Copyright (C) the FFmpeg developers.
  ライセンス: GNU Lesser General Public License v2.1 以降（LGPL-2.1.txt）
  ソースコード: {ffmpeg_src}

■ Python {python}
  Copyright (C) Python Software Foundation.
  ライセンス: Python Software Foundation License（Python.txt）
    Python に含まれる OpenSSL・libffi・bzip2・zlib などの表記も Python.txt にあります。
{mesa}
■ スタジオの映り込みの画像（Ferndale Studio 04）
  Dimitrios Savva, Jarod Guest / Poly Haven
  ライセンス: CC0  https://polyhaven.com/a/ferndale_studio_04
"""

MESA = """
■ Mesa（opengl32sw.dll。GPU で OpenGL を使えない PC で、代わりに描くのに使います）
  ライセンス: MIT ほか  https://docs.mesa3d.org/license.html
"""


def _ffmpeg_version(pyside_dir: Path) -> str | None:
    """PySide6 に同梱の FFmpeg の版（読めなければ None）。"""
    for lib in sorted(pyside_dir.rglob("*avutil*")):
        if lib.suffix not in (".dll", ".dylib", ".so"):
            continue
        try:
            avutil = ctypes.CDLL(str(lib))
            avutil.av_version_info.restype = ctypes.c_char_p
            return avutil.av_version_info().decode()
        except (OSError, AttributeError):
            continue
    return None


def _python_license() -> Path:
    """ビルドに使った Python の LICENSE.txt（Windows は直下、Mac は標準ライブラリの所）。"""
    base = Path(sys.base_prefix)
    stdlib = Path(sysconfig.get_paths()["stdlib"])
    for path in (base / "LICENSE.txt", stdlib / "LICENSE.txt"):
        if path.is_file():
            return path
    raise SystemExit(f"Python の LICENSE.txt が見つからない: {base}")


def write(dest: Path) -> None:
    import PySide6
    from PySide6.QtCore import qVersion

    qt = qVersion()
    ffmpeg = _ffmpeg_version(Path(PySide6.__file__).parent)
    out = dest / "ライセンス"
    out.mkdir(parents=True, exist_ok=True)
    for name in TEXTS:
        shutil.copyfile(LICENSES / name, out / name)
    shutil.copyfile(_python_license(), out / "Python.txt")
    notices = NOTICES.format(
        qt=qt,
        qt_minor=".".join(qt.split(".")[:2]),
        pyside=PySide6.__version__,
        ffmpeg=ffmpeg or "（Qt に同梱の版）",
        ffmpeg_src=(
            f"https://ffmpeg.org/releases/ffmpeg-{ffmpeg}.tar.xz"
            if ffmpeg
            else "https://ffmpeg.org/download.html"
        ),
        python=sys.version.split()[0],
        mesa=MESA if sys.platform == "win32" else "",
    )
    # メモ帳でも崩れないよう CRLF にする
    (out / "同梱しているソフト.txt").write_text(notices, encoding="utf-8", newline="\r\n")
    (dest / "利用規約.txt").write_text(TERMS, encoding="utf-8", newline="\r\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    write(Path(sys.argv[1]))
