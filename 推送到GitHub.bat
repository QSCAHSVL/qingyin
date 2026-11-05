@echo off
chcp 65001 >nul
title 把卿音推到 GitHub
echo.
echo 需要你做的只有两步：
echo   1) 先在 GitHub 建一个空仓库（不要勾 README），名字随意，比如 qingyin
echo   2) 把仓库地址粘到这里，回车
echo.
set /p REPO=仓库地址（https://github.com/你的名字/qingyin.git）：
if "%REPO%"=="" goto :empty
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\push-github.ps1" -Repo "%REPO%"
echo.
pause
exit /b
:empty
echo 没填地址，退出了。
pause