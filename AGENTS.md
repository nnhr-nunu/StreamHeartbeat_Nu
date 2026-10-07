# AI エージェント向けガイド（StreamHeartbeat(ぬ)）

Cursor で開発するときの最短導線。全文読み込みを避け、触るファイルだけ開く。

## 最初に読む（タスク別）

| やること | 入口 |
| -------- | ---- |
| アプリ起動・2 窓の配線 | [`app.py`](./src/stream_heartbeat/app.py) |
| 操作画面 | [`operator_window.py`](./src/stream_heartbeat/ui/operator_window.py) |
| 配信用の窓（OBS 取り込み） | [`output_window.py`](./src/stream_heartbeat/ui/output_window.py) |
| 未完了タスク | [`task.md`](./task.md) |
| セットアップ | [`README.md`](./README.md) |

## 読まない（日常改修）

| ファイル | 理由 | 代わり |
| -------- | ---- | ------ |
| [`HISTORY.md`](./HISTORY.md)（作った場合） | アーカイブ | `git log` |
| 長い製品メモの全文 | トークン消費 | 必要な節だけ / `task.md` |

## Git（コミット・push）

**本リポジトリのデフォルト**: 切りの良いところで日本語メッセージの commit → `origin` へ push。Cursor ユーザールールの「明示指示まで commit しない」より **本ルールを優先**する。ユーザーがそのターンで「commit しないで」と言ったときだけスキップ。push が 10 秒以内に終わらない場合は commit まで済ませ、ユーザーに push を依頼する。

### commit 前

`.py` を変えたら **`pytest`** を実行する。UI を変えたら操作画面と配信用の窓の両方を確認する。

### 版を上げる（push の前）

main へ push するたびに CI が配布の zip を作り直し、リリースの題名の版（`最新版 v0.2.0 / …`）をアプリが読んで「新しい版が出ています」と知らせる。`src/stream_heartbeat/` か `packaging/` を変えて push するときは、[`__init__.py`](./src/stream_heartbeat/__init__.py) の `__version__` を上げる（版はここだけに書く）。

- 直し・小さな改善は 3 つ目（0.2.0 → 0.2.1）、機能の追加は 2 つ目（0.2.0 → 0.3.0）
- 1 回の push につき 1 回でよい（commit ごとではない）
- 上げ忘れると `.githooks/pre-push` が push を止める（有効にする: `git config core.hooksPath .githooks`）
- 版のタグ（`v0.2.0` など）は CI が付ける。手で付けない

### Windows（PowerShell）での commit

bash heredoc は使わない。手順は [`.cursor/rules/git-commit.mdc`](./.cursor/rules/git-commit.mdc)。

```
git status → commit → git push origin main → 報告に hash と origin 同期を書く
```

## ドキュメント

- 完了タスク → `task.md` から削除（履歴は `git log`）
- README は指示がない限り更新しない。製品補足は後で `docs/product/` へ
- 800 行を超えるファイルは責務単位で分割する

## Cursor ルール（`.cursor/rules/`）

| ファイル | 適用 |
| -------- | ---- |
| `StreamHeartbeat.mdc` | 常時（返信形式・ドキュメント・commit/push） |
| `output-overlay.mdc` | 常時（配信用窓の露出防止） |
| `cursor-workspace-titles.mdc` | 常時 |
| `cursor-model-routing.mdc` | 常時 |
| `composer-self-review.mdc` | 常時 |
| `git-commit.mdc` | 常時（PowerShell commit） |
| `python.mdc` | `src/**/*.py` |
| `testing.mdc` | `tests/**` |
