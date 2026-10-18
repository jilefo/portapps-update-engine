# -*- coding: utf-8 -*-
r"""fix_launcher_rtdata.py —— 全库根治「上次未正常关闭」导致便携包拒绝启动。

背景（PAL 源码实证）
--------------------
_shared\toolchain\PortableApps.comLauncher\Other\Source\PortableApps.comLauncher.nsi

    Section
        Call Init                     ; Function Init 第 1 段即 ${RunSegment} Custom
        ...
        ${IfNot} ${FileExists} $DataDirectory\PortableApps.comLauncherRuntimeData-$BaseName.ini
        ${OrIf} $SecondaryLaunch == true
            ... Call Execute          ; 正常启动
        ${Else}
            MessageBox MB_ICONSTOP $(LauncherCrashCleanup)   ; ← L421
        ${EndIf}
        ${CallPS} Post -              ; 清理后直接收尾，程序根本没启动

即：只要 Data\PortableApps.comLauncherRuntimeData-<BaseName>.ini 存在，PAL
就只弹「did not close properly ... Please then start ... again manually」
然后退出，**不启动程序**。该 ini 仅在 PAL 正常收尾时删除
（Segments\Core.nsh L113），所以任何强杀 / 断电 / 崩溃都会留下它，
表现为「点开没反应 / 一直打不开」，必须再点一次才知道能起来。
ini 里没有任何配置项可以关掉这个行为 —— 只能抢在它判断之前清掉。

修法
----
新增 Custom.nsh_Init（PAL Function Init 的第 1 段，早于 Variables 段，
因此 $DataDirectory 尚未赋值，一律用 $EXEDIR）：
  1. 用 FindFirst 探测是否存在残留 ini（没有就零开销直接跳过）；
  2. 有则生成精简 ps1 探测「本包是否有存活实例」（除自身外包内无进程）；
  3. 确认无存活实例才 Delete —— 有实例则完全保持 PAL 原有行为，
     绝不绕过"已在运行"保护，也不破坏 junction 互斥。

用法：python fix_launcher_rtdata.py [--apply]   （默认 dry-run）
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

REPO_ROOT = (os.environ.get("PORTABLEAPPS_ROOT")
             or str(Path(__file__).resolve().parents[2]))

MARK = "Custom.nsh_Init"

# 自愈钩子与精简 helpers（不依赖 LogicLib，纯 StrCmp，任何包都能插）
SNIPPET = r"""
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

"""


def candidates(root: str):
    """返回 (包名, 树别, Custom.nsh 路径)"""
    rootp = Path(root)
    for pkg in sorted(p for p in rootp.iterdir() if p.is_dir()):
        if pkg.name.startswith("_") or pkg.name in ("docs", ".github"):
            continue
        for tree, rel in (("portableapps", "portableapps/App/AppInfo/Launcher/Custom.nsh"),
                          ("dist", "dist/%s/App/AppInfo/Launcher/Custom.nsh" % pkg.name)):
            f = pkg / rel
            if f.is_file():
                yield pkg.name, tree, f


def insert_once(text: str) -> str:
    """插到第一个 !macro Custom.nsh_* 之前；返回新文本，已存在则返回 None"""
    if MARK in text:
        return None
    idx = text.find("!macro Custom.nsh_")
    if idx < 0:
        return None
    return text[:idx] + SNIPPET.lstrip("\n") + text[idx:]


def main():
    apply = "--apply" in sys.argv
    todo, skip, nohook = [], [], []
    for pkg, tree, f in candidates(REPO_ROOT):
        t = io.open(str(f), encoding="utf-8", errors="replace").read()
        new = insert_once(t)
        if new is None:
            (skip if MARK in t else nohook).append((pkg, tree))
            continue
        todo.append((pkg, tree, f, new))

    print("仓库根: %s" % REPO_ROOT)
    print("待修复: %d    已修复过: %d    无 Custom.nsh_ 钩子: %d"
          % (len(todo), len(skip), len(nohook)))
    if nohook[:5]:
        print("  无钩子示例: %s" % nohook[:5])
    if apply:
        for pkg, tree, f, new in todo:
            io.open(str(f), "w", encoding="utf-8", newline="").write(new)
            print("  [写入] %s/%s" % (pkg, tree))
        print("完成：已写入 %d 个 Custom.nsh（请随后重编启动器 exe）" % len(todo))
    else:
        for pkg, tree, _f, _n in todo[:60]:
            print("  [将要写入] %s/%s" % (pkg, tree))
        print("（dry-run，加 --apply 才落盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
