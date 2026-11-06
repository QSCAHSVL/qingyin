# 一条命令出两个包：绿色版 zip + Inno 安装包
#
#   scripts\build-installer.ps1                  # 全自动
#   scripts\build-installer.ps1 -SkipInstaller   # 只出绿色版 zip
#   scripts\build-installer.ps1 -Iscc "C:\path\to\ISCC.exe"
#
# 注意：绿色版目录必须由 scripts\package.py 生成（它同时做隐私扫描）。
# 以前这里调的是 portable.ps1，它吐出的是 dist\cover-pipeline-portable，
# 而 installer\cover-pipeline.iss 的源目录已经跟版本号联动（dist\卿音-<版本>-portable），
# 两边对不上就会编译失败——2026-11-06 踩过一次，已修。
param(
  [string]$Iscc = "",
  [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$py = "py"

# 版本号只有一处手改：src\cover_pipeline\__init__.py
$initPy = Get-Content (Join-Path $root "src\cover_pipeline\__init__.py") -Raw -Encoding UTF8
$version = [regex]::Match($initPy, '__version__\s*=\s*"([^"]+)"').Groups[1].Value
if (-not $version) { throw "读不到版本号" }
$zip = Join-Path $root "dist\卿音-$version-portable.zip"
$dir = Join-Path $root "dist\卿音-$version-portable"
Write-Host "版本 $version"

Write-Host "[1/3] 同步版本号（pyproject / iss）"
& $py -3 (Join-Path $root "scripts\sync_version.py")
if ($LASTEXITCODE -ne 0) { throw "sync_version 失败" }

Write-Host "[2/3] 打绿色版（含隐私扫描）→ $zip"
& $py -3 (Join-Path $root "scripts\package.py")
if ($LASTEXITCODE -ne 0) { throw "打包失败（扫描命中会中止，看上面的输出）" }
if (-not (Test-Path $zip)) { throw "没生成 $zip" }

if ($SkipInstaller) {
  Write-Host "完成（-SkipInstaller，只出了绿色版）"
  exit 0
}

Write-Host "[3/3] 解出目录 + 编译安装包"
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $dir -Force

if (-not $Iscc) {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
  )
  foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { $Iscc = $c; break } }
}
if (-not $Iscc -or -not (Test-Path $Iscc)) {
  Write-Host "没找到 Inno Setup 6。装一个再跑，或手动指定："
  Write-Host "      scripts\build-installer.ps1 -Iscc 'C:\path\to\ISCC.exe'"
  Write-Host "      下载：https://jrsoftware.org/isdl.php"
  Write-Host "      或者：winget install --id JRSoftware.InnoSetup -e"
  Write-Host "（绿色版 zip 已经好了，只是没装安装包）"
  exit 1
}

& $Iscc (Join-Path $root "installer\cover-pipeline.iss")
if ($LASTEXITCODE -ne 0) { Write-Host "编译失败，退出码 $LASTEXITCODE"; exit $LASTEXITCODE }

Write-Host ""
Write-Host "完成："
Get-ChildItem (Join-Path $root "dist") -Filter "卿音-$version-*" -File | ForEach-Object {
  Write-Host ("  {0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB))
}
