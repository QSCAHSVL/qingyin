@echo off
setlocal
cd /d "%~dp0"
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo [ERROR] Python not found. Run setup-deps.bat first.
  pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',7801); exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  echo Port 7801 busy, opening browser instead...
  start "" http://127.0.0.1:7801/
  exit /b 0
)

%PY% -c "import webview" 2>nul || %PY% -m pip install --quiet pywebview
%PY% -m cover_pipeline.cli desktop --port 7801
pause