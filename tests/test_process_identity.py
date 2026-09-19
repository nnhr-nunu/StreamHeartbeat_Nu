from pathlib import Path

from stream_heartbeat.ui import app_icon
from stream_heartbeat.ui.app_icon import PROCESS_DISPLAY_NAME, configure_process_identity


def test_process_display_name_is_app_title() -> None:
    assert PROCESS_DISPLAY_NAME == "StreamHeartbeat(ぬ)"


def test_configure_process_identity_sets_console_title(monkeypatch) -> None:
    titles: list[str] = []

    class Kernel:
        @staticmethod
        def SetConsoleTitleW(text: str) -> int:
            titles.append(text)
            return 1

    class Shell:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(_app_id: str) -> int:
            return 0

    class Windll:
        kernel32 = Kernel()
        shell32 = Shell()

    monkeypatch.setattr(app_icon.sys, "platform", "win32")
    monkeypatch.setattr(app_icon.ctypes, "windll", Windll(), raising=False)
    configure_process_identity()
    assert titles == [PROCESS_DISPLAY_NAME]


def test_configure_process_identity_does_not_raise() -> None:
    configure_process_identity()


def test_windows_version_file_names_the_app() -> None:
    text = Path("packaging/windows_version.txt").read_text(encoding="utf-8")
    assert "StreamHeartbeat(ぬ)" in text
    assert "FileDescription" in text
    assert "OriginalFilename" in text


def test_app_icon_files_exist() -> None:
    folder = Path("src/stream_heartbeat/assets")
    assert (folder / "app_icon.png").is_file()
    assert (folder / "app_icon.ico").is_file()


def test_app_icon_is_a_red_heart() -> None:
    from PySide6.QtGui import QColor, QImage

    img = QImage("src/stream_heartbeat/assets/app_icon.png")
    assert not img.isNull()
    pixel = QColor(img.pixel(img.width() // 2, int(img.height() * 0.55)))
    assert pixel.red() > 80
    assert pixel.red() > pixel.blue()
    assert pixel.red() > pixel.green()
