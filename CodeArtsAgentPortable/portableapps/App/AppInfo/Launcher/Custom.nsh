; ===========================================================================
; Custom.nsh -- CodeArtsAgentPortable 便携版
; ===========================================================================
; 【作用】清除会让 Electron 应用退化成纯 Node 的环境变量。
;
; 【背景：本项目所有 Electron 包「启动即退」的真正原因】
;   症状：进程数 1，MainWindowTitle 恒空，无窗口。
;   真相：环境变量 ELECTRON_RUN_AS_NODE=1 被注入。该变量让 Electron
;         二进制跳过 GUI 初始化，只当 Node.js 跑。
;         它由开发工具链（WorkBuddy CLI，本身是 Electron 应用）注入，
;         并继承给所有子孙进程 —— 包括本启动器。
;   对照实验（Work\_analysis\probe_electron.py）：
;         A. 源目录原始 exe，继承脏环境 -> 1 进程 0 窗口（失败）
;         B. 源目录原始 exe，清掉该变量 -> 5 进程，窗口正常（成功）
;   已确认该变量只存在于**进程级**，User/Machine 级均未设置，
;   因此 SetEnvironmentVariable 清除后不影响系统。
;
; 【为什么需要这一步】
;   真实用户从 Explorer 双击时环境本来干净，这段是无害的空操作；
;   但自动化测试、CI、以及从开发工具内启动时是必需的。
;
; 【NSIS System::Call 语法要点（本项目踩过坑）】
;   SetEnvironmentVariable 的签名是
;       BOOL SetEnvironmentVariableW(LPCWSTR lpName, LPCWSTR lpValue)
;   删变量要传 **两个字符串参数**：名称传字符串，值传空字符串。
;   **不要**用 'kernel32::SetEnvironmentVariable(w,i)' —— 第二个参数类型是
;   w（宽字符串）不是 i（整数），传整数会调用失败或清除无效。
;   正确写法：
;       System::Call 'kernel32::SetEnvironmentVariableW(w, w)i' \
;         'ELECTRON_RUN_AS_NODE' '""'
;
; 【必须带 UTF-8 BOM】
;   附带的 makensis 是 v2.46.5-Unicode，无 BOM 的 UTF-8 文件若含非 ASCII
;   会解析中断，表现为 include 被静默跳过、全部钩子失效。
; ===========================================================================

!include "LogicLib.nsh"

Var ELLog

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

!macro Custom.nsh_.onInit
  CreateDirectory "$EXEDIR\Data\diagnostics"

  ; --- 清除 Electron 退化变量 -------------------------------------------
  ; ELECTRON_RUN_AS_NODE=1 会让 Electron 跳过 GUI 初始化
  System::Call 'kernel32::SetEnvironmentVariableW(w, w)i' \
    'ELECTRON_RUN_AS_NODE' '""'
  System::Call 'kernel32::SetEnvironmentVariableW(w, w)i' \
    'NODE_OPTIONS' '""'

  ; 记录清理结果，便于事后核查
  FileOpen $ELLog "$EXEDIR\Data\diagnostics\env_check.txt" w
  ${If} $ELLog != ""
    System::Call 'kernel32::GetEnvironmentVariableW(w,i,w,i)i' \
      '.r0' 'ELECTRON_RUN_AS_NODE' '$0' 64
    ${If} $0 == 0
      FileWrite $ELLog "ELECTRON_RUN_AS_NODE = (cleared)`r`n"
    ${Else}
      FileWrite $ELLog "ELECTRON_RUN_AS_NODE = STILL PRESENT`r`n"
    ${EndIf}
    FileClose $ELLog
  ${EndIf}
!macroend

!macro Custom.nsh_PreExec
  ; 双保险：PreExec 再清一次（.onInit 之后仍可能有工具链重新注入）
  System::Call 'kernel32::SetEnvironmentVariableW(w, w)i' \
    'ELECTRON_RUN_AS_NODE' '""'

  ; 清掉运行时锁残留，避免走 LauncherCrashCleanup 分支弹框退出
  Delete "$EXEDIR\Data\PortableApps.comLauncherRuntimeData-CodeArtsAgentPortable.ini"
!macroend