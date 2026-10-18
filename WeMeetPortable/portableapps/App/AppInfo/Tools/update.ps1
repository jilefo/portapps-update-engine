# update.ps1 —— 腾讯会议便携版更新逻辑（由包根目录 _更新.bat 调用）
# 流程：读当前版本 -> 获取官方新安装包 -> 7z 解压 -> 同步替换 App\WeMeet -> 更新版本号
# Data 目录全程不参与，用户数据零影响。

param([string]$PackagePath = "")
$ErrorActionPreference = "Stop"
$ToolsDir = $PSScriptRoot
$Root = Split-Path (Split-Path (Split-Path $ToolsDir -Parent) -Parent) -Parent
$AppDir = Join-Path $Root "App\WeMeet"
$AppInfoIni = Join-Path $Root "App\AppInfo\appinfo.ini"

function Get-CurrentVersion {
    $line = Select-String -Path $AppInfoIni -Pattern '^PackageVersion=' | Select-Object -First 1
    return ($line.Line -replace '^PackageVersion=', '').Trim()
}

function Find-7Zip {
    foreach ($p in @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe")) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command 7z.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

Write-Host "============================================"
Write-Host " 腾讯会议便携版 - 更新"
Write-Host "============================================"
$cur = Get-CurrentVersion
Write-Host "当前版本: $cur"
Write-Host ""

# ---- 1. 获取安装包 ----
if (-not $PackagePath) {
    Write-Host "即将打开官网下载页，请下载 Windows 版安装包。"
    Write-Host "下载开始后本脚本会自动检测下载目录中的新安装包（等待最多 10 分钟）..."
    Read-Host "按回车打开官网"
    Start-Process "https://meeting.tencent.com/download/"

    $dl = [Environment]::GetFolderPath("UserProfile") + "\Downloads"
    $before = Get-ChildItem $dl -Filter *.exe -File -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
    $deadline = (Get-Date).AddMinutes(10)
    $found = $null
    while ((Get-Date) -lt $deadline -and -not $found) {
        Start-Sleep -Seconds 3
        $new = Get-ChildItem $dl -Filter *.exe -File -ErrorAction SilentlyContinue |
            Where-Object { $before -notcontains $_.FullName -and
                ($_.Name -match "TencentMeeting|WeMeet|wemeet|meeting") -and
                -not (Test-Path ($_.FullName + ".crdownload")) -and
                -not (Test-Path ($_.FullName + ".part")) -and
                -not (Test-Path ($_.FullName + ".download")) }
        if ($new) {
            # 等文件写完（体积 2 秒不再变化）
            $f = $new[0].FullName
            $s1 = (Get-Item $f).Length; Start-Sleep -Seconds 2
            $s2 = (Get-Item $f).Length
            if ($s1 -eq $s2) { $found = $f }
        }
    }
    if (-not $found) {
        $input_path = Read-Host "未自动检测到下载文件，请手动输入安装包完整路径（或留空取消）"
        if (-not $input_path) { Write-Host "已取消。"; exit 1 }
        $found = $input_path.Trim('"')
    }
    $PackagePath = $found
}
if (-not (Test-Path $PackagePath)) { Write-Host "[X] 安装包不存在: $PackagePath"; exit 1 }
Write-Host "安装包: $PackagePath"

# ---- 2. 7z 解压 ----
$7z = Find-7Zip
if (-not $7z) { Write-Host "[X] 未找到 7-Zip，请安装后重试（https://7-zip.org）"; exit 1 }
$tmp = Join-Path $env:TEMP "WeMeetUpdate"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "解压安装包..."
& $7z x $PackagePath "-o$tmp" -y | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] 7z 解压失败（安装包可能非 NSIS 格式）。"
    Write-Host "    回退方案：手动运行安装包，自定义安装到临时目录后，把其中程序文件覆盖到 App\WeMeet。"
    exit 1
}

# ---- 3. 定位程序目录与版本号 ----
# 腾讯会议 NSIS 包实测结构（2026-10-15）：
#   根目录 = WeMeetApp.exe(引导器) + WeMeetApp_new.exe + $_数字_\(payload 全部程序文件)
#   + $PLUGINSDIR/$TEMP/$WINDIR（NSIS 脚本垃圾）
#   安装后的真实结构 = WeMeetApp.exe + <版本号>\(payload 内容) —— 需要组装。
# 普通包结构：某目录直接含 WeMeetApp.exe 与版本号子目录 —— 直接同步即可。
$stage = $null
$nsisJunk = @('$PLUGINSDIR', '$TEMP', '$WINDIR', '$APPDATA', '$LOCALAPPDATA', '$PROGRAMFILES', '$COMMONFILES', '$SYSDIR', '$DOCUMENTS')
$rootExe = Join-Path $tmp "WeMeetApp.exe"
$payload = Get-ChildItem $tmp -Directory -ErrorAction SilentlyContinue |
    Where-Object { $nsisJunk -notcontains $_.Name } | Select-Object -First 1

if ((Test-Path $rootExe) -and $payload -and ($payload.Name -like '$*')) {
    # NSIS 包：组装 引导器 + 版本号目录(payload)
    $newVer = (Get-Item $rootExe).VersionInfo.ProductVersion
    if (-not $newVer) { Write-Host "[X] 无法从 WeMeetApp.exe 读取版本号"; exit 1 }
    $stage = Join-Path $env:TEMP "WeMeetUpdate_stage"
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    New-Item $stage -ItemType Directory -Force | Out-Null
    Copy-Item $rootExe $stage -Force
    # WeMeetApp_new.exe 与 WeMeetApp.exe 哈希完全相同（安装包自更新预留副本），冗余，不复制
    & robocopy $payload.FullName (Join-Path $stage $newVer) /E /NFL /NDL /NJH /NJS | Out-Null
    $src = $stage
    Write-Host "NSIS 包，已组装程序目录（payload = $($payload.Name)）"
} else {
    # 普通包：递归定位 WeMeetApp.exe 所在目录
    $exe = Get-ChildItem $tmp -Recurse -Filter "WeMeetApp.exe" -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\$PLUGINSDIR' } | Select-Object -First 1
    if (-not $exe) { Write-Host "[X] 解压后未找到 WeMeetApp.exe，安装包结构可能已变化。"; exit 1 }
    $src = $exe.DirectoryName
    $verDir = Get-ChildItem $src -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
        Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
    $newVer = if ($verDir) { $verDir.Name } else { $exe.VersionInfo.ProductVersion }
}
Write-Host "程序目录: $src"
Write-Host "新版本: $newVer"
if ($newVer -eq $cur) {
    Write-Host "与当前版本相同，仍将继续替换以修复可能损坏的文件。"
}

# ---- 4. 同步替换 App\WeMeet（/MIR 镜像：旧版本目录会被清除，Data 不受影响） ----
Write-Host "替换程序文件（App\WeMeet）..."
& robocopy $src $AppDir /MIR /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -gt 7) { Write-Host "[X] 文件同步失败，robocopy 退出码 $LASTEXITCODE"; exit 1 }

# ---- 5. 更新 appinfo.ini 版本号 ----
(Get-Content $AppInfoIni -Encoding UTF8) `
    -replace '^PackageVersion=.*', "PackageVersion=$newVer" `
    -replace '^Version=.*', "Version=$newVer" |
    Set-Content $AppInfoIni -Encoding UTF8

# ---- 6. 清理并报告 ----
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
if ($stage) { Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue }
Write-Host ""
Write-Host "[OK] 更新完成: $cur -> $newVer"
Write-Host "Data 目录未做任何改动，用户数据与配置完整保留。"
