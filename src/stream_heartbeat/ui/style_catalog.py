"""操作画面で選べるスタイルの一覧。(スタイル, 見た目, 表示名) の並び。

見た目はプロファイルの realistic_look に入る（リアルの 1〜3・レントゲンの女性の像・
かわいい2・心電図2 の縁取りなど）。見た目の無いスタイルは空。
"""

from __future__ import annotations

from stream_heartbeat.ui.heart_paint import CUTE_REIWA, ECG_OUTLINE

STYLES = [
    ("realistic", "surgical", "リアル1"),
    ("realistic", "vivid", "リアル2"),
    ("realistic", "anatomy", "リアル3"),
    ("echo", "", "心エコー"),
    ("mri", "", "MRI"),
    ("xray", "", "レントゲン1"),
    ("xray", "female", "レントゲン2"),
    ("xray_heart", "", "レントゲン3"),
    ("cute", "", "かわいい1"),
    ("cute", CUTE_REIWA, "かわいい2"),
    ("chic", "", "オシャレ1"),
    ("poly", "", "オシャレ2"),
    ("mech", "", "機械"),
    ("particles", "", "パーティクル"),
    ("ecg", "", "心電図1"),
    ("ecg", ECG_OUTLINE, "心電図2"),
]
