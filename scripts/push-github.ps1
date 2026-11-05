<#
  把卿音推到 GitHub。
  用法：
    .\scripts\push-github.ps1 -Repo https://github.com/<你>/<仓库名>.git
  说明：
    1. 第一次会弹 GitHub 登录（Git Credential Manager），登录一次以后记住；
    2. 只推当前分支；不带上 work/output/models/logs/backups（已在 .gitignore）；
    3. 推送前会再跑一次敏感内容扫描，有命中直接中止。
#>
param(
  [Parameter(Mandatory = $true)][string]$Repo,
  [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"
$git = "C:\Program Files\Git\cmd\git.exe"
if (-not (Test-Path $git)) { throw "没找到 git：$git" }
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  Write-Host "== 1/4 敏感内容扫描 ==" -ForegroundColor Cyan
  $scan = & py -3 scripts/package.py --scan-only 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Host $scan; throw "扫描没通过，已中止（详见上面的命中项）" }
  Write-Host "  通过" -ForegroundColor Green

  Write-Host "== 2/4 设置远端 ==" -ForegroundColor Cyan
  & $git remote remove origin 2>$null
  & $git remote add origin $Repo
  & $git remote -v

  Write-Host "== 3/4 确认没把私人文件带上 ==" -ForegroundColor Cyan
  $bad = & $git ls-files | Where-Object { $_ -match "^(work|output|models|dist|logs|backups)/|configs/local\.yaml|decisions\.jsonl" }
  if ($bad) { $bad | ForEach-Object { Write-Host "  ⚠ $_" }; throw "有私人文件在索引里，先处理再推" }
  Write-Host "  干净" -ForegroundColor Green

  Write-Host "== 4/4 推送 ==" -ForegroundColor Cyan
  & $git push -u origin $Branch
  Write-Host "完成。" -ForegroundColor Green
} finally {
  Pop-Location
}
