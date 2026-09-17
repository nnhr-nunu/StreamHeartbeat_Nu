# StreamHeartbeat(ぬ)

配信中に、自分の心拍に合わせて脈打つ心臓を OBS へ出すソフトです。VTube Studio のアバターの上に重ねる想定です。

操作用ウィンドウで見た目とマイクを決め、配信用ウィンドウを OBS が取り込みます。

## 入手

**[最新版のダウンロードページを開く](https://github.com/nnhr-nunu/StreamHeartbeat_Nu/releases/tag/latest)**

1. 上記の最新版ページを開きます。
2. Windows は `StreamHeartbeat-windows.zip` をダウンロードします。
3. zip を展開します。
4. `StreamHeartbeat.exe` を開きます。

起動時に「Windows によって PC が保護されました」と出ることがあります。ストア経由ではないためで、ウイルスではありません。**詳細情報** → **実行** を選んでください。

## 使い方

1. 操作画面でマイクを選びます。同じマイクを OBS でも使うときは、OBS 側の独占モードをオフにしてください。
2. 必要なら「キャリブ開始」で心音と少しの発話を録り、「このセッションを採用」します。
3. スタイル・大きさ・透明度・「ドクン」などの文字を決めます。変更は配信用へすぐ出ます。
4. OBS で「ウィンドウの取り込み」を追加し、`StreamHeartbeat(ぬ) - 配信出力` を選びます。
5. クロマキーで緑を抜きます。枠まで写るときは OBS 側でクロップします。
6. 操作画面を閉じるとアプリごと終了し、配信からも消えます。

設定は Windows のアプリデータに残るので、zip を入れ直してもプロファイルは残ります。

## 開発者向けセットアップ（Windows）

Python 3.10 を使います。

```powershell
cd D:\Dev\StreamHeartbeat_Nu
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\pip.exe install -e ".[dev]"
.\.venv\Scripts\pytest.exe
```

起動は `起動.bat`、または `.\.venv\Scripts\python.exe -m stream_heartbeat`。

## 開発者・お問い合わせ

開発者: ぬぬはら
X: [@nnhr_nunu](https://x.com/nnhr_nunu)
