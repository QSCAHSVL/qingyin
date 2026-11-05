# 把当前项目打成绿色版目录（v1）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\portable.ps1
param(
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutDir) { $OutDir = Join-Path $root "dist\cover-pipeline-portable" }

Write-Host "[1/2] 清理旧目录"
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "[2/2] 复制文件到 $OutDir"
$exclude = @("work", "output", "dist", ".venv", "__pycache__", ".git", "_backups")
Get-ChildItem $root -File -Filter "decisions.jsonl" | ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
robocopy $root $OutDir /E /XD $exclude /NFL /NDL /NJH /NJS /NP | Out-Null
Get-ChildItem $OutDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$count = (Get-ChildItem $OutDir -Recurse -File | Measure-Object).Count
Write-Host ""
Write-Host "完成：$OutDir（$count 个文件）"
Write-Host "用法：双击 $OutDir\启动.bat"
Write-Host "提示：绿色版需要机器上有 Python 3.10+；想彻底免装，把便携版 Python 解压到 $OutDir\python\"