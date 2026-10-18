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
  FileWrite $9 'if($$mode -eq "taskclean"){$\r$\n'
  FileWrite $9 'Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $$_.TaskName -like $$a1 -or $$_.TaskName -like $$a2 -and $$_.TaskPath -like $$a3 } | ForEach-Object { Unregister-ScheduledTask -TaskName $$_.TaskName -Confirm:$$false -ErrorAction SilentlyContinue }$\r$\n'
  FileWrite $9 'exit 0}$\r$\n'
  FileWrite $9 'if($$mode -eq "regclean"){$\r$\n'
  FileWrite $9 'Get-ChildItem -Path $$a1 -ErrorAction SilentlyContinue | Where-Object { $$_.PSChildName -like $$a2 } | ForEach-Object { Remove-Item -Path $$_.PSPath -Recurse -Force -ErrorAction SilentlyContinue }$\r$\n'
  FileWrite $9 'exit 0}$\r$\n'
  FileWrite $9 'exit 99$\r$\n'
  FileClose $9
!macroend
!define NP_WriteHelpers `!insertmacro NP_WriteHelpers`

; ===========================================================================
; FoxitPDF Portable  Custom.nsh  （UTF-8 无 BOM，实测可编译，勿加 BOM）
; ===========================================================================
; [2026-10-15 补齐：此前本包没有 Custom.nsh，收尾清理从未存在]
;
; 1) Junction：Foxit PDF Editor 的用户数据落点为
;    %APPDATA%\Foxit Software\Continuous\Foxit PDF Editor\
;    （FxWebView/EBWebView + FormFiller + preferences）。
;    实测：env 重定向后启动页模式零写入，但用户正常使用（改设置/开文档）
;    后必然写入。若该软件走 SHGetFolderPath/KnownFolder API（读注册表、
;    不看进程环境变量），env 重定向将失效 → 用 Junction 兜底：
;    启动前建 宿主%APPDATA%\Foxit Software -> Data\settings\Foxit Software，
;    首次启动时 robocopy 把宿主历史数据(27MB)合并进 Data 再接管，
;    退出时 rmdir（不带 /s）拆除。宿主零残留。
;    【安全性确认 2026-10-15】宿主无正式版 Foxit（Program Files 无目录、
;    无进程），合并历史数据不会影响其他在用软件。
;
; 2) 收尾清理：后台残留进程 / 开机自启 / 自动更新计划任务 / 文件关联
;    （钩子宏名必须是 Custom.nsh_<阶段>，否则静默失效——见踩坑 3.5）
; ===========================================================================

!include "LogicLib.nsh"

; ---------------------------------------------------------------------------
; Junction 宏组（复用自 TodayCNPortable，原理见其 Custom.nsh 文件头）
; ---------------------------------------------------------------------------

; --- 判断路径是否为 reparse point（junction/symlink） --------------------
!macro FX_IsJunction _PATH _RESULT
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
!define FX_IsJunction `!insertmacro FX_IsJunction`

; --- 建立 junction（启动时调用，幂等） -------------------------------------
!macro FX_JunctionCreate
    ${If} ${FileExists} "$APPDATA\Foxit Software"
        ${FX_IsJunction} "$APPDATA\Foxit Software" $7
        ${If} $7 == "1"
            ; 上次异常退出残留的 junction：只删链接，数据本就在 Data
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\Foxit Software"'
        ${Else}
            ; 宿主真实目录（历史数据/历次泄漏残留）：合并回 Data 再移除，不丢数据
            nsExec::ExecToLog 'cmd /c robocopy "$APPDATA\Foxit Software" "$DataDirectory\settings\Foxit Software" /E /XO /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "$APPDATA\Foxit Software"'
        ${EndIf}
    ${EndIf}
    CreateDirectory "$DataDirectory\settings\Foxit Software"
    nsExec::ExecToLog 'cmd /c mklink /J "$APPDATA\Foxit Software" "$DataDirectory\settings\Foxit Software"'
!macroend
!define FX_JunctionCreate `!insertmacro FX_JunctionCreate`

; --- 移除 junction（退出时调用，幂等；只删链接不删目标） -------------------
!macro FX_JunctionRemove
    ${If} ${FileExists} "$APPDATA\Foxit Software"
        ${FX_IsJunction} "$APPDATA\Foxit Software" $7
        ${If} $7 == "1"
            ; rmdir 不带 /s，防止删穿 junction 误删 Data 数据
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\Foxit Software"'
        ${EndIf}
    ${EndIf}
!macroend
!define FX_JunctionRemove `!insertmacro FX_JunctionRemove`

; ---------------------------------------------------------------------------
; 内部函数
; ---------------------------------------------------------------------------

; 结束便携目录内的后台残留进程（按可执行路径过滤，不误杀宿主正式版）
Function KillResidual
    nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" kill "" "" "" "$EXEDIR\App"'
  Pop $0
  Pop $1
FunctionEnd

; 清理开机自启项（兜底）
Function DeleteRunKey
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Foxit PDF Editor"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "FoxitPDFEditor"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Foxit PDF Editor Portable"
FunctionEnd

; 清理自动更新计划任务（Foxit 更新任务名均含 Foxit 前缀）
Function DeleteUpdateTask
  ${NP_TaskClean} '($$_.TaskName -like "Foxit*") -and ($$_.TaskName -like "*Update*" -or $$_.TaskName -like "*Upgrade*")'
  Pop $0
  Pop $1
FunctionEnd

; 清理文件关联（Foxit 会注册 HKCU\Classes\FoxitPDFEditor.* 等大量键）
Function DeleteFileAssoc
      nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" regclean "HKCU:\Software\Classes" "FoxitPDFEditor*" "" ""'
  Pop $0
  Pop $1
FunctionEnd

; ===========================================================================
; PAL 钩子（宏名必须是 Custom.nsh_<阶段>，否则静默失效）
; ===========================================================================

; 主程序启动前
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
  Call KillResidual
  Call DeleteRunKey
  Call DeleteUpdateTask
  ; 关键：建 junction，Foxit 写宿主 %APPDATA%\Foxit Software 实际落 Data
  ; $APPDATA 为 NSIS 常量（SHGetFolderPath 读注册表）= 宿主真实路径
  ${FX_JunctionCreate}
!macroend

; 主程序退出后
!macro Custom.nsh_PostPrimary
  ${NP_WriteHelpers}
  Call KillResidual
  ${FX_JunctionRemove}
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend

; 卸载前
!macro Custom.nsh_Unload
  ${NP_WriteHelpers}
  Call KillResidual
  ${FX_JunctionRemove}
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend
