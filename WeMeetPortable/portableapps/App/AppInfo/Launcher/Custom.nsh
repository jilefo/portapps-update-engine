; ===========================================================================
; Custom.nsh -- 腾讯会议 (WeMeet) 便携版
; ===========================================================================
; 本文件由 Work\_analysis\write_custom_nsh.py 生成，**必须带 UTF-8 BOM**
; （见文件头说明）。请勿手工编辑后另存为无 BOM 的 UTF-8。
;
; [2026-10-15 二次修复 —— 方案更换为 Junction 目录联接]
;   FilesMove 实测缺陷：便携包在 D 盘、宿主 APPDATA 在 C 盘，跨卷时
;         PAL 的 FilesMove 退化为【复制】（Data 侧源完整保留），退出时
;         搬回因 Data 侧已有同名目录而静默失败 —— 宿主残留 + 本次会话
;         数据变更丢失（已实测复现）。
;   Junction 方案：启动时在宿主 %APPDATA%\Tencent\WeMeet 建目录联接
;         指向 Data\settings\Tencent\WeMeet，退出时 rmdir（不带 /s）
;         只删链接。数据物理上始终只在 Data，宿主路径仅是指针：
;         零搬运、跨卷无感、无搬回失败风险。
;   关键实现：
;   - $APPDATA 为 NSIS 内置常量（SHGetFolderPath 读注册表），不受 PAL
;     [Environment] 改进程环境的影响，始终解析为宿主真实路径。
;   - 判断 junction：GetFileAttributesW & FILE_ATTRIBUTE_REPARSE_POINT
;     (0x400)，区分"残留联接"与"宿主真实目录"；真实目录先 robocopy
;     合并回 Data 再移除，绝不丢数据。
;   - 删联接只用 rmdir（不带 /s），防止删穿 junction 误删 Data 数据。
;   - 绝不联接共享/他软件目录（Marvis 属 <本机工具目录>/Marvis 独立套件；
;     beacon/BeaconConfig/DtConfig 为腾讯系共享埋点缓存）。
;
; [踩坑清单，勿重复]
;   1. Custom.nsh 改名成 <AppID>.nsh  -> /nonfatal 静默跳过，全部钩子失效
;   2. 文件无 UTF-8 BOM              -> Unicode 版 makensis 解析中断，同样静默失效
;   3. 用 !echo 做探针               -> NSIS 2.46 会丢弃 !echo，改用 !warning
;   4. 在 exe 里搜字符串判断逻辑是否编译进去 -> 不可靠，NSIS 内部会重排/压缩
;   5. Data\PortableApps.comLauncherRuntimeData-<包名>.ini 残留
;      -> 启动器走 LauncherCrashCleanup 分支弹框 Quit，所有钩子都不执行。
;      每次测试前必须删掉它，否则会误判成「钩子没生效」。
;      （2026-10-15 的启动弹框即由此残留引起）
;   6. System::Call 'kernel32::SetEnvironmentVariable(t, t)' '.r0' '路径'
;      -> 第一个参数是【字面字符串 ".r0"】，实际设了名为 .r0 的变量。
;      正确写法见下方 PreExec（变量名必须是字面量）。
; ===========================================================================

!include "LogicLib.nsh"

Var WMLog

; ---------------------------------------------------------------------------
; Junction 宏组（方案核心，见文件头二次修复说明）
; ---------------------------------------------------------------------------

; --- 判断路径是否为 reparse point（junction/symlink） --------------------
;   用法：${WM_IsJunction} "路径" $结果变量   ; "1"=junction  "0"=否/不存在
!macro WM_IsJunction _PATH _RESULT
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
!define WM_IsJunction `!insertmacro WM_IsJunction`

; --- 建立 junction（启动时调用，幂等） -------------------------------------
!macro WM_JunctionCreate
    ; 1. 确保宿主父目录存在
    ${IfNot} ${FileExists} "$APPDATA\Tencent"
        CreateDirectory "$APPDATA\Tencent"
    ${EndIf}
    ; 2. 宿主路径已存在：区分残留 junction 与真实目录
    ${If} ${FileExists} "$APPDATA\Tencent\WeMeet"
        ${WM_IsJunction} "$APPDATA\Tencent\WeMeet" $7
        ${If} $7 == "1"
            ; 上次异常退出残留的 junction：只删链接，数据本就在 Data
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\Tencent\WeMeet"'
        ${Else}
            ; 宿主真实目录（原版数据或泄漏残留）：合并回 Data 再移除
            nsExec::ExecToLog 'cmd /c robocopy "$APPDATA\Tencent\WeMeet" "$DataDirectory\settings\Tencent\WeMeet" /E /XO /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "$APPDATA\Tencent\WeMeet"'
        ${EndIf}
    ${EndIf}
    ; 3. 确保 Data 侧目标存在并建立 junction
    CreateDirectory "$DataDirectory\settings\Tencent\WeMeet"
    nsExec::ExecToLog 'cmd /c mklink /J "$APPDATA\Tencent\WeMeet" "$DataDirectory\settings\Tencent\WeMeet"'
!macroend
!define WM_JunctionCreate `!insertmacro WM_JunctionCreate`

; --- 移除 junction（退出时调用，幂等；只删链接不删目标） -------------------
!macro WM_JunctionRemove
    ${If} ${FileExists} "$APPDATA\Tencent\WeMeet"
        ${WM_IsJunction} "$APPDATA\Tencent\WeMeet" $7
        ${If} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "$APPDATA\Tencent\WeMeet"'
        ${EndIf}
    ${EndIf}
!macroend
!define WM_JunctionRemove `!insertmacro WM_JunctionRemove`

; ---------------------------------------------------------------------------
; PreExec -- 建目录 + 环境变量双保险 + 记录卸载兜底清理清单
; ---------------------------------------------------------------------------
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

!macro Custom.nsh_PreExec
  ; 1) 建目录（FilesMove 的源目录必须预先存在）
  ClearErrors
  CreateDirectory "$DataDirectory\settings"
  CreateDirectory "$DataDirectory\settings\local"
  CreateDirectory "$DataDirectory\settings\Temp"
  CreateDirectory "$DataDirectory\settings\user\Documents"
  CreateDirectory "$DataDirectory\settings\Tencent"

  ; 2) 环境变量双保险（对使用 getenv 的组件生效；junction 之外的补充）
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'APPDATA' '$DataDirectory\settings'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'LOCALAPPDATA' '$DataDirectory\settings\local'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'TEMP' '$DataDirectory\settings\Temp'
  System::Call 'kernel32::SetEnvironmentVariable(t, t)i' 'TMP' '$DataDirectory\settings\Temp'

  ; 3) 建立 junction：宿主 %APPDATA%\Tencent\WeMeet -> Data\settings\...
  ;    WeMeet 无论用 SHGetFolderPath 还是 KnownFolder API 访问宿主路径，
  ;    实际读写都落在 Data（junction 是文件系统级指针，对所有 API 透明）
  ${WM_JunctionCreate}

  ; 3) 记录卸载兜底清理清单（FilesMove 正常退出后宿主本无残留，
  ;    此清单用于异常退出后的手动/卸载时兜底，见 _卸载.bat）
  ;    注意：绝不列入 %APPDATA%\Tencent\Marvis —— 它属于宿主独立
  ;    安装的 Marvis 套件（<本机工具目录>/Marvis），清理会误伤他软件。
  FileOpen $WMLog "$DataDirectory\settings\leak_paths.txt" w
  ${If} $WMLog != ""
    FileWrite $WMLog "%APPDATA%\Tencent\WeMeet`r`n"
    FileWrite $WMLog "%APPDATA%\Tencent\BeaconConfig`r`n"
    FileWrite $WMLog "%APPDATA%\Tencent\DtConfig`r`n"
    FileWrite $WMLog "%APPDATA%\Tencent\beacon`r`n"
    FileWrite $WMLog "%LOCALAPPDATA%\Tencent`r`n"
    FileClose $WMLog
  ${EndIf}
!macroend

; ---------------------------------------------------------------------------
; PostPrimary -- 主程序退出后：拆除 junction（宿主零残留）
; ---------------------------------------------------------------------------
;   正常退出路径：WeMeet 退出 -> PAL 执行本钩子 -> rmdir 联接 ->
;   宿主 %APPDATA%\Tencent\WeMeet 消失，数据自始至终只在 Data。
;   异常退出（强杀/崩溃）：junction 残留于宿主，但数据安全在 Data；
;   下次启动 PreExec 检测到残留 junction 会 rmdir 重建（幂等自愈）。
!macro Custom.nsh_PostPrimary
  ${WM_JunctionRemove}
!macroend