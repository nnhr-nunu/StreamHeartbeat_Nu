"""英訳の表（操作画面・スタイル・演出・状態・ダイアログ）。{日本語の原文: 英語}。

`{名前}` つきの文は、日本語と英語で同じ名前を使う（tests/test_i18n.py が確かめる）。
用語: 心拍の補正 = Heartbeat calibration、スタイル = Style、演出 = Effect、
プロファイル = Profile、同期文字 = Beat text、配信用の窓 = output window、操作用 = control window。
"""

from __future__ import annotations

EN_GENERAL: dict[str, str] = {
    # ---- 操作画面: 見出し・欄 --------------------------------------------------
    "プロファイル": "Profile",
    "① マイク": "① Microphone",
    "マイク": "Microphone",
    "音の大きさ": "Sound level",
    "② スタイル": "② Style",
    "スタイル": "Style",
    "演出": "Effect",
    "大きさ": "Size",
    "透明度": "Opacity",
    "背景": "Background",
    "③ 同期文字": "③ Beat text",
    "文言": "Text",
    "左右": "Horizontal",
    "上下": "Vertical",
    "ゆらぎ": "Jitter",
    "傾き": "Tilt",
    "文字色": "Text color",
    "縁取り": "Outline",
    "④ 心拍数": "④ Heart rate",
    "⑤ VTube Studio 連携": "⑤ VTube Studio link",
    "心拍の補正（数字が合わないときだけ）": "Heartbeat calibration (only if the numbers are wrong)",
    "推しログ(ぬ)連携（未実装）": "OshiLog(Nu) link (not implemented)",
    "心拍ID": "Heartbeat ID",
    "補助 BPM URL": "Auxiliary BPM URL",
    # ---- 操作画面: ボタン・チェック・スライダーの端 ------------------------------
    "名前を付けて保存": "Save as…",
    "設定をリセット": "Reset settings",
    "角度を固定": "Lock angle",
    "角度をリセット": "Reset angle",
    "鼓動に合わせて文字を出す": "Show text on each beat",
    "心拍数（BPM）を出す": "Show heart rate (BPM)",
    "補正開始": "Start calibration",
    "補正を保存": "Save calibration",
    "中止": "Cancel",
    "保存した補正を消す": "Delete saved calibration",
    "拍": "Beat",
    "大": "Large",
    "小": "Small",
    "透明": "Transparent",
    "不透明": "Opaque",
    "右": "Right",
    "左": "Left",
    "上": "Top",
    "下": "Bottom",
    "なし": "None",
    "強": "Strong",
    # ---- 操作画面: ツールチップ・説明 -------------------------------------------
    "配信用の窓をドラッグしても回さない": "Don't rotate even if the output window is dragged",
    "配信用の窓を左ドラッグで回転、ダブルクリックで元の向き。": (
        "Left-drag the output window to rotate it; double-click to restore the original angle."
    ),
    "心音を拾うと動きます。まったく動かないときはマイクを確かめてください": (
        "Moves when a heart sound is picked up. If it never moves, check your microphone."
    ),
    "設定は変えるたびに自動で保存されます": (
        "Settings are saved automatically whenever you change them"
    ),
    "今の設定を別の名前で残します（配信ごとに見た目を切り替えたいとき）": (
        "Save the current settings under another name (handy for switching looks per stream)"
    ),
    "心拍数が半分や倍に出るときだけ使います。"
    "「{start}」を押すと自分の心音が聞こえるので（ヘッドホン推奨）、"
    "鼓動に合わせて「拍」かスペースキーを10回ほど押し、"
    "「{save}」を押します。": (
        'Use this only when the heart rate shows half or double the real value. Press "{start}" '
        "to hear your own heart sound (headphones recommended), tap the \"Beat\" button or the "
        'space bar about 10 times in time with your heartbeat, then press "{save}".'
    ),
    # ---- OBS の案内 --------------------------------------------------------------
    "クロマキーで緑": "a Chroma Key filter (green)",
    "カラーキーで白": "a Color Key filter (white)",
    "カラーキーで黒": "a Color Key filter (black)",
    "OBS では「ウィンドウキャプチャ」で「{title}」を選び、{key}を抜きます。": (
        'In OBS, add a Window Capture, select "{title}", and remove the background with {key}.'
    ),
    "OBS では「ウィンドウキャプチャ」で「{title}」を選び、"
    "プロパティの「キャプチャ方法」を「Windows 10（1903以降）」にします"
    "（透けないときは背景を緑にして、クロマキーで抜きます）。": (
        'In OBS, add a Window Capture, select "{title}", and set "Capture Method" in its '
        'properties to "Windows 10 (1903 and later)" (if it does not become transparent, '
        "set the background to green and remove it with a Chroma Key filter)."
    ),
    "OBS では「ウィンドウキャプチャ」で「{title}」を選びます"
    "（透けないときは背景を緑にして、クロマキーで抜きます）。": (
        'In OBS, add a Window Capture and select "{title}" (if it does not become '
        "transparent, set the background to green and remove it with a Chroma Key filter)."
    ),
    # ---- 状態の帯・警告 ----------------------------------------------------------
    "心拍同期表示中": "Synced to your heartbeat",
    "プレビュー中（心音未認識）": "Preview (no heart sound detected)",
    "検出できていません": "Not detected",
    "{status}  最後 {bpm} BPM": "{status}  Last {bpm} BPM",
    "補正中  {label}": "Calibrating  {label}",
    "これは医療機器ではありません。診断・治療には使えません。": (
        "This is not a medical device. It cannot be used for diagnosis or treatment."
    ),
    "立体表示を使えないため 2D で描いています": (
        "3D display is unavailable, so the heart is drawn in 2D"
    ),
    "マイクから音が届いていません。つながりと、選んだマイクを確かめてください": (
        "No sound is reaching the microphone. Check the connection and the selected microphone."
    ),
    "マイクを開けません。OBS と同時に使うときは、独占モードをオフにしてください": (
        "Cannot open the microphone. If you also use it in OBS, turn off exclusive mode."
    ),
    "時計と数字がズレています（推しログは遅延します）": (
        "The clock and the number are out of sync (OshiLog is delayed)"
    ),
    "推しログ(ぬ) 補助: {bpm}（遅延のことがあります）": "OshiLog(Nu) aux: {bpm} (may be delayed)",
    # ---- 知らせ・ダイアログ ------------------------------------------------------
    "保存できませんでした（ファイルが使用中か、空き容量が足りません）": (
        "Could not save (the file is in use, or the disk is full)"
    ),
    "プロファイルを保存しました": "Profile saved",
    "「{name}」として保存しました": 'Saved as "{name}"',
    "プロファイル名": "Profile name",
    "「{name}」はもうあります。今の設定で置き換えますか？": (
        '"{name}" already exists. Replace it with the current settings?'
    ),
    "補正を中止しました": "Calibration cancelled",
    "補正を保存しました": "Calibration saved",
    "音が録れていなかったので保存しませんでした。マイクを確かめてください": (
        "Nothing was recorded, so it was not saved. Check your microphone."
    ),
    "保存した心拍の補正を全部消して、最初からやり直しますか？": (
        "Delete all saved heartbeat calibration and start over?"
    ),
    "保存した補正を消しました": "Saved calibration deleted",
    "透明にするため配信用の窓を開き直しました。OBS の取り込みが外れたら選び直してください": (
        "The output window was reopened to make it transparent. "
        "If OBS loses it, select the window again."
    ),
    "心音ファイルを追加": "Add heart sound file",
    "音声・動画 (*.wav *.mp3 *.m4a *.mp4 *.mov);;すべて (*.*)": (
        "Audio / video (*.wav *.mp3 *.m4a *.mp4 *.mov);;All files (*.*)"
    ),
    "この音声ファイルは読めませんでした": "This audio file could not be read",
    "音声ファイルが空でした": "The audio file was empty",
    "心音サンプルを追加しました": "Heart sound sample added",
    "保存値 {value}": "Saved value {value}",
    # ---- 補正の拍の数（session.tap_label） ----------------------------------------
    "拍はまだ（{goal}回以上が目安）": "No beats yet (aim for {goal} or more)",
    "拍 {count} / {goal} 回": "Beats {count} / {goal}",
    "拍 {count} 回  約 {bpm} BPM（保存してOK）": "{count} beats  about {bpm} BPM (OK to save)",
    # ---- 色・縁・背景 -------------------------------------------------------------
    "白": "White",
    "黄": "Yellow",
    "黒": "Black",
    "赤": "Red",
    "黒縁": "Black outline",
    "白縁": "White outline",
    "緑（クロマキー）": "Green (chroma key)",
    # ---- スタイル名 ---------------------------------------------------------------
    "リアル1": "Realistic 1",
    "リアル2": "Realistic 2",
    "リアル3": "Realistic 3",
    "心エコー": "Echo",
    "レントゲン1": "X-ray 1",
    "レントゲン2": "X-ray 2",
    "レントゲン3": "X-ray 3",
    "かわいい1": "Cute 1",
    "かわいい2": "Cute 2",
    "オシャレ1": "Chic 1",
    "オシャレ2": "Chic 2",
    "機械": "Mechanical",
    "パーティクル": "Particles",
    "心電図1": "ECG 1",
    "心電図2": "ECG 2",
    # ---- 演出 ---------------------------------------------------------------------
    "心臓わしづかみ": "Heart grab",
    "聴診器1": "Stethoscope 1",
    "聴診器2": "Stethoscope 2",
    "カラードプラ": "Color Doppler",
    "タギング": "Tagging",
    "モニター画面": "Monitor screen",
    "はじけるハート": "Popping hearts",
    "配信用の窓をクリックすると、ぎゅっと強く握ります（押している間は握ったまま）。": (
        "Click the output window to squeeze hard (it stays squeezed while you hold the button)."
    ),
    "配信用の窓の上でマウスを動かすと聴診器がついてきます。"
    "クリックした所に置いておけます（マウスが窓の外へ出るとそこへ戻ります）。": (
        "Move the mouse over the output window and the stethoscope follows it. Click to leave it "
        "where you clicked (it returns there when the mouse leaves the window)."
    ),
    "血の流れを色で重ねます（赤: 探触子へ向かう流れ / 青: 遠ざかる流れ）。": (
        "Overlays blood flow in color (red: flow toward the probe / blue: flow away from it)."
    ),
    "拍のたびに格子の縞を焼き付けます。縞は心筋と一緒に曲がりながら薄れます。": (
        "Burns a grid of stripes in on every beat. The stripes bend with the heart muscle "
        "as they fade."
    ),
    "心電図をベッドサイドのモニターの画面に映します。拍で右上のハートが光ります。": (
        "Shows the ECG on a bedside monitor screen. The heart in the top right flashes "
        "on each beat."
    ),
    "鼓動のたびに心臓からハートがはじけます。"
    "配信用の窓をクリックすると、その場所からも大きくはじけます。": (
        "Hearts pop out of the heart on every beat. Click the output window to make big ones "
        "pop from that spot too."
    ),
    # ---- 起動中の小窓 ---------------------------------------------------------------
    "起動しています。お待ちください…": "Starting up. Please wait…",
    "設定を読み込んでいます": "Loading settings",
    "心臓を用意しています": "Preparing the heart",
    "心臓の形を作っています（初回だけ少しかかります）": (
        "Building the heart shape (first launch only; takes a moment)"
    ),
    "画面を組み立てています": "Building the windows",
}
