# StreamHeartbeat(ぬ)：自分の心拍で脈打つ心臓を配信に出すソフト

> 🇬🇧 **English speakers:** the app starts in English automatically if your OS language is not Japanese, and an English guide is at the [bottom of this page](#english-summary).

マイクで拾った自分の心音に合わせて、心臓がドクンと脈打つ映像を OBS へ出せる Windows / Mac 用ソフトです。VTuber のアバターの横や上に重ねて、緊張やドキドキを視聴者さんと共有できます。

操作用ウィンドウで見た目やマイクを決め、配信用ウィンドウを OBS で取り込む流れになっています。

**▶ [動画による使い方紹介（X 投稿）](https://x.com/nunu_hara/status/2106318291551781076)**

## 入手

**[最新版のダウンロードページを開く](https://github.com/nnhr-nunu/StreamHeartbeat_Nu/releases/tag/latest)**

1. 上のリンクを開き、下の表から使っている PC に合う zip をダウンロードします。
2. zip を展開します。
3. 展開したフォルダの `StreamHeartbeat.exe`（Mac は `StreamHeartbeat.app`）を開きます。

| OS | ダウンロードするファイル |
| -- | ------------------------ |
| Windows 10 / 11 | `StreamHeartbeat-windows.zip` |
| Mac（Apple チップ。M1 / M2 / M3 など） | `StreamHeartbeat-macOS.zip` |
| Mac（Intel。2016 年の MacBook Pro など） | `StreamHeartbeat-macOS-intel.zip` |

Mac は macOS 12 以降で動きます。Apple チップか Intel か分からないときは、左上のリンゴマーク → **この Mac について** の「チップ」（Apple）か「プロセッサ」（Intel）を見てください。

起動時に「Windows によって PC が保護されました」と出ることがあります。ストア経由の配布ではないためで、ウイルスではありません。**詳細情報** → **実行** を選んでください。

Mac で「開けません」「開発元を確認できません」などと出たときも同じ理由です。いったん閉じてから **システム設定 → プライバシーとセキュリティ**（macOS 12 は **システム環境設定 → セキュリティとプライバシー → 一般**）の **このまま開く** を押し、もう一度開いてください。初回にマイクの使用を聞かれたら **許可** を押してください。

## クレジット表記のお願い

配信や動画などでこのソフトを使っていただいた場合は、概要欄などに次の表記をお願いします。

```
StreamHeartbeat(ぬ)
開発者：ぬぬはら - 催眠音声制作者
YouTube(催眠音声)：https://www.youtube.com/@nnhr_nunu
YouTube(実写催眠)：https://www.youtube.com/channel/UCqYpbbypex0iOikcZRenxGA
X(Twitter)：https://x.com/nnhr_nunu
使い方など：https://github.com/nnhr-nunu/StreamHeartbeat_Nu
```

## 必要なもの

- 心音を拾えるマイク（聴診器型のマイクや、胸に当てたピンマイクなど）
- OBS Studio
- ヘッドホン（心拍の補正をするとき、自分の心音を聴くのに使います。あると便利です）
- VTube Studio（モデルに心臓を付けたいときだけ）

マイクの代わりに、録音した心音のファイルや Bluetooth の心拍計でも動かせます（β。下の「マイクの代わりの入力（β）」を参照）。

## 使い方（はじめての配信まで）

起動すると、操作用ウィンドウと配信用ウィンドウの 2 つが開きます。操作用ウィンドウは、上から「プロファイル」、①〜⑤ の欄、いちばん下の「心拍の補正」に分かれています。

設定を変えると配信用ウィンドウにすぐ反映され、**自動で保存**されます（保存ボタンはありません）。次の起動でもそのまま使えます。

1. **① 入力** で「マイク」を選び、心音を拾うマイクを選びます。胸に当てて、「音の大きさ」のバーが鼓動に合わせて動けば OK です。
2. **② スタイル** で心臓の見た目と演出を選び、大きさ・透明度・背景の色を決めます。スタイルと演出は、一覧の上でマウスのホイールを回すだけでも次々に切り替えられます。
3. 必要なら **③ 同期文字**（鼓動に合わせて跳ねる「❤」などの文字）と **④ 心拍数**（BPM の数字）にチェックを入れます。チェックを入れると、文言・大きさ・位置・色を決める欄が開きます。
4. OBS のソースに「ウィンドウキャプチャ」を追加し（Mac は「macOS 画面キャプチャ」を追加して、方法を「ウィンドウキャプチャ」にします）、`StreamHeartbeat(ぬ) - 配信出力` を選びます。
5. OBS で背景の色を抜きます。
   - 背景が緑: フィルタの「クロマキー」
   - 背景が白か黒: フィルタの「カラーキー」
   - 背景が透明: フィルタは要りません。Windows の OBS では、取り込んだ配信出力のプロパティで「キャプチャ方法」を「Windows 10（1903以降）」にしてください（「自動」のままだと透けないことがあります）。それでも透けないときは、背景を緑にしてクロマキーで抜きます
   - 枠まで写るときは、OBS 側でクロップしてください
6. 操作用ウィンドウの上の帯が緑になり、「心拍同期表示中」と出ていれば、心拍に合わせて動いています。

心拍数が半分や倍に出るなど、数字が合わないときだけ、いちばん下の **心拍の補正** を使ってください（下の「よくある質問」を参照）。

VTube Studio のモデルの胸に心臓を付けたいときは、**⑤ VTube Studio 連携** を使います（下の「VTube Studio 連携」を参照）。

## スタイルと演出

スタイルは 18 種類あります: リアル1〜4、心エコー、MRI、レントゲン1〜4、かわいい1・2、オシャレ1・2、機械、パーティクル、心電図1・2。レントゲン4 は、リアル1 と同じ心臓を X 線で写し、周りに肋骨を描きます（心臓の材質は操作画面で選べます）。

演出は、スタイルに重ねて出す動きです。選べる演出はスタイルによって変わります。

| 演出 | 選べるスタイル | 内容・操作 |
| ---- | -------------- | ---------- |
| はじけるハート | すべて | 鼓動のたびに、心臓から小さなハートがはじけます。配信用ウィンドウをクリックすると、その場所からも大きくはじけます |
| 心臓わしづかみ | リアル1〜4、レントゲン1〜4、かわいい1・2、オシャレ1・2、機械 | 手が心臓をつかみ、鼓動に合わせて握り直します。配信用ウィンドウを押している間は、ぎゅっと強く握ります |
| 聴診器1・2 | リアル1〜4、レントゲン1〜4、かわいい1・2、オシャレ1・2、機械 | 配信用ウィンドウの上でマウスを動かすと、聴診器がついてきます。クリックした所に置いておけます（マウスがウィンドウの外へ出るとそこへ戻ります）。1 は裏側（ベルの側）、2 は膜の面が見えます |
| 除細動器 | リアル1〜4、レントゲン1〜4 | 2 本のパドル（先端の円い金属の板）が心臓を左右からはさみます。配信用ウィンドウをクリックすると電気ショックをかけ、心臓がびくっと止まってから、毎回ちがう不整脈を出しながら今の心拍数へ戻ります（その間の心拍数は「--」） |
| カラードプラ | 心エコー | 血の流れを色で重ねます（赤: 探触子へ向かう流れ / 青: 遠ざかる流れ） |
| タギング | MRI | 拍のたびに格子の縞を焼き付けます。縞は心筋と一緒に曲がりながら薄れます |
| モニター画面 | 心電図1・2 | 心電図をベッドサイドのモニターの画面に映します。拍で右上のハートが光ります |

リアル1〜4・レントゲン3・4・オシャレ2・機械は立体の心臓で、配信用ウィンドウを左ドラッグすると好きな向きに回せます（心臓わしづかみ・除細動器の間は正面に固定）。

背景は 緑 / 白 / 黒 / 透明 から選べます。透明にすると配信用ウィンドウを開き直すので、OBS の取り込みが外れたら選び直してください。OBS 側の設定は「使い方」の手順 5 を参照してください。

## VTube Studio 連携

VTube Studio のモデルの胸に心臓を付けて、心拍に合わせて動かせます。付けた心臓は、モデルが動いても一緒についていきます。

出せるスタイルは、リアル1〜4、レントゲン3・4、かわいい1・2、オシャレ1・2、機械 です。Mac 版の VTube Studio との連携は、まだ実機で確かめていません。

### 準備（はじめの 1 回だけ）

1. VTube Studio を起動して、モデルを表示しておきます。
2. VTube Studio の設定（歯車のアイコン）を開き、プラグインの欄にある **「APIの起動（プラグインを許可）」** をオンにします。ポート番号は 8001 のままにします。歯車が見えないときは、VTube Studio の画面をダブルクリックすると出ます。
3. 操作用ウィンドウの **⑤ VTube Studio 連携** で、「VTube Studio とつなぐ」にチェックを入れます。
4. VTube Studio の画面に、このアプリ（StreamHeartbeat）をつないでよいかの確認が出るので、**「許可」** を押します。⑤ の欄に「VTube Studio とつながりました」と出れば準備完了です。

### 心臓をモデルに付ける

5. 「心臓を出す」を押します。VTube Studio の画面に心臓が出ます（スタイルによっては数秒かかります）。
6. 「心臓を付ける場所を選ぶ」を押します。心臓はクリックの邪魔にならないよう、いったん VTube Studio の画面の左端へよけます。
7. VTube Studio の画面に切り替えて、モデルの胸（心臓を付けたい所）を **左クリック** します。心臓がそこへ移ります。肩や頭など、モデルの上ならどこにでも付けられます。モデルの無い所や右クリックでは決まりません。やめるときはボタンをもう一度押します。
8. 「大きさ」のつまみで、心臓の大きさを合わせます。

### 次からは

- 付けた場所はモデルごとに、大きさは全体で覚えています。「VTube Studio とつなぐ」にチェックを入れたままにしておけば、次からはこのアプリと VTube Studio を起動するだけで、同じ所に心臓が出ます。VTube Studio をあとから起動しても、自動でつながります。
- スタイルや心臓の向きを変えたときは「作り直す（今の見た目で）」を押すと、VTube Studio の心臓も同じ見た目になります（押すまでは前の見た目のままです）。
- 心臓を消すときは「しまう」を押します。次に起動しても出ません（また出すときは「心臓を出す」）。

### パラメータ（上級者向け）

「心拍を VTube Studio のパラメータにも送る（上級者向け）」にチェックを入れると、次の 2 つを VTube Studio のパラメータとして送ります。

| パラメータ | 値 |
| ---------- | -- |
| `SHBHeartbeat` | 拍の瞬間に 1、拍と拍のあいだは 0 に近い値 |
| `SHBBpm` | 心拍数 |

VTube Studio のモデル設定で、パラメータの入力にこれを選ぶと、拍に合わせてモデルの体や表情を動かせます。

### 上手くいかないとき

| 困ったこと | 確かめること |
| ---------- | ------------ |
| 「VTube Studio とつながりません」と出る | VTube Studio が起動しているか、「APIの起動（プラグインを許可）」がオンか、ポート番号が 8001 のままか（つながるまで 5 秒ごとに試します） |
| 「確認が出ています」のまま進まない | VTube Studio の画面を前に出すと、確認が出ています。「許可」を押してください |
| 「許可されなかった」と出る | もう一度チェックを入れ、VTube Studio に出た確認で「許可」を押してください |
| 心臓が出ない | ⑤ の「上手くいかない時」を開き、「書き出し先」が VTube Studio の Items フォルダ（Windows は `VTube Studio_Data\StreamingAssets\Items`）になっているか確かめてください。Steam 以外で入れたときは「フォルダを選ぶ」で選び直します |
| VTube Studio 側で心臓を消してしまった | 「心臓を出す」をもう一度押してください |
| 心臓の位置がずれた・別の所に付け直したい | 「心臓を付ける場所を選ぶ」を押して、モデルをクリックし直してください |

## マイクの代わりの入力（β）

**① 入力** の「入力」で、マイクの代わりに次の 2 つを選べます。どちらも試験中の機能（β）です。選んだものと、選んだファイル・つないだ心拍計は覚えていて、次の起動でもそのまま使えます。

### 録音した心音のファイル

録音しておいた心音で心臓を動かします。

1. 「入力」で「音声・動画ファイル（β）」を選びます。
2. 「選ぶ…」でファイルを選ぶと、読み込んで流し始めます。wav・mp3・m4a などの音声と、mp4・mov などの動画（音だけ使います）を読めます。長いファイルは最初の 60 分まで使います。
3. 「■ 止める」で止まり、「▶ 再生」で頭から流します。

- 「くり返し再生」にチェックを入れておくと、最後まで流したら頭に戻って流し続けます（外すと最後で止まります）。
- 「音も鳴らす」にチェックを入れると、この PC のスピーカーからも音が出ます。OBS でデスクトップの音を取り込んでいると配信に乗るので注意してください。
- 心拍数が半分や倍に出るときの「心拍の補正」も、ファイルの音で使えます。
- 動画編集で使うときは、ファイルを流しながら配信用ウィンドウを録画して、動画に重ねてください（ファイルから直接書き出す機能はまだありません）。

### Bluetooth の心拍計

心拍を Bluetooth で送れる心拍計や腕時計から、心拍数を受け取って動かします。標準の Bluetooth の心拍（Heart Rate）を送れる機器に対応しています。

1. 心拍計を着けて、心拍を送る状態にします（時計は下の表の設定）。
2. 「入力」で「Bluetooth 心拍計（β）」を選び、「探す」を押します。
3. 見つかった心拍計を一覧から選んで「つなぐ」を押します（1 台だけ見つかったときは、すぐつなぎます）。
4. 上の帯に「心拍計から受信中 ◯◯ BPM」と出れば OK です。次からは、起動すると同じ心拍計に自動でつなぎます。

| 機器 | 心拍を送る設定 | 使えるか |
| ---- | -------------- | -------- |
| 胸ベルト・腕のセンサー（Polar H10・H9・Verity Sense、Garmin HRM-Dual・HRM-Pro、Wahoo TICKR、COOSPO など） | 着けるだけ | ○ いちばん確実です |
| Google Pixel Watch 2 以降 | 文字盤を下にスワイプ →「Connected Fitness」→「接続」（はじめは「拡張デバイス アクセス」をオン） | △ PC とつながるかは未確認 |
| Fitbit Charge 6 | 文字盤を下にスワイプ →「機器内の心拍数」 | △ PC とつながるかは未確認。同時に 1 台だけ |
| Fitbit Air | Google Health アプリの「心拍数を共有」 | △ PC とつながるかは未確認 |
| Garmin の腕時計 | 「心拍数をブロードキャスト」（Broadcast Heart Rate） | △ 機種による（古い機種は ANT+ だけで使えません） |
| Amazfit（Zepp OS 3 以降）・HUAWEI・Xiaomi の一部 | 「Heart Rate Push」「HR Data Broadcasts」など | △ 機種による・未確認 |
| Apple Watch・Galaxy Watch | 標準では送れません | × 心拍を送る別のアプリが要ります |
| Fitbit のほかの機種（Inspire・Versa・Sense など） | 送る機能がありません | × |

- 届くのは心拍数（機種によっては拍と拍の間の長さも）だけです。心臓はその間隔で脈打つので、心拍数は合いますが、拍の瞬間は本物の鼓動とずれます。心拍数が変わってから表示が変わるまでも、マイクより少し遅れます。
- スマホのアプリ（Zwift・Strava など）とつながっている間は、PC からつなげない機種があります（Polar H9・Fitbit Charge 6 などは同時に 1 台だけ）。先にスマホ側を切ってください。
- Bluetooth を使える PC が要ります（ノート PC はたいてい内蔵。デスクトップは USB の Bluetooth アダプタ）。Mac は、はじめに Bluetooth の使用許可を聞かれるので「許可」を押してください。
- 心拍計の実機では、まだ作者が確かめていません。使えた機種・使えなかった機種を教えてもらえると助かります。
- 音が無いので、心拍計のときは「心拍の補正」は使えません。

## 画面の見方

| 操作用ウィンドウの上の帯 | 意味 |
| ------------------------ | ---- |
| 緑「心拍同期表示中 ◯◯ BPM」 | 心音を読み取れていて、その心拍で脈打っています |
| 黄「プレビュー中（心音未認識）」 | まだ心音を読み取れていません。マイクの位置や選択を確かめてください（途中で見失ったときは、最後の BPM も出ます） |
| 紫「補正中」 | 心拍の補正の録音中です。鼓動に合わせて「拍」を押してください |

保存できなかったときやマイクの音が届かないときなどの知らせも、この帯に出ます。

## 操作

| やりたいこと | 操作 |
| ------------ | ---- |
| スタイル・演出をさっと切り替える | 一覧の上でマウスのホイールを回す |
| 立体の心臓を回す（立体のスタイルのみ） | 配信用ウィンドウを左ドラッグ |
| 心臓の向きを元に戻す | 配信用ウィンドウをダブルクリック / ② の「角度をリセット」 |
| 回らないように固定する | ② の「角度を固定」 |
| 演出を動かす | 配信用ウィンドウをクリック（「スタイルと演出」の表を参照） |
| 配信ごとに見た目を切り替える | 「名前を付けて保存」で別のプロファイルを作り、いちばん上の「プロファイル」で選ぶ |
| 補正中に拍を打つ | スペースキー / 「拍」ボタン |
| 終了する | どちらかのウィンドウを閉じる（両方とも閉じます。設定は自動で保存されます） |

## よくある質問

### Q. 心臓が心拍に合わせて動きません

**A.** 次を確かめてください。

1. ① の「音の大きさ」のバーが鼓動に合わせて動いているか。動かないときはマイクの選択や、胸への当て方を見直してください。
2. 話し声や物音が大きくないか。大きいと読み取りにくくなります。
3. 心拍数が半分や倍に出ていないか。出ているときは、次の質問の補正を試してください。

### Q. 心拍数が半分や倍に出ます

**A.** 操作用ウィンドウのいちばん下にある **心拍の補正（数字が合わないときだけ）** を開いて、次の手順で補正します。

1. 「補正開始」を押します。マイクが拾った自分の心音が聞こえてきます（ヘッドホンがおすすめです）。
2. 鼓動に合わせて「拍」ボタン（またはスペースキー）を 10 回ほど押します。
3. 「補正を保存」を押します。

途中でやめるときは「中止」を押します。補正をやり直したいときは「保存した補正を消す」で最初の状態に戻せます。

### Q. 「マイクを開けません」と出ます

**A.** 同じマイクを OBS でも使っているときは、Windows のサウンド設定でそのマイクの「アプリケーションによりこのデバイスを排他的に制御できるようにする」（独占モード）をオフにしてください。

Mac で音の大きさのバーが動かないときは、マイクの使用を許可していないかもしれません。**システム設定 → プライバシーとセキュリティ → マイク**（macOS 12 は **システム環境設定 → セキュリティとプライバシー → プライバシー → マイク**）で StreamHeartbeat をオンにして、開き直してください。新しい版に入れ替えたあとは、もう一度許可を聞かれることがあります。

### Q. 操作用ウィンドウも配信に映したい

**A.** 操作用ウィンドウも OBS の「ウィンドウキャプチャ」で取り込めます。`StreamHeartbeat(ぬ)` の操作画面を選んでください。

### Q. 設定はどこに保存されますか

**A.** 設定は変えるたびに自動で、PC 側のアプリデータ（Windows は `%LOCALAPPDATA%\StreamHeartbeat_Nu`、Mac は `~/Library/Application Support/StreamHeartbeat_Nu`）に保存されます。新しい版の zip に入れ替えても、プロファイルや補正はそのまま残ります。

## 開発者・お問い合わせ

開発者: ぬぬはら
X: [@nnhr_nunu](https://x.com/nnhr_nunu)

バグ報告は X の DM などでお願いいたします。
配信でご利用いただける場合、もしよければフォローしていただけたらとても嬉しいです。

## 利用上の注意

- これは医療機器ではありません。表示される心拍数は目安で、診断・治療には使えません。
- 心音の読み取りは環境によってずれることがあります。配信の前に操作用ウィンドウで動きを確かめてください。
- このソフトウェアの利用による不都合について、開発者は責任を負いかねます。

---

## English (summary)

**StreamHeartbeat(ぬ)** is a Windows / macOS app that picks up your own heart sound with a microphone and shows a heart beating in time with it. Put it in your OBS scene next to your avatar and share your nerves and excitement with your viewers.

The app's interface **automatically starts in English** unless your OS display language is Japanese. You can also switch between Japanese and English at any time with the "English" / "日本語" button next to "Heartbeat calibration" at the bottom of the control window (your choice is remembered). The detailed guide above is in Japanese.

- **Video guide (Japanese):** [X post](https://x.com/nunu_hara/status/2106318291551781076)
- **Download:** [latest release](https://github.com/nnhr-nunu/StreamHeartbeat_Nu/releases/tag/latest)

| OS | File |
| -- | ---- |
| Windows 10 / 11 | `StreamHeartbeat-windows.zip` |
| macOS 12+, Apple silicon (M1 / M2 / M3 …) | `StreamHeartbeat-macOS.zip` |
| macOS 12+, Intel | `StreamHeartbeat-macOS-intel.zip` |

Unzip it and open `StreamHeartbeat.exe` (Windows) or `StreamHeartbeat.app` (macOS).

**Credit:** if you use this software in a stream or video, please add the following credit to the description (the Japanese block in the section "クレジット表記のお願い" above works just as well).

```
StreamHeartbeat(ぬ)
Developer: Nunuhara (ぬぬはら) - hypnosis audio creator
YouTube (hypnosis audio): https://www.youtube.com/@nnhr_nunu
YouTube (live-action hypnosis): https://www.youtube.com/channel/UCqYpbbypex0iOikcZRenxGA
X (Twitter): https://x.com/nnhr_nunu
Usage guide: https://github.com/nnhr-nunu/StreamHeartbeat_Nu
```

It would also mean a lot to me if you could like and repost the introduction post on X. Thank you!
https://x.com/nunu_hara/status/2106318291551781076

**What you need:** a microphone that can pick up your heartbeat (a stethoscope-type mic, or a lavalier mic pressed against your chest) and OBS Studio. Headphones are optional but handy for calibration. VTube Studio is only needed if you want to attach the heart to a model.

**Quick start**

1. Launch the app. Two windows open: the control window and the output window. Changes apply immediately and are saved automatically.
2. In section ① (input), choose "Microphone" and your mic, then hold it against your chest. The level bar should move with each beat.
3. In section ② (style), choose a heart style and effect, then set the size, opacity and background color (green / white / black / transparent).
4. In OBS, add a *Window Capture* source (on macOS: *macOS Screen Capture* with the *Window Capture* method) and select the window titled `StreamHeartbeat(ぬ) - 配信出力`.
5. Remove the background in OBS: a *Chroma Key* filter for green, a *Color Key* filter for white or black. A transparent background needs no filter; on Windows, set the source's *Capture Method* to "Windows 10 (1903 and later)".
6. When the bar at the top of the control window turns green ("Synced to your heartbeat"), the heart is beating with you.

**Beta: other inputs.** Instead of a microphone, section ① can also use:

- *Audio / video file (beta):* plays a recorded heart sound (wav, mp3, m4a, mp4, mov …, up to the first 60 minutes) as if it came from the mic. "Loop" starts it again from the beginning; "Play the sound" also plays it on your speakers.
- *Bluetooth HR monitor (beta):* receives the heart rate from a monitor that sends the standard Bluetooth heart rate service. Chest straps and arm sensors (Polar H10 / H9 / Verity Sense, Garmin HRM-Dual / HRM-Pro, Wahoo TICKR, COOSPO …) work best. Some watches can send it when set to (Pixel Watch 2 or later: "Connected Fitness", Fitbit Charge 6: "HR on Equipment", Garmin: "Broadcast Heart Rate"), but whether they connect to a PC is unconfirmed. Apple Watch and Galaxy Watch can't send it on their own. Only the heart rate arrives, so the heart beats at that rate but not exactly with your real heartbeat. Some monitors can't connect to the PC while a phone app is connected to them.

**Troubleshooting**

- *The BPM is half or double the real value:* open the "Heartbeat calibration" panel at the bottom of the control window, press "Start calibration", tap the beat button (or the space bar) about 10 times in time with your heartbeat, then save.
- *Windows says "Windows protected your PC":* the app is not distributed through the Microsoft Store; it is not a virus. Click "More info" → "Run anyway".
- *macOS refuses to open the app:* close the dialog, open System Settings → Privacy & Security and click "Open Anyway". Allow microphone access when asked.
- *"Cannot open the microphone":* if OBS uses the same mic, turn off exclusive mode for that device in the Windows sound settings.

**Notes**

- This is not a medical device. The displayed BPM is only a rough guide and must not be used for diagnosis or treatment.
- Use at your own risk; the developer accepts no liability for any problems caused by using this software.

**Developer / contact:** Nunuhara — X: [@nnhr_nunu](https://x.com/nnhr_nunu). Bug reports by DM are welcome.
