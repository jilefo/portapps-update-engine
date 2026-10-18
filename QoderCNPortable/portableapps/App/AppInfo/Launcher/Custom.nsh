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
; Qoder CN Portable  Custom.nsh  （UTF-8 无 BOM，实测可编译，勿加 BOM）
; ===========================================================================
; [2026-10-15 重写：修复"打不开"(WINDOWS_LAUNCHER_STATE_MISSING) + 数据落盘]
;
; 1) 启动失败根因（app.asar 内 aBt 函数，installType==="user" 路径）：
;    Qoder CN.exe 启动时读 %LOCALAPPDATA%\Qoder CN\Qoder CN Launcher\state.ini
;    （launcher state 机制，schemaVersion=3）。文件缺失 → ENOENT →
;    WINDOWS_LAUNCHER_STATE_MISSING → "Startup selection failed" → Error 弹窗退出。
;    正常安装由官方安装器写入该文件；便携包需自行预置。
;    → PreExecPrimary 动态写 state.ini：installDir 用 $EXEDIR 生成（包可移动）。
;      注意不能用 NSIS 的 $LOCALAPPDATA 常量（读注册表 Shell Folders，不受
;      PAL 环境重定向影响）——直接用 $EXEDIR 拼包内落点，确保写进 Data。
;    ★ 严禁把 resources\install-type.json 改成 "system"：会触发 system 级
;      launcher/更新机制（实测下载 231MB 系统安装包并接管启动）。
;
; 2) 数据落盘：
;    - userData：launcher.ini 的 --user-data-dir 已指向 Data\settings ✓
;    - USERPROFILE 侧：~\.qoder-cn（实测 638MB，agent/模型/扩展缓存）
;      用 Junction 收纳：启动前建 宿主链接 -> Data\settings\.qoder-cn，
;      退出时 rmdir（不带 /s）拆除。宿主零残留。
;    ★ launcher.ini 禁止重定向 USERPROFILE（Electron 主进程
;      "Failed to get 'appData' path" 崩溃，见 docs\踩坑记录.md 4.7）。
; ===========================================================================

!include "LogicLib.nsh"

; ---------------------------------------------------------------------------
; Junction 宏组（复用自 TodayCNPortable，原理见其 Custom.nsh 文件头）
; ---------------------------------------------------------------------------

; --- 判断路径是否为 reparse point（junction/symlink） --------------------
!macro QD_IsJunction _PATH _RESULT
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
!define QD_IsJunction `!insertmacro QD_IsJunction`

; --- 建立 junction（启动时调用，幂等） -------------------------------------
!macro QD_JunctionCreate
    ${If} ${FileExists} "$PROFILE\.qoder-cn"
        ${QD_IsJunction} "$PROFILE\.qoder-cn" $7
        ${If} $7 == "1"
            ; 上次异常退出残留的 junction：只删链接，数据本就在 Data
            nsExec::ExecToLog 'cmd /c rmdir "$PROFILE\.qoder-cn"'
        ${Else}
            ; 宿主真实目录（历史数据/历次泄漏残留）：合并回 Data 再移除，不丢数据
            nsExec::ExecToLog 'cmd /c robocopy "$PROFILE\.qoder-cn" "$DataDirectory\settings\.qoder-cn" /E /XO /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "$PROFILE\.qoder-cn"'
        ${EndIf}
    ${EndIf}
    CreateDirectory "$DataDirectory\settings\.qoder-cn"
    nsExec::ExecToLog 'cmd /c mklink /J "$PROFILE\.qoder-cn" "$DataDirectory\settings\.qoder-cn"'
!macroend
!define QD_JunctionCreate `!insertmacro QD_JunctionCreate`

; --- 移除 junction（退出时调用，幂等；只删链接不删目标） -------------------
!macro QD_JunctionRemove
    ${If} ${FileExists} "$PROFILE\.qoder-cn"
        ${QD_IsJunction} "$PROFILE\.qoder-cn" $7
        ${If} $7 == "1"
            ; rmdir 不带 /s，防止删穿 junction 误删 Data 数据
            nsExec::ExecToLog 'cmd /c rmdir "$PROFILE\.qoder-cn"'
        ${EndIf}
    ${EndIf}
!macroend
!define QD_JunctionRemove `!insertmacro QD_JunctionRemove`

; ---------------------------------------------------------------------------
; [2026-10-16 补] Electron userData 落点逃逸收纳
; 实测（data-persist 测试）：Qoder CN 主进程内部代码用
; app.getPath('appData') + '\com.qodercn.app.stable' 拼路径，而 Electron 的
; appData 走 SHGetKnownFolderPath(RoamingAppData) 读注册表 Shell Folders，
; 完全无视进程环境变量 APPDATA 重定向 → 63 文件/8.3MB 泄漏到宿主。
; 环境变量方案对 KnownFolder API 无效（踩坑 5.2 同理），必须 Junction。
; $APPDATA 常量读注册表 = 宿主真实路径，正好用作链接端。
; ---------------------------------------------------------------------------
!macro QD2_JunctionCreate
    ${If} ${FileExists} "$APPDATA\com.qodercn.app.stable"
        ${QD_IsJunction} "$APPDATA\com.qodercn.app.stable" $7
        ${If} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\com.qodercn.app.stable"'
        ${Else}
            nsExec::ExecToLog 'cmd /c robocopy "$APPDATA\com.qodercn.app.stable" "$DataDirectory\settings\com.qodercn.app.stable" /E /XO /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "$APPDATA\com.qodercn.app.stable"'
        ${EndIf}
    ${EndIf}
    CreateDirectory "$DataDirectory\settings\com.qodercn.app.stable"
    nsExec::ExecToLog 'cmd /c mklink /J "$APPDATA\com.qodercn.app.stable" "$DataDirectory\settings\com.qodercn.app.stable"'
!macroend
!define QD2_JunctionCreate `!insertmacro QD2_JunctionCreate`

!macro QD2_JunctionRemove
    ${If} ${FileExists} "$APPDATA\com.qodercn.app.stable"
        ${QD_IsJunction} "$APPDATA\com.qodercn.app.stable" $7
        ${If} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\com.qodercn.app.stable"'
        ${EndIf}
    ${EndIf}
!macroend
!define QD2_JunctionRemove `!insertmacro QD2_JunctionRemove`

; ---------------------------------------------------------------------------
; 预置 launcher state.ini（主程序启动前必须存在，否则报
; WINDOWS_LAUNCHER_STATE_MISSING 拒绝启动）
; 字段模板取自实测抓取的 state.system.ini（schemaVersion=3）。
; installDir 每次启动用 $EXEDIR 动态生成，包移动到任意路径均有效。
; 落点固定用 $EXEDIR 拼接（$LOCALAPPDATA 常量读注册表不可靠，见文件头）。
; ---------------------------------------------------------------------------
Function WriteLauncherState
  CreateDirectory "$EXEDIR\Data\settings\local\Qoder CN\Qoder CN Launcher"
  FileOpen $0 "$EXEDIR\Data\settings\local\Qoder CN\Qoder CN Launcher\state.ini" w
  ${If} $0 != ""
    FileWrite $0 "[launcher]$\r$\n"
    FileWrite $0 "schemaVersion=3$\r$\n"
    FileWrite $0 "status=healthy$\r$\n"
    FileWrite $0 "installDir=$EXEDIR\App\Qoder CN$\r$\n"
    FileWrite $0 "appExecutable=Qoder CN.exe$\r$\n"
    FileWrite $0 "targetVersion=0.4.4$\r$\n"
    FileWrite $0 "updatedAt=2026-01-01T00:00:00.000Z$\r$\n"
    FileClose $0
  ${EndIf}
FunctionEnd

; ---------------------------------------------------------------------------
; 内部函数
; ---------------------------------------------------------------------------

; 结束便携目录内的后台残留进程（按可执行路径过滤，不误杀宿主正式版）
Function KillResidual
    nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" kill "" "" "" "$EXEDIR\App"'
  Pop $0
  Pop $1
FunctionEnd

; 清理开机自启项（监控日志中该软件未写 Run 键，此处为兜底）
Function DeleteRunKey
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Qoder CN"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Qoder CN Portable"
FunctionEnd

; 清理自动更新计划任务（按前缀通配；便携版禁用官方更新链）
Function DeleteUpdateTask
  ${NP_TaskClean} '($$_.TaskName -like "Qoder CN*") -or (($$_.TaskPath -like "*Qoder CN*") -and ($$_.TaskName -like "*Update*"))'
  Pop $0
  Pop $1
FunctionEnd

; 清理文件关联（该架构会注册大量 HKCU\Classes\<软件名>.<扩展名>）
Function DeleteFileAssoc
      nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" regclean "HKCU:\Software\Classes" "Qoder CN.*" "" ""'
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
  ; 关键 1：预置 launcher state.ini（缺失即拒绝启动）
  Call WriteLauncherState
  ; 关键 2：junction 收纳 ~\.qoder-cn（638MB 落点）
  ${QD_JunctionCreate}
  ; 关键 3：junction 收纳 %APPDATA%\com.qodercn.app.stable（Electron userData 逃逸）
  ${QD2_JunctionCreate}
!macroend

; 主程序退出后
!macro Custom.nsh_PostPrimary
  ${NP_WriteHelpers}
  Call KillResidual
  ${QD_JunctionRemove}
  ${QD2_JunctionRemove}
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend

; 卸载前
!macro Custom.nsh_Unload
  ${NP_WriteHelpers}
  Call KillResidual
  ${QD_JunctionRemove}
  ${QD2_JunctionRemove}
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend
