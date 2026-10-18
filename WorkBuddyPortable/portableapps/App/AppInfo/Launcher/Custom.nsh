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

; WorkBuddy Portable  Custom.nsh

; ===========================================================================

; 依据：WorkBuddy 日志 - 注册表项目.txt / WorkBuddy 日志 - 文件和文件夹.txt

; 仅处理三类问题：开机自启 / 计划任务 / 后台进程

; ===========================================================================



!include "WinVer.nsh"

!include "LogicLib.nsh"



; ---------------------------------------------------------------------------

; 结束便携目录内的后台残留进程

; ---------------------------------------------------------------------------

; 【关键安全设计】按「可执行路径」过滤，只结束本便携目录内的进程。

;   若用户同时装有正式版，绝不能误杀。

Function KillResidual

    nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" kill "" "" "" "$EXEDIR\App"'

  Pop $0

  Pop $1

FunctionEnd



; ---------------------------------------------------------------------------

; 清理开机自启项

; ---------------------------------------------------------------------------

; 监控日志中该软件未写 Run 键（匹配 0 条），此处为兜底双保险。

Function DeleteRunKey

  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WorkBuddy"

  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "WorkBuddy Portable"

FunctionEnd



; ---------------------------------------------------------------------------

; 清理自动更新计划任务

; ---------------------------------------------------------------------------

; Cursor 日志中有一条 TaskCache\Tasks\{9257AF6E-...} 残留。

; 任务名可能内嵌用户名/SID，故按前缀通配删除。

Function DeleteUpdateTask

      nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" taskclean "WorkBuddy*" "*Update*" "*WorkBuddy*" ""'

  Pop $0

  Pop $1

FunctionEnd



; ---------------------------------------------------------------------------

; 清理语言扩展名关联

; ---------------------------------------------------------------------------

; 该架构会注册上千条 HKCU\Classes\<软件名>.<扩展名> 关联。

; 逐条清理代价过高，此处按前缀批量删除。

Function DeleteFileAssoc

      nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" regclean "HKCU:\Software\Classes" "WorkBuddy.*" "" ""'

  Pop $0

  Pop $1

FunctionEnd



; ===========================================================================

; PAL 钩子

; ===========================================================================

; ===========================================================================
; PAL 钩子（宏名必须是 Custom.nsh_<阶段>，旧名静默失效——踩坑 3.5）
; ===========================================================================

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
  Call DeleteRunKey
  Call DeleteUpdateTask
  ; 启动前先清残留，防止上次异常关闭留下的进程占用端口
  Call KillResidual
  ; 每次启动都重新确认自启与更新任务未复活
  Call DeleteRunKey
  Call DeleteUpdateTask
!macroend

!macro Custom.nsh_PostPrimary
  ${NP_WriteHelpers}
  Call KillResidual
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend

!macro Custom.nsh_Unload
  ${NP_WriteHelpers}
  Call KillResidual
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend
