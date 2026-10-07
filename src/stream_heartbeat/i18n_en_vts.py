"""英訳の表（VTube Studio 連携の欄）。{日本語の原文: 英語}。

原文は vts_text.py の定数をそのままキーにする（日本語を直しても表が追いつくように）。
案内文は 1 行ずつ、並びの順に英語を当てる（行数が合わなければ import で気付く）。
"""

from __future__ import annotations

from stream_heartbeat import vts_text as t

_HOW_TO_EN = (
    "[Setup (first time only)]",
    "1. Start VTube Studio and show your model.",
    '2. Open the VTube Studio settings (gear icon) and turn on "{switch}" in the plugin '
    "section. Leave the port number at {port}.",
    "   If you cannot see the gear icon, double-click the VTube Studio window to make it appear.",
    '3. Tick "Connect to VTube Studio" in this section.',
    '4. VTube Studio asks whether this app (StreamHeartbeat) may connect; press "Allow". '
    'When this section says "Connected to VTube Studio", setup is done.',
    "[Attach the heart to your model]",
    '5. Press "{show}". The heart appears in the VTube Studio window '
    "(it can take a few seconds depending on the style).",
    '6. Press "{pin}". The heart moves to the left edge of the VTube Studio window '
    "so it does not block your click.",
    "7. Switch to the VTube Studio window and left-click the model's chest (where you want "
    "the heart). The heart moves there and follows the model from then on.",
    "   You can attach it anywhere on the model, such as a shoulder or the head. Clicking where "
    "there is no model, or right-clicking, does not set it. Press the button again to cancel.",
    '8. Adjust the heart\'s size with the "{size}" slider.',
    "[From next time]",
    "- The attachment point is remembered per model and the size is remembered globally. "
    'If you leave "Connect to VTube Studio" ticked, just starting this app and VTube Studio '
    "shows the heart in the same place. It also connects automatically if you start "
    "VTube Studio later.",
    "- You can also drag the heart to a new place in the VTube Studio window. It reappears there "
    "even after the heart is remade with a new look, but it is not attached to the body (this app "
    'cannot read where VTube Studio attached it). To attach it, use "{pin}".',
    '- Change the size with "{size}". A size changed with the mouse wheel in the VTube Studio '
    'window goes back to the "{size}" size when the heart is remade.',
    "- If you change the style, the heart's angle or the effect, the heart in VTube Studio "
    "automatically follows after a short wait.",
    "- The Heart grab, Stethoscope and Popping hearts effects also appear on the VTube Studio "
    "heart. With Heart grab, clicking the heart in the VTube Studio window makes the hand "
    "squeeze it. The stethoscope following the mouse only works in the output window; in "
    "VTube Studio the stethoscope stays where you left it in the output window.",
    '- If you tick "{words}", the beat text (such as ❤ or "ba-dump") also appears in the same '
    "place as in the output window (always in the same spot, without the per-beat wobble).",
    '- If you tick "{bpm_check}", the heart rate number also appears in VTube Studio. Its color, '
    'outline and size follow the "④ Heart rate" settings. Drag it in the VTube Studio window to '
    "place it (the place is remembered for next time. If you put it on the model it moves with "
    'the body, but it comes off when it is remade after you change the "④" settings).',
    '- To remove the heart, press "{hide}". It will not appear the next time you start the app '
    '(press "{show}" to show it again).',
    "- Styles available in VTube Studio: {names}",
    "[Parameters (advanced)]",
    'If you tick "{params}", these two are sent:',
    "- {beat}: 1 at the moment of a beat, close to 0 between beats",
    "- {bpm}: heart rate",
    "In the VTube Studio model settings, choose these as parameter inputs to move the model's "
    "body or expression in time with each beat.",
)

_TROUBLE_EN = (
    '- "Cannot connect to VTube Studio" is shown',
    '   -> Check that VTube Studio is running, that "{switch}" is on, and that the port number '
    "is still {port}.",
    '- Stuck on "A confirmation is showing"',
    "   -> Bring the VTube Studio window to the front; the confirmation is there. "
    'Press "Allow".',
    '- "VTube Studio did not allow the connection" is shown',
    '   -> Tick the checkbox again and press "Allow" in the confirmation shown by VTube Studio.',
    "- The heart does not appear",
    '   -> Check that "Export folder" below is the VTube Studio Items folder. If you installed '
    'it outside Steam, choose it again with "Choose folder".',
    "- The heart in VTube Studio looks different from the output window",
    '   -> Press "{remake}".',
    "- I removed the heart on the VTube Studio side",
    '   -> Press "{show}" again.',
    "- After changing the look, the heart in VTube Studio came off the body or got bigger",
    "   -> A place or size changed by dragging or with the mouse wheel in the VTube Studio window "
    'goes back when the heart is remade. Attach it with "{pin}" and set the size with "{size}".',
    "- The heart is out of place, or I want to attach it somewhere else",
    '   -> Press "{pin}" and click the model again in the VTube Studio window.',
)


def _by_line(source: tuple[str, ...], english: tuple[str, ...]) -> dict[str, str]:
    lines = [line for line in source if line]
    if len(lines) != len(english):
        raise ValueError(f"案内文の行数が合いません: 原文 {len(lines)} 行 / 英語 {len(english)} 行")
    return dict(zip(lines, english, strict=True))


EN_VTS: dict[str, str] = {
    # ---- つながりの状態 ------------------------------------------------------------
    t.API_SWITCH: "Start API (allow plugins)",
    t.LABEL_OFF: "Not connected",
    t.LABEL_CONNECTING: "Connecting to VTube Studio…",
    t.LABEL_WAITING_USER: (
        'A confirmation is showing in the VTube Studio window. Press "Allow".'
    ),
    t.LABEL_READY: "Connected to VTube Studio",
    t.LABEL_NO_VTS: (
        'Cannot connect to VTube Studio. Start VTube Studio and turn on "{switch}" in its '
        "settings (retrying every 5 seconds until connected)."
    ),
    t.LABEL_DENIED: (
        "VTube Studio did not allow the connection, so connecting was stopped. "
        "To connect, tick the checkbox again."
    ),
    # ---- 欄の文字 -------------------------------------------------------------------
    t.INTRO: (
        "Attach the heart to your VTube Studio model's chest and make it beat in time "
        "with your heartbeat."
    ),
    "VTube Studio とつなぐ": "Connect to VTube Studio",
    t.SHOW_BUTTON: "Show heart",
    t.REMAKE_BUTTON: "Remake (with the current look)",
    t.HIDE_BUTTON: "Put away",
    t.PIN_BUTTON: "Choose where to attach the heart",
    t.PICKING_BUTTON: "Waiting for a click… (press again to cancel)",
    t.SIZE_LABEL: "Size",
    "小さく": "Smaller",
    "大きく": "Larger",
    t.PARAMS_CHECK: "Also send the heartbeat as parameters (advanced)",
    t.TEXT_CHECK: "Also show the beat text with the heart in VTube Studio",
    t.BPM_CHECK: "Also show the heart rate number in VTube Studio",
    t.BPM_SHOWN_NOTE: (
        "The heart rate number is shown. Drag it in the VTube Studio window to place it."
    ),
    t.T_BPM_FAILED: "Could not show the heart rate number ({error})",
    "数字の色・縁取り・文字の大きさは「④ 心拍数」の設定のとおりです。"
    "VTube Studio での大きさは、この欄の「大きさ」で心臓と一緒に変わります。"
    "置き場所は VTube Studio の画面でドラッグして決めます": (
        'The number\'s color, outline and text size follow the "④ Heart rate" settings. Its size '
        'in VTube Studio changes together with the heart via "Size" in this section. Drag it in '
        "the VTube Studio window to place it."
    ),
    "配信用の窓の拍の文字（❤ やドクンなど）を、VTube Studio の心臓にも同じ所に出します。"
    "文字・大きさ・色は「③ 同期文字」の設定のとおりです": (
        "Shows the output window's beat text (such as ❤) on the VTube Studio heart too, "
        "in the same place. The text, size and color follow the beat text settings."
    ),
    "押したあと、VTube Studio の画面でモデルの心臓を付けたい所を左クリックします": (
        "After pressing this, left-click the spot on the model in the VTube Studio window "
        "where you want the heart."
    ),
    "フォルダを選ぶ": "Choose folder",
    "使い方": "How to use",
    "上手くいかない時": "Troubleshooting",
    "書き出し先: VTube Studio の Items フォルダが見つかりません": (
        "Export folder: the VTube Studio Items folder was not found"
    ),
    "書き出し先: {folder}": "Export folder: {folder}",
    "VTube Studio の Items フォルダ（StreamingAssets の中）": (
        "VTube Studio Items folder (inside StreamingAssets)"
    ),
    # ---- 心臓の様子の一文 ------------------------------------------------------------
    t.T_BAD_STYLE: "This style cannot be shown in VTube Studio. Available styles: {names}",
    t.T_NOT_SHOWN: 'Next, press "{show}"',
    t.NOTE_STALE: "The look has changed. After a short wait, the heart in VTube Studio will match.",
    t.T_STALE_FAILED: (
        'Could not update the heart in VTube Studio to the current look. Press "{remake}".'
    ),
    t.T_UNPINNED: (
        'The heart is shown. Next, press "{pin}" and decide where on the model to attach it.'
    ),
    t.T_PINNED: 'The heart is attached to the model. You can change its size with "{size}".',
    t.T_HAND_PLACED: (
        "Placed on the body in the VTube Studio window. Remaking it with a new look takes it off "
        'the body, so to keep it attached, attach it with "{pin}".'
    ),
    t.PICK_NOTICE: (
        "Switch to the VTube Studio window and left-click the model's chest "
        "(where you want the heart) with the mouse"
    ),
    t.T_PICKING: (
        "{pick}. The heart has been moved to the left edge of the screen for now so it does "
        "not block your click. Clicking where there is no model, or right-clicking, will "
        "not set it."
    ),
    # ---- 知らせ ---------------------------------------------------------------------
    t.REMADE_NOTICE: "The heart in VTube Studio now matches the current look",
    t.T_HAND_PLACED_NOTICE: (
        'To keep it attached to the body after changing the look, attach it with "{pin}"'
    ),
    t.T_HAND_REMADE_NOTICE: (
        "Updated the heart in VTube Studio to the current look and showed it where it was. "
        'To attach it to the body, press "{pin}".'
    ),
    t.BPM_SHOWN_NOTICE: (
        "Showed the heart rate in VTube Studio. Drag it in the VTube Studio window to where you "
        "want it."
    ),
    "心拍数の画像を書き出せませんでした（書き出し先のフォルダを確かめてください）": (
        "Could not export the heart rate images (check the export folder)"
    ),
    "VTube Studio に心拍数を出せませんでした（{error}）": (
        "Could not show the heart rate in VTube Studio ({error})"
    ),
    t.PINNED_NOTICE: (
        "Attached to the model. From now on the heart will be attached here automatically "
        "whenever you show it."
    ),
    t.NOT_ITEMS_NOTICE: (
        "Please choose the Items folder "
        "(VTube Studio folder → VTube Studio_Data → StreamingAssets → Items)"
    ),
    "VTube Studio につながってから押してください": "Press this after connecting to VTube Studio",
    "アイテムの画像を書き出せませんでした（書き出し先のフォルダを確かめてください）": (
        "Could not export the item images (check the export folder)"
    ),
    "VTube Studio に心臓を出し、覚えている場所に付けました": (
        "Showed the heart in VTube Studio and attached it to the remembered spot"
    ),
    "VTube Studio に心臓を出しました。次は「{pin}」を押してください": (
        'Showed the heart in VTube Studio. Next, press "{pin}".'
    ),
    "VTube Studio に出せませんでした（{error}）": "Could not show it in VTube Studio ({error})",
    "先に「{show}」で VTube Studio に心臓を出してください": (
        'First show the heart in VTube Studio with "{show}"'
    ),
    "モデルに付けられませんでした（{error}）": "Could not attach it to the model ({error})",
    # vts.py が返す失敗の理由
    "アイテムを出せませんでした": "Could not show the item",
    "留められませんでした": "Could not pin it",
    # ---- スタイル名のまとめ方（style_names） ------------------------------------------
    "{name}{a}": "{name} {a}",
    "{name}{a}・{b}": "{name} {a} & {b}",
    "{name}{a}〜{b}": "{name} {a}–{b}",
    "、": ", ",
    # ---- 案内文（1 行ずつ） ------------------------------------------------------------
    **_by_line(t.HOW_TO_LINES, _HOW_TO_EN),
    **_by_line(t.TROUBLE_LINES, _TROUBLE_EN),
}
