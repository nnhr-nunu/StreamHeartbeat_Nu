@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m stream_heartbeat
  exit /b 0
)

if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" -m stream_heartbeat
  exit /b 0
)

echo venv がまだありません。
echo 一度だけ、README の開発者向け（pip install -e ".[dev]"）を実行してください。
pause
exit /b 1
