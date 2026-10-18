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
; QoderCNIDEPortable  Custom.nsh   （UTF-8 无 BOM —— 本文件必须无 BOM 才能被 makensis 正常解析）
; ===========================================================================
;   安装监控日志：QoderCNIDEPortable\_制作素材（安装.reg / 文件与注册表日志）
;   安装位置、用户目录、协议关联均按日志逐项确定
;
; [踩坑清单，勿重复 —— 详见 docs\踩坑记录.md]
;  1. 钩子宏名必须是 Custom.nsh_<阶段>（Segments.nsh L54），
;     写成 CustomPreExec / CustomInit 会**静默失效**；
;  2. Custom.nsh 必须放在 App\AppInfo\Launcher\ 且名字恰为 Custom.nsh；
;  3. $INSTDIR 在 PAL 启动器中未初始化（展开为空），路径一律 $EXEDIR 运行时拼接；
;  4. 拆 Junction 只能 rmdir（不带 /s），带 /s 会删穿联接误删 Data 数据；
;  5. 绝不联接共享/他软件目录（会误伤宿主正在运行的软件）。
; ===========================================================================

!include "LogicLib.nsh"


; --- 判断路径是否为 reparse point（junction/symlink） --------------------
!macro NP_IsJunction _PATH _RESULT
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
!define NP_IsJunction `!insertmacro NP_IsJunction`

; --- 建立 / 拆除 junction（幂等；宿主真实目录先合并回 Data 再移除） --------
!macro NP_JunctionCreate _HOST _TARGET
    ${If} ${FileExists} "${_HOST}"
        ${NP_IsJunction} "${_HOST}" $7
        ${If} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "${_HOST}"'
        ${Else}
            nsExec::ExecToLog 'cmd /c robocopy "${_HOST}" "${_TARGET}" /E /XO /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "${_HOST}"'
        ${EndIf}
    ${EndIf}
    CreateDirectory "${_TARGET}"
    nsExec::ExecToLog 'cmd /c mklink /J "${_HOST}" "${_TARGET}"'
!macroend
!define NP_JunctionCreate `!insertmacro NP_JunctionCreate`

!macro NP_JunctionRemove _HOST
    ${If} ${FileExists} "${_HOST}"
        ${NP_IsJunction} "${_HOST}" $7
        ${If} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "${_HOST}"'
        ${EndIf}
    ${EndIf}
!macroend
!define NP_JunctionRemove `!insertmacro NP_JunctionRemove`

; --- 结束便携目录内的后台残留进程（按路径限定，绝不用映像名全局杀） ------
Function KillResidual
    nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" kill "" "" "" "$EXEDIR\App"'
  Pop $0
  Pop $1
FunctionEnd

; --- 清理开机自启项（安装期写入的 Run 值，退出后不得残留） ----------------
Function DeleteRunKey
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Qoder CN IDE"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "QoderCNIDE"

FunctionEnd

; ===========================================================================
; PAL 钩子（宏名必须是 Custom.nsh_<阶段>）
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

  ClearErrors
  CreateDirectory "$DataDirectory\settings"
  CreateDirectory "$DataDirectory\settings\local"
  CreateDirectory "$DataDirectory\settings\Temp"
  CreateDirectory "$DataDirectory\settings\user"

  ; 环境变量双保险（对 getenv 组件生效；Junction 之外的补充）
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'APPDATA' '$DataDirectory\settings'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'LOCALAPPDATA' '$DataDirectory\settings\local'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'TEMP' '$DataDirectory\settings\Temp'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'TMP' '$DataDirectory\settings\Temp'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'USERPROFILE' '$DataDirectory\settings\user'

  Call DeleteRunKey

!macroend

!macro Custom.nsh_PostPrimary
  ${NP_WriteHelpers}
  Call KillResidual

  Call DeleteRunKey
!macroend

!macro Custom.nsh_Unload
  ${NP_WriteHelpers}
  Call KillResidual

  Call DeleteRunKey
!macroend
