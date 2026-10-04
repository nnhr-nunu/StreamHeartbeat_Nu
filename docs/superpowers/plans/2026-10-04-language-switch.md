# 日本語 / English 切り替え Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 操作用ウィンドウの表示を、ボタン 1 つで日本語と英語に切り替えられるようにする（再起動なし、言語は保存）。

**Architecture:** 日本語の原文をキーにした英訳の表（`i18n_en*.py`）と、`tr()` / `translate_tree()`（`i18n.py`）。静的な文字（ラベル・ボタン・枠・ツールチップ・コンボ項目）は作ったあとに画面の部品を走査して付け替え、実行中に作る文字は `tr()` を通す。ウィンドウは作り直さない。

**Tech Stack:** Python 3.10、PySide6、pytest（`QT_QPA_PLATFORM=offscreen`）。

**Spec:** [2026-10-04-language-switch-design.md](../specs/2026-10-04-language-switch-design.md)

## Global Constraints

- 日本語の表示・保存データ・既存テストの結果は変えない。テストの間は言語を `ja` に固定する。
- ウィンドウの題名 `StreamHeartbeat(ぬ) - 配信出力` / `StreamHeartbeat(ぬ)` は言語で変えない（OBS が題名で探す）。
- 言語ボタンの文字は `English`（日本語表示のとき）/ `日本語`（英語表示のとき）。翻訳しない。
- 言語の保存先は `app_state`（`save_app_state(language=...)`）。ボタンを押したときだけ保存し、保存が無いときは OS の言語（日本語なら `ja`、それ以外は `en`）。
- 英訳が無い文字は日本語のまま出す（落ちない）。
- 800 行を超えるファイルは作らない（表は `i18n_en.py` と `i18n_en_vts.py` に分ける）。
- `.py` を変えたら `pytest` と `ruff check src tests`。commit は日本語、PowerShell から、`git push origin main`。
- 利用者が入れた文字（プロファイル名、同期文字の文言）は翻訳しない。`tr(template, **fmt)` は **テンプレートだけ** を `format` し、引数の中身の `{}` は触らない。

## Review Focus

- 補正の録音中（「拍  3」「補正中 …」）に言語を切り替えても、拍の数が消えず、落ちない。
- プロファイル名に `{0}` や `}` を含めても、保存の知らせ・確認ダイアログが壊れない。
- `app_state` の `language` が `"fr"`・数・空などの壊れた値でも、OS の言語で決まる。
- 英語表示でも、配信用ウィンドウの題名は日本語のまま（OBS の取り込みが外れない）。
- ja → en → ja の往復で、プロファイルの値（スタイル・色・背景・「保存値 …」の項目）が変わらない。

---

## File Structure

| ファイル | 役目 |
| -------- | ---- |
| `src/stream_heartbeat/i18n.py`（新規） | 言語の状態、`tr`、`translate_tree`、初回の言語の決め方 |
| `src/stream_heartbeat/i18n_en.py`（新規） | 操作画面・スタイル・演出・状態・ダイアログの英訳 |
| `src/stream_heartbeat/i18n_en_vts.py`（新規） | VTube Studio 連携の英訳 |
| `ui/fold.py` | 見出しの題名を覚え、`tr` で組み立てる |
| `ui/operator_window.py` / `operator_controls.py` | 言語ボタン、`_set_language`、文字の `tr` 化 |
| `ui/style_catalog.py` / `ui/effects.py` / `ui/heart_paint.py` | 表示名は日本語のまま。使う側で `tr` |
| `ui/vts_panel.py` / `vts.py` | 長い案内文を関数にして `tr` で組む |
| `session.py` / `config.py` / `ui/splash.py` / `app.py` | 状態・起動中の文言 |
| `tests/conftest.py` / `tests/test_i18n.py`（新規） | 言語固定、核のテスト、漏れ検査 |

---

### Task 1: `i18n` の核

**Files:**
- Create: `src/stream_heartbeat/i18n.py`, `src/stream_heartbeat/i18n_en.py`, `src/stream_heartbeat/i18n_en_vts.py`（どちらも辞書 `EN` / `EN_VTS` だけ。最初は数件）, `tests/test_i18n.py`
- Modify: `tests/conftest.py`（autouse で `set_language("ja")`、終了後も `ja` に戻す）, `ui/fold.py`

**Interfaces:**
- Produces（以降の全タスクが使う）:
  - `LANG_JA = "ja"`, `LANG_EN = "en"`
  - `language() -> str` / `set_language(lang: str) -> None`（不明な値は `ja`）
  - `detect_language(saved: object, locale_name: str) -> str`: `saved` が `"ja"`/`"en"` ならそれ、そうでなければ `locale_name` が `ja` で始まれば `ja`、それ以外は `en`
  - `init_language(data_dir: Path | None = None) -> str`: `app_state` と `QLocale.system().name()` から決めて `set_language` する
  - `tr(text: str, **fmt: object) -> str`
  - `translate_tree(root: QWidget) -> None`
  - `other_language_label() -> str`（`ja` 表示なら `"English"`、`en` 表示なら `"日本語"`）
  - `EN: dict[str, str]`（`i18n_en.EN` と `i18n_en_vts.EN_VTS` を合わせたもの）と、英訳から日本語への逆引き
- `fold_toggle(title, inner, *, expanded)` は題名の日本語をプロパティ `fold_title` に覚え、`▶/▼ + tr(title)` で組み立てる。

- [ ] **Step 1: 失敗するテストを書く（`tests/test_i18n.py`）**
  - `test_tr_returns_japanese_by_default` / `test_tr_translates_in_english`（`EN` に 1 件足して確かめる）/ `test_tr_falls_back_to_japanese_when_missing`
  - `test_tr_formats_only_the_template`: `tr("{n} 件", n="{0}")` が英語表示で `"{0} items"` 相当（引数の `{0}` はそのまま）
  - `test_detect_language`: `("en","ja_JP")→"en"`、`("ja","en_US")→"ja"`、`(None,"ja_JP")→"ja"`、`(None,"en_US")→"en"`、`("fr","ja_JP")→"ja"`、`(123,"en_US")→"en"`、`("", "de_DE")→"en"`
  - `test_init_language_reads_saved_state`: `tmp_path` に `app_state.json`（ファイル名は `profile.STATE_FILENAME`）で `{"language":"en"}` を書き、`init_language(tmp_path)` が `"en"`
  - `test_translate_tree_round_trip`: `QLabel`・`QPushButton`・`QCheckBox`・`QGroupBox`・ツールチップ・`QLineEdit` の placeholder・`QComboBox`（項目 2 つ、`itemData` つき）・`fold_toggle` の `QToolButton` を並べた `QWidget` を `ja` で作り、`en` に切り替えて `translate_tree` → 英語、`ja` に戻して `translate_tree` → 元の文字。`itemData` は変わらない
  - `test_translate_tree_skips_unknown_text`: 表に無い文字（動的な文）と、数字だけの `QLabel` は触らない
  - `test_translate_tree_follows_text_changed_after_first_walk`: 一度走査したボタンに別の既知の日本語を `setText` してから `translate_tree` → 英語になる（逆引きで追う）
  - `test_other_language_label`
- [ ] **Step 2: 実行して失敗を確かめる** — `.\.venv\Scripts\python.exe -m pytest tests/test_i18n.py -q` → import エラーで FAIL
- [ ] **Step 3: `i18n.py` を実装する**
  - `tr`: `en` かつ `text in EN` なら `EN[text]`、無ければ `text`。`fmt` があれば `text.format(**fmt)`（`fmt` が空のときは `format` しない）。
  - `translate_tree`: `root.findChildren(QWidget)` に `root` 自身も足して走査。`QLabel`・`QAbstractButton` は `text()`、`QGroupBox` は `title()`、`QLineEdit` は `placeholderText()`、`QComboBox` は各項目の `itemText`、すべての部品の `toolTip()`。`fold_title` を持つ `QToolButton` は `▶/▼ + tr(題名)` で組み直す。
  - 日本語の元の文字を解決する関数 `_source_of(current, stored)`: `stored` があり `current` が `stored` か `tr(stored)` に一致すればそれ、`current` が `EN` のキーならそれ、`current` が英訳の逆引きにあれば元の日本語、どれでもなければ `None`（触らない）。解決できた元の文字は動的プロパティ `i18n_text`（コンボの項目は `Qt.UserRole + 100` のデータ）に覚える。
  - 英訳が重複する日本語（例 `小` と `小さく`）は、覚えたプロパティで見分ける。
  - `init_language`: JSON を直接読む（`profile` を import しない。`paths.resolve_data_dir()` と `STATE_FILENAME` の値を使う。`STATE_FILENAME` を `profile` から import すると重ければ `paths` に移さず、同じ文字を定数で持つ）。
- [ ] **Step 4: `conftest.py` と `fold.py` を直し、テストが通ることを確かめる** — 同じコマンドで PASS。続けて `pytest -q` 全体が PASS（既存テストが `ja` のまま通る）。
- [ ] **Step 5: Commit** — `i18n: 言語の状態・tr・画面の付け替えの核を追加`

---

### Task 2: 操作用ウィンドウと言語ボタン

**Files:**
- Modify: `ui/operator_window.py`, `ui/operator_controls.py`, `ui/fold.py`（行の右に置く部品を渡せるようにする）, `app.py`（`init_language` を splash の前に呼ぶ）, `i18n_en.py`
- Test: `tests/test_i18n.py`（窓のテストを足す。既存の窓のテストの作り方は `tests/test_windows.py` に合わせる）

**Interfaces:**
- Consumes: Task 1 の `tr` / `translate_tree` / `set_language` / `other_language_label`
- Produces: `OperatorWindow._set_language(lang: str) -> None`、言語ボタン `OperatorWindow._lang_btn`（`QPushButton`）、`OperatorWindow._retranslate() -> None`

- [ ] **Step 1: 失敗するテストを書く**
  - `test_language_button_text`: `ja` の窓の `_lang_btn.text() == "English"`、`en` の窓では `"日本語"`
  - `test_language_button_is_right_of_calibration_fold`: `_lang_btn` と 心拍の補正の見出し（`fold_title == "心拍の補正（数字が合わないときだけ）"` の `QToolButton`）が同じ行（同じ親レイアウト）にあり、ボタンの `x` が見出しより右
  - `test_switch_to_english_and_back_restores_everything`: `_lang_btn.click()` で en。①〜⑤の枠の題名が英語。もう一度押すと `ja`。往復後に、全部品の文字が最初と同じ、`profile` の全フィールドが同じ
  - `test_switch_saves_language`: 押すと `tmp_path` の `app_state.json` に `language` が入る
  - `test_titles_stay_japanese_in_english`: `en` でも `windowTitle()` は `OPERATOR_WINDOW_TITLE`、配信用ウィンドウも `OUTPUT_WINDOW_TITLE`
  - `test_switch_during_calibration_keeps_tap_count`: 補正を始め、拍を 3 回打ち、`en` に切り替えても `_tap_btn.text()` に `3`、`_status` の文字に拍の数、ボタンの文字は「保存」側の英訳
  - `test_profile_name_with_braces_is_safe`: プロファイル名 `{0}x}` で `_save_current` → 知らせの文字に `{0}x}` がそのまま入る（`en` で）
  - `test_saved_color_not_in_list_survives_round_trip`: 一覧に無い色（`#123456`）のプロファイルで往復しても、その項目（`保存値 #123456`）が残り、選択が変わらない
- [ ] **Step 2: 実行して失敗を確かめる**
- [ ] **Step 3: 実装する**
  - `operator_window.py`: ここに出る文字の連結・f 文字列をテンプレート化して `tr` を通す（`obs_hint`、`cal_hint`、ステータス、`_flash(...)`、保存、確認ダイアログ、`QInputDialog`、`QFileDialog`、マイクを開けない、音が届かない、推しログ補助）。定数（`CAL_START` など）は日本語のまま残し、使う場所で `tr`。`startswith("時計と数字")` は `self._clock_warn: bool` の旗で判定し直す。`_tap_btn` の「拍  N」は `_tap_text()` に集め、`_sync_cal_ui` もそれを使う。
  - `fold.py`: `make_fold(title, inner, *, expanded=False, side: QWidget | None = None)`。`side` があれば見出しボタンと同じ横並びの行の右端に置く。
  - 言語ボタン: `QPushButton(other_language_label())`、`objectName` は `langBtn`、固定の小さな見た目（`styles.py` に最小限）。`clicked` → `_set_language("en" if language() == "ja" else "ja")`。
  - `_set_language(lang)`: `set_language` → `save_app_state(self._data_dir, language=lang)`（`OSError` は握りつぶして `_flash` しない）→ `_retranslate()`。
  - `_retranslate()`: `translate_tree(self)`、`_lang_btn.setText(other_language_label())`、`_refresh_style_controls()`、`_sync_cal_ui()`、タップ中は `_tap_btn` と `_status`、`_show_folder` に当たる VTS の更新は Task 4 で足す。
  - 作った直後の `__init__` の最後で `translate_tree(self)` を 1 回呼ぶ（起動時の言語が `en` のため）。
  - `app.py`: `QApplication` を作った直後に `init_language()`。
  - 英訳は `i18n_en.py` に足す（用語は仕様の「英訳の方針」に従う）。
- [ ] **Step 4: 通ることを確かめる** — `pytest tests/test_i18n.py tests/test_windows.py tests/test_operator_bugs.py -q`、続けて全体。
- [ ] **Step 5: Commit** — `操作画面: 日本語 / English の切り替えボタンを追加`

---

### Task 3: スタイル・演出・色・背景

**Files:**
- Modify: `ui/operator_controls.py`（`保存値 {value}` と演出の一覧）, `ui/effects.py`（ラベルとヒントはそのまま、`effect_choices` と `EFFECT_HINTS` を使う側で `tr`）, `i18n_en.py`
- Test: `tests/test_i18n.py`

**Interfaces:**
- Consumes: Task 1 の `tr`。Task 2 の `_retranslate`
- Produces: 表の英訳（`リアル1` → `Realistic 1`、`心エコー` → `Echo`、`MRI` → `MRI`、`レントゲン1〜3` → `X-ray 1`〜`3`、`かわいい1・2` → `Cute 1`・`2`、`オシャレ1・2` → `Chic 1`・`2`、`機械` → `Mechanical`、`パーティクル` → `Particles`、`心電図1・2` → `ECG 1`・`2`）、演出名・演出の説明・色・縁・背景の名前

- [ ] **Step 1: 失敗するテストを書く**
  - `test_style_combo_in_english`: `en` の窓のスタイル欄の全項目が英語（日本語の文字を含まない）で、`itemData` は変わらない
  - `test_effect_combo_rebuilt_in_current_language`: `en` でスタイルを心エコーにすると演出の一覧が英語、ヒントも英語。`ja` に戻すと日本語
  - `test_color_and_backdrop_combos_in_english`
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装** — `_sync_effect_choices` の `addItem(label, key)` と `_effect_hint.setText(hint)` を `tr` に通す。`_select_combo` の `保存値` は `tr("保存値 {value}", value=value)`。`_retranslate()` から `_sync_effect_choices()` を呼ぶ（`_refresh_style_controls` が呼ぶので追加は不要）。英訳を足す。
- [ ] **Step 4: 通ることを確かめる**（全体）
- [ ] **Step 5: Commit** — `スタイル・演出・色の名前を英訳`

---

### Task 4: VTube Studio 連携の欄

**Files:**
- Modify: `ui/vts_panel.py`, `vts.py`（画面に出る 2 つの失敗の文だけ。VTube Studio 側に出るパラメータの説明 `StreamHeartbeat: …` は変えない）, `i18n_en_vts.py`
- Test: `tests/test_vts.py`（既存。`ja` のまま通ること）, `tests/test_i18n.py`

**Interfaces:**
- Consumes: Task 1 の `tr`
- Produces: `VtsPanel.retranslate() -> None`（Task 2 の `_retranslate` から呼ぶ）、`how_to_text() -> str` / `trouble_text() -> str`（`HOW_TO` / `TROUBLE` の代わりの関数）、`style_names(keys)` が表示言語の名前と区切り（`、` → `, `、`〜` → `–`、`・` → ` & `）で返す

- [ ] **Step 1: 失敗するテストを書く**
  - `test_vts_panel_has_no_japanese_in_english`: `en` で `VtsPanel` を作り、各状態（`OFF`/`CONNECTING`/`WAITING_USER`/`READY`/`NO_VTS`/`DENIED`）に `_on_state` で変え、`READY` のうえで 心臓なし・あり・留めた・見た目が古い・古くて失敗・留め待ち・出せないスタイル の各メモを出し、全部品（隠れている部品も）の文字にひらがな・カタカナ・漢字が残らない（`StreamHeartbeat` や `VTube Studio` の英字はそのまま）
  - `test_style_names_in_english`: `style_names(ITEM_STYLES)` が `Realistic 1–3, X-ray 3, Cute 1 & 2, Chic 1 & 2, Mechanical`
  - `test_vts_panel_switch_updates_note_and_folder`: `ja` で出ていたメモと「書き出し先: …」が、`retranslate()` のあと英語になり、戻すと日本語
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装**
  - `STATE_LABELS`・`NOTE_*`・`*_NOTICE`・ボタン名は日本語の定数のまま。使う側（`_on_state`、`_refresh`、`_notify(...)`、`setText`）で `tr`。連結（`NOTE_PICKING = PICK_NOTICE + …`）と f 文字列は、`{}` つきの 1 つのテンプレートにして `tr(template, 名前=…)`。
  - `HOW_TO`・`TROUBLE` は 1 行ずつ（または 1 段落ずつ）を `tr` する関数 `how_to_text()` / `trouble_text()` に変え、`QLabel` はその結果で作る。`retranslate()` で作り直した文を入れる。
  - `style_names`: 日本語のラベルの語尾の数字で束ね、基本名は `tr(label)` の数字を除いた名前、区切りは `tr("、")`・`tr("〜")`・`tr("・")`。
  - 隠し部品も走査されるので、`retranslate()` は `_view = None` にして `_refresh()`、`_show_folder()`、`how_to`/`trouble` の文の差し替え、`_pin_btn` のツールチップ、スライダーの端の文字（走査が追う）を行う。
  - `QFileDialog` の題名と、`vts.py` の `アイテムを出せませんでした` / `決められませんでした` を `tr` に通す。
  - 英訳を `i18n_en_vts.py` に足す。
- [ ] **Step 4: 通ることを確かめる** — `pytest tests/test_vts.py tests/test_i18n.py -q`（`test_vts` 単体の GC 落ちは既知。メモリ `vts-and-focus-testing` を参照）、続けて全体。
- [ ] **Step 5: Commit** — `VTube Studio 連携の欄を英訳`

---

### Task 5: 状態・起動中・そのほか

**Files:**
- Modify: `session.py`（`tap_label`）, `config.py` の文字定数を使う側（`operator_window.py` は Task 2 で済み）, `ui/splash.py`, `app.py`, `ui/output_window.py`（画面に出る失敗の文があれば）, `i18n_en.py`
- Test: `tests/test_i18n.py`

**Interfaces:**
- Consumes: Task 1 の `tr`
- Produces: `HeartSession.tap_label()` が表示言語で返す

- [ ] **Step 1: 失敗するテストを書く** — `test_tap_label_in_english`（拍 0 / 間隔なし / 間隔あり の 3 通りが英語）、`test_splash_texts_in_english`（`WAIT_TEXT`・各 `step` の文）
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装** — `tap_label` と splash の文言をテンプレート化して `tr`。`app.py` の `splash.step("…")` は `tr(…)`。`PROCESS_DISPLAY_NAME` / ウィンドウの題名は変えない。
- [ ] **Step 4: 通ることを確かめる**（全体）
- [ ] **Step 5: Commit** — `状態の帯・起動中の文言を英訳`

---

### Task 6: 漏れ検査・目での確認・仕上げ

**Files:**
- Modify: `tests/test_i18n.py`, `README.md`（英語概要の 1 文）, `task.md`（`L-1` を消す）

- [ ] **Step 1: 漏れ検査のテストを書く**
  - `test_every_japanese_ui_literal_is_translated`: `src/stream_heartbeat` のうち `render/` 以外の `.py` を `ast` で読み、docstring を除く日本語を含む文字列定数がすべて `EN` のキーにある。許す例外は表 `NOT_UI`（ウィンドウの題名、`StreamHeartbeat(ぬ)` を含む名前、VTube Studio のパラメータの説明、OBS が探す文字など。入れる理由を 1 行ずつ書く）。日本語を含む `f` 文字列（`JoinedStr`）は例外以外 FAIL。
  - `test_every_tr_literal_has_english`: `tr("…")` の最初の引数が文字列のものはすべて `EN` にある。
  - `test_english_operator_window_has_no_japanese`: 英語の窓の全部品（隠れている部品を含む）に、許す文字（`日本語`、`ぬ`、利用者の入力）以外の日本語が無い。
  - `test_translation_placeholders_match`: 各エントリで日本語と英語の `{名前}` の集合が同じ。
- [ ] **Step 2: 失敗を直す** — 出てきた抜けを `EN` に足す・`tr` に通す。通るまで繰り返す。
- [ ] **Step 3: 目で確かめる** — `visual-check-styles` のやり方で操作用ウィンドウを日本語と英語で撮り、折り返しと幅（最小幅 440）が崩れていないかを見る。言語ボタンの位置と見た目も見る。崩れていれば `styles.py` か文を詰める。
- [ ] **Step 4: README の英語概要の 1 文を直す** — 「The app's interface and the detailed guide above are in Japanese.」を、画面は日本語 / English を切り替えられること（「心拍の補正」の右のボタン）と、詳しい案内は日本語であることに直す。ほかの README は変えない。`task.md` の `L-1` を消す。
- [ ] **Step 5: 全体を確かめる** — `.\.venv\Scripts\python.exe -m pytest -q` と `.\.venv\Scripts\python.exe -m ruff check src tests`。
- [ ] **Step 6: Commit と push** — `日本語 / English 切り替え: 漏れ検査・README の英語概要`、`git push origin main`
