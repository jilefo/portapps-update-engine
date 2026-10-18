; --- 计划任务清理宏（参数化 Where 条件，运行时生成 ps1 + -File 执行） -----
!macro NP_TaskClean _EXPR
  FileOpen $9 "$DataDirectory\settings\.np-taskclean.ps1" w
  FileWrite $9 'Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { '
  FileWrite $9 '${_EXPR}'
  FileWrite $9 ' } | ForEach-Object { Unregister-ScheduledTask -TaskName $$_.TaskName -Confirm:$$false -ErrorAction SilentlyContinue }$\r$\n'
  FileClose $9
  nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-taskclean.ps1"'
!macroend
!define NP_TaskClean `!insertmacro NP_TaskClean`

; --- helpers ps1：junction 探针 / 包内进程计数 / 残留清理 / Run 值清理 ----
; [2026-10-17 修复] 原实现用 nsExec 内联 powershell -Command，踩两重坑：
;   ① NSIS 把内联脚本里的 $l/$t/$p/$own 等当未声明变量吞掉（要 $$ 转义）；
;   ② PowerShell 5.1 -Command 的引号规则与预期不符（'' / "" 均 ParserError），
;   且原样还有 ^|（PS 不认 ^ 转义）。改为 FileWrite 生成 ps1 + -File 传参，
;   彻底绕开内联引号/转义地狱（probe_file_test 实测三段语义全对）。
!macro NP_WriteHelpers
  FileOpen $9 "$DataDirectory\settings\.np-helpers.ps1" w
  FileWrite $9 'param($$mode,$$a1,$$a2,$$a3,$$a4)$\r$\n'
  FileWrite $9 '$$ErrorActionPreference="SilentlyContinue"$\r$\n'
  FileWrite $9 'if($$mode -eq "probe"){$\r$\n'
  FileWrite $9 '$$p=".junc-probe-"+$$a3$\r$\n'
  FileWrite $9 '$$tp=Join-Path $$a2 $$p$\r$\n'
  FileWrite $9 'Set-Content -LiteralPath $$tp -Value "x" -Encoding ASCII$\r$\n'
  FileWrite $9 'if(Test-Path -LiteralPath (Join-Path $$a1 $$p)){Remove-Item -LiteralPath $$tp -Force;exit 0}$\r$\n'
  FileWrite $9 'Remove-Item -LiteralPath $$tp -Force$\r$\n'
  FileWrite $9 '$$li=Get-Item -LiteralPath $$a1 -Force$\r$\n'
  FileWrite $9 '$$lt=$$li.LinkTarget$\r$\n'
  FileWrite $9 'if(-not $$lt){$$lt=($$li.Target | Select-Object -First 1)}$\r$\n'
  FileWrite $9 'if(-not $$lt){exit 2}$\r$\n'
  FileWrite $9 'if(-not(Test-Path -LiteralPath $$lt)){exit 3}$\r$\n'
  FileWrite $9 'exit 1}$\r$\n'
  FileWrite $9 'if($$mode -eq "count"){$\r$\n'
  FileWrite $9 '$$r=(Resolve-Path -LiteralPath $$a4).Path$\r$\n'
  FileWrite $9 '$$n=(Get-Process -ErrorAction SilentlyContinue | Where-Object {$$_.Path -and $$_.Path.StartsWith($$r,[System.StringComparison]::OrdinalIgnoreCase)}).Count$\r$\n'
  FileWrite $9 'Write-Output $$n$\r$\n'
  FileWrite $9 'exit 0}$\r$\n'
  FileWrite $9 'if($$mode -eq "kill"){$\r$\n'
  FileWrite $9 '$$r=(Resolve-Path -LiteralPath $$a4).Path$\r$\n'
  FileWrite $9 'Get-Process -ErrorAction SilentlyContinue | Where-Object {$$_.Path -and $$_.Path.StartsWith($$r,[System.StringComparison]::OrdinalIgnoreCase)} | ForEach-Object {try{Stop-Process -Id $$_.Id -Force -ErrorAction SilentlyContinue}catch{}}$\r$\n'
  FileWrite $9 'exit 0}$\r$\n'
  FileWrite $9 'if($$mode -eq "runclean"){$\r$\n'
  FileWrite $9 '$$k="HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"$\r$\n'
  FileWrite $9 '$$v=(Get-ItemProperty -Path $$k -Name $$a4 -ErrorAction SilentlyContinue).$$a4$\r$\n'
  FileWrite $9 'if($$v -and $$v.StartsWith($$a3,[System.StringComparison]::OrdinalIgnoreCase)){Remove-ItemProperty -Path $$k -Name $$a4 -Force}$\r$\n'
  FileWrite $9 'exit 0}$\r$\n'
  FileWrite $9 'exit 99$\r$\n'
  FileClose $9
!macroend
!define NP_WriteHelpers `!insertmacro NP_WriteHelpers`

; ===========================================================================
; ZoomPortable 7.2.0  Custom.nsh  （UTF-8 无 BOM，实测可编译，勿加 BOM）
; ===========================================================================
; [2026-10-15 终案 —— 直启 + Junction]
;   根因链（实测 + 安装日志确证）：
;   1. Zoom_launcher 是引导下载器：读 HKCU\Software\ZoomUMX\InstallLocation
;      拼 \Zoom.exe 找程序，找不到 -> 从 zoom.us 全量下载 268MB；
;      即使找到，后台仍下载更新包 41.8MB
;      （Zoom.msi 36.67 + vcredist 4.02 + Installer 1.12）。
;      下载是 launcher 自身行为，删 zUpdater.exe 不足以阻断（方案A实测证伪）。
;   2. bin\Zoom.exe 可独立运行，直启 90s 实测零下载。
;   3. 但 Zoom.exe 用 SHGetFolderPath/KnownFolder API 写宿主 %APPDATA%\Zoom，
;      [Environment] env 重定向对其无效（直启实测泄漏 28.84MB 到宿主）。
;   终案：
;   A. launcher.ini ProgramExecutable=Zoom\bin\Zoom.exe —— PAL 直接拉起
;      真程序，Zoom_launcher 永不执行，下载链从源头消失。
;   B. Junction：启动前建 宿主%APPDATA%\Zoom -> Data 目录联接，
;      退出时 rmdir（不带 /s）拆除。数据物理上全程只在 Data，宿主零残留。
;      （宏组复用自 WeMeetPortable Custom.nsh，原理见其文件头）
;
; [本包特有教训]
;   - $INSTDIR 在 PAL 启动器中未初始化（展开为空），路径一律用 $EXEDIR 拼接。
;   - !define 含 $EXEDIR 会在编译期展开成字面量，不可靠；运行时直接用 $EXEDIR。
;   - 钩子宏名必须是 Custom.nsh_<阶段> 格式（Segments.nsh L54）。
; ===========================================================================

!include "LogicLib.nsh"

; ---------------------------------------------------------------------------
; Junction 宏组（复用自 WeMeetPortable，详见其 Custom.nsh 文件头说明）
; ---------------------------------------------------------------------------

; --- 判断路径是否为 reparse point（junction/symlink） --------------------
;   用法：${ZM_IsJunction} "路径" $结果变量   ; "1"=junction  "0"=否/不存在
!macro ZM_IsJunction _PATH _RESULT
    StrCpy $8 "${_PATH}"
    System::Call 'kernel32::GetFileAttributesW(t r8) i .r9'
    ${If} $9 == -1
        StrCpy ${_RESULT} "0"
    ${Else}
        IntOp $9 $9 & 0x400
        ${If} $9 == 0
            StrCpy ${_RESULT} "0"
        ${Else}
            StrCpy ${_RESULT} "1"
        ${EndIf}
    ${EndIf}
!macroend
!define ZM_IsJunction `!insertmacro ZM_IsJunction`

; --- 建立 junction（启动时调用，幂等） -------------------------------------
!macro ZM_JunctionCreate
    ; 宿主路径已存在：区分残留 junction 与真实目录
    ${If} ${FileExists} "$APPDATA\Zoom"
        ${ZM_IsJunction} "$APPDATA\Zoom" $7
        ${If} $7 == "1"
            ; 上次异常退出残留的 junction：只删链接，数据本就在 Data
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\Zoom"'
        ${Else}
            ; 宿主真实目录（正式版数据或历次泄漏残留）：合并回 Data 再移除，不丢数据
            nsExec::ExecToLog 'cmd /c robocopy "$APPDATA\Zoom" "$DataDirectory\settings\user\AppData\Roaming\Zoom" /E /XO /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "$APPDATA\Zoom"'
        ${EndIf}
    ${EndIf}
    ; 确保 Data 侧目标存在并建立 junction
    ; $APPDATA 为 NSIS 常量（SHGetFolderPath 读注册表）= 宿主真实路径
    CreateDirectory "$DataDirectory\settings\user\AppData\Roaming\Zoom"
    nsExec::ExecToLog 'cmd /c mklink /J "$APPDATA\Zoom" "$DataDirectory\settings\user\AppData\Roaming\Zoom"'
!macroend
!define ZM_JunctionCreate `!insertmacro ZM_JunctionCreate`

; --- 移除 junction（退出时调用，幂等；只删链接不删目标） -------------------
!macro ZM_JunctionRemove
    ${If} ${FileExists} "$APPDATA\Zoom"
        ${ZM_IsJunction} "$APPDATA\Zoom" $7
        ${If} $7 == "1"
            ; rmdir 不带 /s，防止删穿 junction 误删 Data 数据
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\Zoom"'
        ${EndIf}
    ${EndIf}
!macroend
!define ZM_JunctionRemove `!insertmacro ZM_JunctionRemove`

; ---------------------------------------------------------------------------
; 内部函数：删除 Zoom 自动更新计划任务
; ---------------------------------------------------------------------------
; 任务名 ZoomUpdateTaskUser-<当前用户SID>，逐机器不同，用前缀通配删除。
Function ZoomDeleteUpdateTask
  ${NP_TaskClean} '$$_.TaskName -like "ZoomUpdateTaskUser*"'
  Pop $0
  Pop $1
FunctionEnd

; ---------------------------------------------------------------------------
; 内部函数：结束便携目录内的后台残留进程
; ---------------------------------------------------------------------------
; 只结束「可执行路径位于本便携 App\Zoom 内」的进程，避免误杀宿主正式版。
; 注意：$INSTDIR 在 PAL 中未初始化，必须用 $EXEDIR（= 包根）。
Function ZoomKillResidual
    nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" kill "" "" "" "$EXEDIR\App"'
  Pop $0
  Pop $1
FunctionEnd

; ---------------------------------------------------------------------------
; 内部函数：清理自启项（双保险）
; ---------------------------------------------------------------------------
Function ZoomDeleteRunKey
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Zoom"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Zoom Workplace"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ZoomLauncher"
FunctionEnd

; ---------------------------------------------------------------------------
; 内部函数：删除 zUpdater.exe（方案A，幂等）
; ---------------------------------------------------------------------------
; 下载主犯是 launcher 而非 zUpdater，但 zUpdater 仍会被拉起跑闲时检查，
; 一并删除（便携版固定版本，更新走项目统一 _更新.bat 流程）。
Function ZoomDisableUpdater
  Delete "$EXEDIR\App\Zoom\bin\zUpdater.exe"
FunctionEnd

; ===========================================================================
; PAL 钩子
; ===========================================================================

; 主程序启动前（PreExecPrimary：启动器即将拉起 ProgramExecutable 前）
; ===========================================================================
; ★ 自愈钩子：清掉「上次未正常关闭」残留，避免 PAL 拒绝启动程序
; ---------------------------------------------------------------------------
; PAL 源码实证（PortableApps.comLauncher.nsi）：Section 首行 Call Init，
; Function Init 第 1 段就是 Custom（即本宏，早于 Variables 段）；随后才判断
;   FileExists $DataDirectory\PortableApps.comLauncherRuntimeData-$BaseName.ini
; 命中则只 MessageBox $(LauncherCrashCleanup) 并直接走 Post/Unload，
; **压根不启动程序** —— 用户点完确定什么都没发生，不知情就是「一直打不开」。
; 该 ini 只在 PAL 正常收尾时删除（Segments\Core.nsh L113），任何强杀/断电/
; 崩溃都会留下它。ini 里没有开关能关掉这行为，只能抢在判断前清掉。
;
; 本钩子**仅当确认本包没有任何存活实例**时才删残留：
;   · 有存活实例 → 不动，完整保留 PAL 原有行为（不绕过"已在运行"保护，
;     也不破坏 junction 互斥，不会出现两个实例抢同一份 Data）；
;   · 无存活实例 → 残留必是陈旧的，删掉后本次启动即正常开始。
; 注意：Init 阶段 $DataDirectory 尚未赋值，一律用 $EXEDIR 拼路径。
; ===========================================================================
!macro NP_WriteHelpersInit
  CreateDirectory "$EXEDIR\Data\settings"
  FileOpen $9 "$EXEDIR\Data\settings\.np-helpers.ps1" w
  FileWrite $9 'param($$mode,$$a1,$$a2,$$a3,$$a4)$\r$\n'
  FileWrite $9 '$$ErrorActionPreference="SilentlyContinue"$\r$\n'
  FileWrite $9 'if($$mode -eq "alive"){$\r$\n'
  FileWrite $9 '$$r=(Resolve-Path -LiteralPath $$a4).Path$\r$\n'
  FileWrite $9 '$$self=[int]$$a1$\r$\n'
  FileWrite $9 '$$ps=Get-Process -ErrorAction SilentlyContinue | Where-Object {$$_.Path -and $$_.Path.StartsWith($$r,[System.StringComparison]::OrdinalIgnoreCase)}$\r$\n'
  FileWrite $9 'foreach($$p in $$ps){if($$p.Id -ne $$self){exit 1}}$\r$\n'
  FileWrite $9 'exit 0}$\r$\n'
  FileWrite $9 'exit 99$\r$\n'
  FileClose $9
!macroend
!define NP_WriteHelpersInit `!insertmacro NP_WriteHelpersInit`

!macro Custom.nsh_Init
  FindFirst $8 $9 "$EXEDIR\Data\PortableApps.comLauncherRuntimeData-*.ini"
  StrCmp $8 "" _np_init_done
  FindClose $8
  !insertmacro NP_WriteHelpersInit
  System::Call 'kernel32::GetCurrentProcessId() i.r6'
  nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$EXEDIR\Data\settings\.np-helpers.ps1" alive "$6" "" "" "$EXEDIR"'
  Pop $8
  Pop $9
  StrCmp $8 "0" 0 _np_init_done
  Delete "$EXEDIR\Data\PortableApps.comLauncherRuntimeData-*.ini"
  _np_init_done:
!macroend

!macro Custom.nsh_PreExecPrimary
  ${NP_WriteHelpers}
  ; 清残留，防止上次异常关闭留下的进程占用
  Call ZoomKillResidual
  ; 每次启动都重新确认更新任务未复活
  Call ZoomDeleteUpdateTask
  Call ZoomDeleteRunKey
  ; 删 zUpdater（幂等）
  Call ZoomDisableUpdater
  ; 关键：建 junction，Zoom.exe 写宿主 %APPDATA%\Zoom 实际落 Data
  ${ZM_JunctionCreate}
!macroend

; 主程序退出后（PostPrimary）
!macro Custom.nsh_PostPrimary
  ${NP_WriteHelpers}
  Call ZoomKillResidual
  ${ZM_JunctionRemove}
  Call ZoomDeleteUpdateTask
  Call ZoomDeleteRunKey
!macroend

; 卸载前
!macro Custom.nsh_Unload
  ${NP_WriteHelpers}
  Call ZoomKillResidual
  ${ZM_JunctionRemove}
  Call ZoomDeleteUpdateTask
  Call ZoomDeleteRunKey
!macroend
