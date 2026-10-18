; ===========================================================================
; KukuAIPortable  Custom.nsh
; ===========================================================================
; 踩坑（2026-10-17 实测）：KukuAI 原本无 Custom.nsh，启动器 ini 把
; TEMP/TMP 重定向到 $DataDirectory\settings\Temp，但没人创建该目录 ——
; Electron/Chromium 启动时要求 TEMP 可写，秒退且无任何报错。
; 本钩子补建 settings 目录树；数据收纳沿用 ini 的环境变量重定向。
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
  CreateDirectory "$DataDirectory\settings"
  CreateDirectory "$DataDirectory\settings\local"
  CreateDirectory "$DataDirectory\settings\Temp"
    ${SJ_Setup}
!macroend

!macro Custom.nsh_PostPrimary
    ${SJ_Teardown}
!macroend

!macro Custom.nsh_Unload
    ${SJ_Teardown}
!macroend

; ===========================================================================
; ★ ~/.xxx 点目录接管（20261018）
; ---------------------------------------------------------------------------
; Electron/VSCode 系的扩展、插件、ripgrep 等写在 %USERPROFILE%\.<name>，
; 环境变量重定向管不到（详见 tools/fix_dot_home_dirs.py 头注释）。
; 这里沿用仓库既有 junction 约定：宿主真实目录先 robocopy 合并进 Data 再移除
; （不丢数据）；已是 junction 则不抢不拆；退出只 rmdir 不带 /s（只拆联接）。
; ===========================================================================
!macro SJ_IsJunction _PATH _RESULT
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
!define SJ_IsJunction `!insertmacro SJ_IsJunction`

!macro SJ_Create _HOST _TARGET
    CreateDirectory "${_TARGET}"
    ${If} ${FileExists} "${_HOST}"
        ${SJ_IsJunction} "${_HOST}" $7
        ${If} $7 != "1"
            nsExec::ExecToLog 'cmd /c robocopy "${_HOST}" "${_TARGET}" /E /XO /XJ /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c attrib -R -S -H "${_HOST}\\*" /S /D'
            nsExec::ExecToLog 'cmd /c del /f /s /q "${_HOST}\\*" >nul 2>nul'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "${_HOST}"'
        ${EndIf}
    ${EndIf}
    ${IfNot} ${FileExists} "${_HOST}"
        nsExec::ExecToLog 'cmd /c mklink /J "${_HOST}" "${_TARGET}"'
    ${EndIf}
!macroend
!define SJ_Create `!insertmacro SJ_Create`

!macro SJ_Remove _HOST
    ${If} ${FileExists} "${_HOST}"
        ${SJ_IsJunction} "${_HOST}" $7
        ${If} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "${_HOST}"'
        ${EndIf}
    ${EndIf}
!macroend
!define SJ_Remove `!insertmacro SJ_Remove`

!macro SJ_Setup
    ${SJ_Create} "$PROFILE\.kukuai" "$DataDirectory\settings\user\.kukuai"
!macroend
!define SJ_Setup `!insertmacro SJ_Setup`

!macro SJ_Teardown
    ${SJ_Remove} "$PROFILE\.kukuai"
!macroend
!define SJ_Teardown `!insertmacro SJ_Teardown`
