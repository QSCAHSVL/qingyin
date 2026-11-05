@echo off
setlocal
cd /d "%~dp0"
set "PY="
if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY (where py >nul 2>nul && set "PY=py -3")
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.10+ and run this file again.
  pause
  exit /b 1
)
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
%PY% "%~dp0scripts\first_run.py"
pause