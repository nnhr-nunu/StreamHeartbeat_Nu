# StreamHeartbeat(ぬ) タスク一覧（未完了のみ）

完了の詳細は `git log`。仕様は [docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md](./docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md)。

| ID | やること |
| -- | -------- |
| R-2 | Live2D 差し込み口 |
| R-3 | リアルの上に重ねる血液の飛び |
| O-1 | OshiLog の Firestore 最新 BPM をログイン無しで読む経路 |
| D-1 | 110 BPM 超でドッでなくクンに合わせてしまう（BPM は正しい。見た目の拍が約 0.25 秒遅れる） |
| D-2 | 心音の型との照合が時間合わせ無しで、ほぼ効いていない（`BUNDLED_CORR_MIN` 0.08） |
| B-1 | 操作画面の色の選択肢に無い色がプロファイルにあると、他の項目を触った時に上書きされる |
| B-2 | 補正を保存するたびに録音全体がプロファイルに積み増される（保存ファイルが大きくなる） |
