# package-paf.ps1 —— 通用版：生成压缩包/SHA256SUMS，尝试生成 .paf.exe
param(
    [string]$Pkg,
    [switch]$SkipChecksum
)
$ErrorActionPreference = "Stop"
# 仓库根 = _shared/scripts 的上两级
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Pkg) {
    $leaf = Split-Path -Leaf (Get-Location).Path
    if ($leaf -like "*Portable") { $Pkg = $leaf }
}
if (-not $Pkg) { Write-Error "请用 -Pkg 指定包名，或在包目录下运行"; exit 1 }
$repo = Join-Path $root $Pkg
if (-not (Test-Path $repo)) { Write-Error "包目录不存在: $repo"; exit 1 }

Write-Host "[1/2] 打包压缩包 ($Pkg)"
& python "$PSScriptRoot\package-paf.py" $Pkg
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $SkipChecksum) { Write-Host "[2/2] 校验和: dist\SHA256SUMS" }

$installer = Get-Command "PortableApps.comInstaller.exe" -ErrorAction SilentlyContinue
if (-not $installer) {
    $cand = @(
        "$root\_shared\toolchain\PortableApps.comInstaller\App\PortableApps.comInstaller.exe",
        "C:\Program Files\PortableApps.com Installer\PortableApps.comInstaller.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($cand) { $installer = @{ Source = $cand } }
}
if (-not $installer) {
    Write-Warning "未找到 PortableApps.com Installer，跳过 .paf.exe。"
    exit 0
}
Write-Host "使用 Installer: $($installer.Source)"
& $installer.Source "/SILENT" "/DESTINATION=$repo\dist"
exit $LASTEXITCODE
