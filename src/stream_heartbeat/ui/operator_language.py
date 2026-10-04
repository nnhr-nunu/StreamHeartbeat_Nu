"""操作画面の表示言語の切り替えと、言語で変わる OBS の案内文。"""

from __future__ import annotations

import sys

from stream_heartbeat import OUTPUT_WINDOW_TITLE
from stream_heartbeat.i18n import (
    LANG_EN,
    LANG_JA,
    language,
    other_language_label,
    set_language,
    tr,
    translate_tree,
)
from stream_heartbeat.profile import save_app_state

# OBS で背景を抜く方法（背景の色ごと）
OBS_KEYS = {"green": "クロマキーで緑", "white": "カラーキーで白", "black": "カラーキーで黒"}


def obs_hint(backdrop: str, windows: bool = sys.platform == "win32") -> str:
    """OBS への取り込み方。背景の色で抜き方が変わる。

    透明は Windows ではキャプチャ方法を「Windows 10（1903以降）」にしないと透けない。
    それでも透けないときの逃げ道も書く。
    """
    key = OBS_KEYS.get(backdrop)
    if key:
        return tr(
            "OBS では「ウィンドウキャプチャ」で「{title}」を選び、{key}を抜きます。",
            title=OUTPUT_WINDOW_TITLE,
            key=tr(key),
        )
    if windows:
        return tr(
            "OBS では「ウィンドウキャプチャ」で「{title}」を選び、"
            "プロパティの「キャプチャ方法」を「Windows 10（1903以降）」にします"
            "（透けないときは背景を緑にして、クロマキーで抜きます）。",
            title=OUTPUT_WINDOW_TITLE,
        )
    return tr(
        "OBS では「ウィンドウキャプチャ」で「{title}」を選びます"
        "（透けないときは背景を緑にして、クロマキーで抜きます）。",
        title=OUTPUT_WINDOW_TITLE,
    )


class LanguageMixin:
    """OperatorWindow が持つ部品（self._lang_btn など）を前提にする。"""

    def _toggle_language(self) -> None:
        self._set_language(LANG_EN if language() == LANG_JA else LANG_JA)

    def _set_language(self, lang: str) -> None:
        """表示言語を切り替えて保存する。窓は作り直さず、文字だけを入れ替える。"""
        set_language(lang)
        try:
            save_app_state(self._data_dir, language=language())
        except OSError:
            pass
        self._retranslate()

    def _retranslate(self) -> None:
        translate_tree(self)
        self._lang_btn.setText(other_language_label())
        self._cal_hint.setText(self._cal_hint_text())
        self._refresh_cal_texts()
        self._refresh_style_controls()
        self._refresh_status()
        self._vts.retranslate()
        self._show_aux(self._session.clock.oshilog_bpm)
