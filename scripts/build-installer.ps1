# 生成安装包（v2）：先打绿色版目录，再调 Inno Setup 编译
param(
  [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "[1/2] 生成绿色版目录"
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "portable.ps1")

if (-not $Iscc) {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
  )
  foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { $Iscc = $c; break } }
}

if (-not $Iscc -or -not (Test-Path $Iscc)) {
  Write-Host "[2/2] 没找到 Inno Setup 6。装一个再跑，或手动指定："
  Write-Host "      scripts\build-installer.ps1 -Iscc 'C:\path\to\ISCC.exe'"
  Write-Host "      下载：https://jrsoftware.org/isdl.php"
  Write-Host "      或者：winget install --id JRSoftware.InnoSetup -e"
  exit 1
}

Write-Host "[2/2] 编译安装包：$Iscc"
& $Iscc (Join-Path $root "installer\cover-pipeline.iss")
if ($LASTEXITCODE -ne 0) { Write-Host "编译失败，退出码 $LASTEXITCODE"; exit $LASTEXITCODE }
Write-Host "完成，安装包在 dist 下"