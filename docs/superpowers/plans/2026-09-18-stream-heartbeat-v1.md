# StreamHeartbeat(ぬ) 初回公開 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (tasks are tightly coupled). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 心音を時計にした心臓オーバーレイを、操作画面と OBS 用緑窓で動かす。

**Architecture:** 設定・心音検出・拍時計・描画状態を UI から分離する。操作画面は状態を変え、配信用は状態を塗るだけ。OshiLog は任意の補助 BPM 源。

**Tech Stack:** Python 3.10、PySide6（Widgets + Multimedia）、pytest。Windows。

**Spec:** `docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md`

## Global Constraints

- 配信用に出してよい画素: 心臓、同期文字、設定オンの BPM、条件時の不整脈文字。検出ロスト文言は操作画面のみ。
- クロマキー緑は `#00FF00`。心臓と文字に使わない。
- 操作画面 close = プロセス終了。出力だけ隠す UI は置かない。
- 心音はローカルのみ。OshiLog へ音を送らない。
- プロファイル既定: `%LOCALAPPDATA%\StreamHeartbeat_Nu\`。exe 横 `data` があればそちら優先。
- 拍ロスト時は最後の BPM（無ければ 70）で打ち続ける。操作画面は「検出できていません」。
- スライダーは配信用へ即反映。
- 医療機器ではない旨は操作画面。
- Windows のみ。

---

### Task 1: パスとプロファイル

**Files:**
- Create: `src/stream_heartbeat/config.py`
- Create: `src/stream_heartbeat/paths.py`
- Create: `src/stream_heartbeat/profile.py`
- Test: `tests/test_paths.py`, `tests/test_profile.py`

**Produces:**
- `CHROMA_GREEN = QColor(0, 255, 0)` は描画側。config は `CHROMA_HEX = "#00FF00"`, `DEFAULT_BPM = 70`, `APP_DIR_NAME = "StreamHeartbeat_Nu"`
- `resolve_data_dir(exe_dir: Path, *, localappdata: Path, portable_exists: bool) -> Path`
- `HeartProfile` dataclass + `load_profile` / `save_profile` / `list_profiles` / `app_state.json` の last profile 名

- [ ] テスト先行で data 優先と AppData フォールバック、JSON 往復、未知キー無視

---

### Task 2: 拍時計と不整脈

**Files:**
- Create: `src/stream_heartbeat/clock.py`
- Test: `tests/test_clock.py`

**Produces:**
- `BeatClock.feed_beat(t: float) -> None`
- `BeatClock.pulse_scale(t: float) -> float` 拍直後 1.0 に近づき戻る
- `BeatClock.bpm` 心音由来。ロスト後も last bpm（初期 70）
- `BeatClock.detected: bool`
- `BeatClock.lost_if_silent(t: float) -> None` 期待間隔の 2.5 倍でロスト、メトロノーム継続
- `BeatClock.pop_arrhythmia(t: float) -> bool` 25% ずれ 2 連続、8s クールダウン
- `BeatClock.oshilog_bpm` 補助。`bpm_mismatch() -> bool` 差 20 以上

---

### Task 3: 心音検出とキャリブ型

**Files:**
- Create: `src/stream_heartbeat/detect.py`
- Test: `tests/test_detect.py`

**Produces:**
- `envelope_rms(samples: list[float], hop: int) -> list[float]`
- `CalibrationTemplate.from_sessions(sessions: list[list[float]]) -> CalibrationTemplate`
- `HeartSoundDetector.feed(samples, t) -> list[float]` 拍時刻。型があれば相関、無ければピーク。最小間隔 60/220 秒

---

### Task 4: 描画状態とふわっと文字

**Files:**
- Create: `src/stream_heartbeat/overlay.py`
- Test: `tests/test_overlay.py`

**Produces:**
- `HeartStyle` = realistic | cute | mech | ecg
- `FloatBurst` 文言・位置・開始時刻
- `OverlayState.on_beat(t, text: str)` / `on_arrhythmia(t)` 同時最大 3、内側 15% 余白の乱数位置（rng 注入）
- `OverlayState.bursts_at(t)` アルファ
- BPM 数字は overlay に載せるが未検出ラベルは載せない

---

### Task 5: 配信用キャンバスと操作画面

**Files:**
- Modify: `src/stream_heartbeat/ui/output_window.py`
- Modify: `src/stream_heartbeat/ui/operator_window.py`
- Modify: `src/stream_heartbeat/app.py`
- Create: `src/stream_heartbeat/audio.py`
- Create: `src/stream_heartbeat/oshilog.py`
- Modify: `tests/test_windows.py`

**Notes:**
- 出力: 緑全面、スタイル別心臓、pulse_scale、bursts、show_bpm なら数字。最前面可。隠すボタン削除。
- 操作: プロファイル、マイク、キャリブ開始/採用/破棄、スタイル、大きさ、透明度、同期文字、BPM オン、OshiLog ID/URL、検出状態、補助 BPM、ズレ警告、免責。
- マイクは Qt Multimedia 共有。テストはデバイス無しでも時計を手動 feed できること。
- OshiLog: `fetch_aux_bpm(url) -> int | None` と public id 保存。URL が `{"bpm": n}` なら読む。

- [ ] pytest 全件 / ruff
