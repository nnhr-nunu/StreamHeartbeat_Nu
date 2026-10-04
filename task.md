# StreamHeartbeat(ぬ) タスク一覧（未完了のみ）

完了の詳細は `git log`。仕様は [docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md](./docs/superpowers/specs/2026-09-18-stream-heartbeat-design.md)。

| ID | やること |
| -- | -------- |
| R-1 | Blender の心臓モデル（`material/`・git 管理外）を新しいリアル1 に。`material/data/wip/GLB/4.glb` の形とシェイプキー 3 つ・1 秒の拍アニメを小さなバイナリに変換して `assets/` へ。見た目はグラデ（`material/data/wip/動画/４` の水色〜ピンク〜紫。波模様の色は `scripts/heart_model/bake_gradient.py` で `material/build/gradient_bake.png` に書き出し済み。陰 2 段・縁の暗さはシェーダーで。数値はメモリ blender-heart-model）と、できればガラス風（水色・透け・縁の光・`material/build/glass_env.png` の映り込み・ノイズのでこぼこ。表面の血管は形に入っている）。既存リアル1〜3 は表示名だけリアル2〜4 へずらす（保存キーは変えない）。最初の起動は新リアル1。断面と手のへこみは最初は外す |
| R-2 | Live2D 差し込み口 |
| R-3 | リアルの上に重ねる血液の飛び |
| O-1 | OshiLog の Firestore 最新 BPM をログイン無しで読む経路 |
| D-1 | ドッとクンの音色（高い音の割合）が分かれない録音では、100 BPM を超えてほぼ等間隔になるとクンに合わせることがある（音色で分かれる失神前後の録音は取り違え 15%→6% に改善済み）。擦れ音で拍が抜ける区間（失神前後 180〜190 秒・240〜300 秒）は表示 BPM が乱れる |
| D-2 | 心音の型との照合を時間合わせ付きで作り直す（時間合わせ無しでは本物の拍を落とすだけだったので `BUNDLED_CORR_MIN` 0 で止めている。声などを弾く役目も果たせていなかった） |
| D-3 | 心音なしで大きなキーボード・衣擦れだけが入ると、まだ拍を拾う（`scripts/heart_eval/noise_eval.py` の「心音なし」で 1 分 15〜35 回。話し声は小さめなら 2〜3 回まで減った） |
| M-1 | Mac の実機で確かめる: マイクの許可が出て音が取れるか・立体の心臓が 2D に落ちずに出るか・OBS の「macOS 画面キャプチャ」で配信出力を取り込めるか・VTube Studio（Mac の Steam 版）のアイテムのフォルダが見つかるか・心エコー/MRI の 2 回描き（縮めた画を使うぼかし）とオシャレ2（ポリゴン）・心臓わしづかみの GL の手（心臓に巻き付く手。描けないと平らな 2D の手になる）が出るか（CI では起動とシェーダーまでしか確かめられない） |
