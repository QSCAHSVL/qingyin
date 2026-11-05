# 一键安装（Windows / PowerShell）
# 用法：在项目根目录执行  powershell -ExecutionPolicy Bypass -File scripts/install.ps1

$ErrorActionPreference = "Stop"
Write-Host "== cover-pipeline 安装 ==" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "没找到 python，请先装 Python 3.10+ 并勾选 Add to PATH" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "创建虚拟环境 .venv ..."
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -e .

Write-Host ""
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "ffmpeg 已就绪" -ForegroundColor Green
} else {
    Write-Host "还缺 ffmpeg，请执行：winget install Gyan.FFmpeg，然后重开终端" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "安装完成。下一步：" -ForegroundColor Cyan
Write-Host "  .venv\Scripts\activate"
Write-Host "  cover doctor"