"""StreamHeartbeat(ぬ) — 配信者向け心拍同期の心臓描画。"""

# 配布物の版。アプリの中身を変えて main へ push するときは必ず上げる（AGENTS.md の Git の節）
__version__ = "0.2.0"
OUTPUT_WINDOW_TITLE = "StreamHeartbeat(ぬ) - 配信出力"
OPERATOR_WINDOW_TITLE = "StreamHeartbeat(ぬ)"


def display_version() -> str:
    return f"v{__version__}"
