# StreamHeartbeat(ぬ) タスク一覧（未完了のみ）

完了の詳細は `git log`。仕様は [docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md](./docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md)。

| ID | やること |
| -- | -------- |
| R-2 | Live2D 差し込み口 |
| R-3 | リアルの上に重ねる血液の飛び |
| O-1 | OshiLog の Firestore 最新 BPM をログイン無しで読む経路 |
| D-1 | 100〜120 BPM でドッとクンがほぼ等間隔になると、どちらがドッか決められずクンに合わせることがある（BPM は正しい。失神前後の録音 120〜240 秒で約 4 割。音の高さでは見分けられなかった） |
| D-2 | 心音の型との照合を時間合わせ付きで作り直す（時間合わせ無しでは本物の拍を落とすだけだったので `BUNDLED_CORR_MIN` 0 で止めている。声などを弾く役目も果たせていなかった） |
