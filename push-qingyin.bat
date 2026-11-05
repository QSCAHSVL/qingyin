@echo off
title Push qingyin to GitHub
cd /d "%~dp0"
set GIT="C:\Program Files\Git\cmd\git.exe"
set REPO=https://github.com/QSCAHSVL/qingyin.git

echo ==== 1) scan for sensitive content ====
py -3 scripts\package.py --scan-only
if errorlevel 1 goto fail

echo.
echo ==== 2) set remote ====
%GIT% remote remove origin 2>nul
%GIT% remote add origin %REPO%
%GIT% remote -v

echo.
echo ==== 3) push (HTTP/1.1, up to 5 tries) ====
set /a TRY=0
:retry
set /a TRY+=1
echo ---- attempt %TRY% ----
%GIT% -c http.version=HTTP/1.1 -c http.postBuffer=524288000 -c http.lowSpeedLimit=0 push -u origin main
if not errorlevel 1 goto ok
echo attempt %TRY% failed
if %TRY% GEQ 5 goto fail
timeout /t 5 /nobreak >nul
goto retry

:ok
echo.
echo ==== PUSH OK ====
%GIT% log --oneline -1
goto end

:fail
echo.
echo ==== FAILED (see messages above) ====

:end
echo.
pause