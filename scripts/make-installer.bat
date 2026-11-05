@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo Building installer (v2)...
powershell -ExecutionPolicy Bypass -File "%~dp0build-installer.ps1"
echo.
pause