# StreamHeartbeat(ぬ)

配信中に心臓の描画を出すためのデスクトップアプリです。開発中の骨格で、製品の動きはまだありません。

## 開発者向けセットアップ（Windows）

Python 3.10 を使います。

```powershell
cd D:\Dev\StreamHeartbeat_Nu
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\pytest.exe
```

起動:

- `起動.bat`
- または `.\.venv\Scripts\python.exe -m stream_heartbeat`

窓は 2 つ出ます。

- `StreamHeartbeat(ぬ)` … 操作画面
- `StreamHeartbeat(ぬ) - 配信出力` … OBS の「ウィンドウの取り込み」用（いまは緑一色）

## 開発ルール

OshiLog と同じ運用（日本語 commit、完了は `git log`、`task.md` は未完了のみ、README は入口専用）に、StreamMediaViewer(ぬ) の Python / 2 窓 / Cursor ルールを合わせています。詳細は [`AGENTS.md`](./AGENTS.md)。
