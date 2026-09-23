# StreamHeartbeat(ぬ) — Claude Code 向け

@AGENTS.md

## Claude Code での補足

- `.cursor/rules/*.mdc` の内容が正本のルール。特に次は毎回守る:
  - 返信は日本語。先頭 2 行は `# ★【対応結果】★：{kind}-{ID}{絵文字}` と `---`（`StreamHeartbeat.mdc`）
  - 配信用の窓にデバッグ文字・パス・例外文を出さない（`output-overlay.mdc`）
  - コード変更後はセルフレビュー → `pytest` → 日本語で commit → `git push origin main`（`composer-self-review.mdc`）
  - README は指示がない限り更新しない。完了タスクは `task.md` から消す
- 開発用 Python は `.venv\Scripts\python.exe`（3.10）。`pytest` / `ruff check src tests` もここから
- `QT_QPA_PLATFORM=offscreen` だと OpenGL が使えず、窓位置テスト 1 件が失敗する。窓/GL を確かめるときは offscreen 無しで実行
- commit は PowerShell 前提。bash heredoc は使わず `-m` か `-F` を使う（`git-commit.mdc`）

## 主な作業領域の入口

| 目的 | 入口 |
| ---- | ---- |
| UI・見た目 | `ui/operator_window.py`（803 行。追加時は分割）, `ui/styles.py`, `ui/slider.py`, `ui/combo.py` |
| 心臓モデル（立体） | `render/heart_mesh.py`, `render/heart_shaders.py`, `render/heart_gl.py`, `ui/heart_realistic.py` |
| 心臓モデル（2D 各種） | `ui/heart_cute.py`, `heart_ecg.py`, `heart_echo.py`, `heart_imaging.py`, `heart_paint.py`, `motion.py` |
| 心音認識 | `detect.py`（ピーク検出・型）, `audio.py`, `session.py`, `profile.py`（キャリブ）, `samples.py` + `tests/test_detect.py` |
