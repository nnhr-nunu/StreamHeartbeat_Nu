"""英訳の表（操作画面・スタイル・演出・状態・ダイアログ）。{日本語の原文: 英語}。

`{名前}` つきの文は、日本語と英語で同じ名前を使う（tests/test_i18n.py が確かめる）。
用語: 心拍の補正 = Heartbeat calibration、スタイル = Style、演出 = Effect、
プロファイル = Profile、同期文字 = Beat text、配信用の窓 = output window、操作用 = control window。
"""

from __future__ import annotations

EN_GENERAL: dict[str, str] = {}
