@echo off
setlocal
cd /d "%~dp0"
set "PY="
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo [ERROR] Python not found. Run setup-deps.bat first, or install Python 3.10+.
  pause
  exit /b 1
)
set "PYTHONPATH=%~dp0src"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

rem 已经开着一个界面就直接打开浏览器，不重复起服务
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('127.0.0.1',7801); exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  echo Already running, opening browser...
  start "" http://127.0.0.1:7801/
  exit /b 0
)

%PY% -c "import yaml" 2>nul || %PY% -m pip install --quiet pyyaml
%PY% -m cover_pipeline.cli serve --port 7801
pause