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
; TRAE CN Portable  Custom.nsh  （UTF-8 无 BOM，实测可编译，勿加 BOM）
; ===========================================================================
; [2026-10-15 重写：修复"打不开"(USERPROFILE 重定向崩溃) + 收尾清理]
;
; 1) 启动失败根因：launcher.ini 重定向 USERPROFILE → Electron 主进程
;    app.getPath('appData') 经 SHGetKnownFolderPath 按 %USERPROFILE% 展开
;    出不存在的路径 → "Failed to get 'appData' path" → Error 弹窗退出
;    （QoderCN/TodayCN/OfficeAce/MiniMaxCode/AiPyPro 同型，见踩坑 4.7）。
;    → 修复：ini 移除 USERPROFILE 重定向（--user-data-dir 已覆盖 userData）。
;      实测：仅删 USERPROFILE 一行后 PAL 拉起即正常（13+ 进程出主窗口）。
;
; 2) 【设计限制，禁用 Junction】~\.trae-cn（约245MB）是 TRAE CN 产品级
;    数据目录（AI 对话/模型缓存/扩展），**宿主 TraeCode CN IDE 正在运行
;    并写入同一目录**——便携版与宿主 IDE 是同一产品，Junction 会让两者
;    共用目录并在退出拆除时危及宿主数据（2026-10-15 实战踩坑，已回滚；
;    详见 docs\踩坑记录.md「同产品宿主冲突」条目）。
;    → userData 已由 --user-data-dir 隔离；~\.trae-cn 与宿主 IDE 互通
;      属产品级共享（数据格式同版兼容），标注为设计限制。
;      ★ 任何情况下不得对 ~\.trae-cn / ~\.trae 建联接或删除。
;
; 3) 历史缺陷（本次一并修掉）：原钩子宏名 CustomInit/CustomPreStart/
;    CustomPostClose/CustomUnInit 静默失效（PAL 只认 Custom.nsh_<阶段>）；
;    $INSTDIR 未初始化展开为空 → 一律改用 $EXEDIR（= 包根）。
; ===========================================================================

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
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Trae CN"
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "Trae CN Portable"
FunctionEnd

; 清理自动更新计划任务（Trae 前缀通配；便携版禁用官方更新链）
Function DeleteUpdateTask
  ${NP_TaskClean} '($$_.TaskName -like "Trae*") -and ($$_.TaskName -like "*Update*" -or $$_.TaskName -like "*Upgrade*")'
  Pop $0
  Pop $1
FunctionEnd

; 清理文件关联（该架构会注册大量 HKCU\Classes\<软件名>.<扩展名>）
Function DeleteFileAssoc
      nsExec::ExecToStack 'powershell -NoProfile -ExecutionPolicy Bypass -File "$DataDirectory\settings\.np-helpers.ps1" regclean "HKCU:\Software\Classes" "Trae CN.*" "" ""'
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
    ${SJ_Setup}
!macroend

; 主程序退出后
!macro Custom.nsh_PostPrimary
    ${SJ_Teardown}
  ${NP_WriteHelpers}
  Call KillResidual
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
!macroend

; 卸载前
!macro Custom.nsh_Unload
    ${SJ_Teardown}
  ${NP_WriteHelpers}
  Call KillResidual
  Call DeleteRunKey
  Call DeleteUpdateTask
  Call DeleteFileAssoc
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
    ${SJ_Create} "$PROFILE\.trae-cn" "$DataDirectory\settings\user\.trae-cn"
    ${SJ_Create} "$PROFILE\.ai_completion" "$DataDirectory\settings\user\.ai_completion"
!macroend
!define SJ_Setup `!insertmacro SJ_Setup`

!macro SJ_Teardown
    ${SJ_Remove} "$PROFILE\.trae-cn"
    ${SJ_Remove} "$PROFILE\.ai_completion"
!macroend
!define SJ_Teardown `!insertmacro SJ_Teardown`
