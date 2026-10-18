# -*- coding: utf-8 -*-
r"""
fix_dot_home_dirs.py —— 「数据保存不对」专项：接管 `~/.xxx` 点目录

原因（实测，2026-10-18）
------------------------
Electron / VSCode 系有两条落盘路径，环境变量重定向只能管住一条：

  1) %APPDATA%\<Vendor>     走 SHGetKnownFolderPath(FOLDERID_RoamingAppData)
     —— **不读 %APPDATA% 环境变量**，只改环境变量对它完全无效。
     本仓库对这些目录已用 junction 接管（实测退出后均为 junction，正常）。
  2) %USERPROFILE%\.<name>  走 Node os.homedir() / Electron app.getPath('home')
     —— 由 VSCode 系（Trae / Cursor / CodeArts / CherryStudio / KukuAI...）
     写入 extensions、plugins、ripgrep 二进制等，动辄上百 MB。
     本仓库此前**完全没接管**，实测 Trae 运行时 `~/.trae-cn\builtin` 被改写、
     `~/.ai_completion\.ripgrep` 被改写，`~/.trae-cn` 现存 102.9MB。

修法： junction 接管（与 QQ 系同一套约定）
  · 宿主是真实目录 → robocopy 合并进 Data 后再移除（沿用仓库既有语义，不丢数据）
  · 宿主已是 junction → 不抢不拆（避免误伤他包）
  · 退出时只 rmdir（不带 /s），只拆联接、绝不删穿真实 Data

刻意不做（避免破坏宿主上正在跑的同名软件）：
  WorkBuddyPortable / CodeBuddyCNPortable 的 `~/.workbuddy`、`~/.codebuddy`
  —— 本机宿主实例正在使用，接管会导致当前会话异常，留作手工选项。

用法：python fix_dot_home_dirs.py [--apply]    默认 dry-run
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = os.environ.get("PORTABLEAPPS_ROOT") or str(Path(__file__).resolve().parents[2])
STAMP = date.today().strftime("%Y%m%d")

# 产品根唯一解析处（dist 迁移到 D:\Portapps 后由它接管产品路径）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

# 包 -> [(宿主路径模板, Data 内相对路径)]，宿主用 NSIS 变量写
CONFIG = {
    "TraeCNPortable": [
        (r"$PROFILE\.trae-cn", r"user\.trae-cn"),
        (r"$PROFILE\.ai_completion", r"user\.ai_completion"),
    ],
    "CherryStudioPortable": [
        (r"$PROFILE\.cherrystudio", r"user\.cherrystudio"),
    ],
    "CodeArtsPortable": [
        (r"$PROFILE\.codearts", r"user\.codearts"),
        (r"$PROFILE\.codeartsdoer", r"user\.codeartsdoer"),
        (r"$PROFILE\.codearts-doer-for-coding", r"user\.codearts-doer-for-coding"),
    ],
    "KukuAIPortable": [
        (r"$PROFILE\.kukuai", r"user\.kukuai"),
    ],
    "CursorPortable": [
        (r"$PROFILE\.cursor", r"user\.cursor"),
    ],
}

MACROS = r"""
; ===========================================================================
; ★ ~/.xxx 点目录接管（{stamp}）
; ---------------------------------------------------------------------------
; Electron/VSCode 系的扩展、插件、ripgrep 等写在 %USERPROFILE%\.<name>，
; 环境变量重定向管不到（详见 tools/fix_dot_home_dirs.py 头注释）。
; 这里沿用仓库既有 junction 约定：宿主真实目录先 robocopy 合并进 Data 再移除
; （不丢数据）；已是 junction 则不抢不拆；退出只 rmdir 不带 /s（只拆联接）。
; ===========================================================================
!macro SJ_IsJunction _PATH _RESULT
    StrCpy $8 "${{_PATH}}"
    System::Call 'kernel32::GetFileAttributesW(t r8) i .r9'
    ${{If}} $9 == -1
        StrCpy ${{_RESULT}} "0"
    ${{Else}}
        IntOp $9 $9 & 0x400
        ${{If}} $9 == 0
            StrCpy ${{_RESULT}} "0"
        ${{Else}}
            StrCpy ${{_RESULT}} "1"
        ${{EndIf}}
    ${{EndIf}}
!macroend
!define SJ_IsJunction `!insertmacro SJ_IsJunction`

!macro SJ_Create _HOST _TARGET
    CreateDirectory "${{_TARGET}}"
    ${{If}} ${{FileExists}} "${{_HOST}}"
        ${{SJ_IsJunction}} "${{_HOST}}" $7
        ${{If}} $7 != "1"
            nsExec::ExecToLog 'cmd /c robocopy "${{_HOST}}" "${{_TARGET}}" /E /XO /XJ /NFL /NDL /NJH /NJS'
            nsExec::ExecToLog 'cmd /c attrib -R -S -H "${{_HOST}}\\*" /S /D'
            nsExec::ExecToLog 'cmd /c del /f /s /q "${{_HOST}}\\*" >nul 2>nul'
            nsExec::ExecToLog 'cmd /c rmdir /s /q "${{_HOST}}"'
        ${{EndIf}}
    ${{EndIf}}
    ${{IfNot}} ${{FileExists}} "${{_HOST}}"
        nsExec::ExecToLog 'cmd /c mklink /J "${{_HOST}}" "${{_TARGET}}"'
    ${{EndIf}}
!macroend
!define SJ_Create `!insertmacro SJ_Create`

!macro SJ_Remove _HOST
    ${{If}} ${{FileExists}} "${{_HOST}}"
        ${{SJ_IsJunction}} "${{_HOST}}" $7
        ${{If}} $7 == "1"
            nsExec::ExecToLog 'cmd /c rmdir "${{_HOST}}"'
        ${{EndIf}}
    ${{EndIf}}
!macroend
!define SJ_Remove `!insertmacro SJ_Remove`

!macro SJ_Setup
{setup}!macroend
!define SJ_Setup `!insertmacro SJ_Setup`

!macro SJ_Teardown
{teardown}!macroend
!define SJ_Teardown `!insertmacro SJ_Teardown`
"""


def build_block(pairs, datadir_var):
    setup = "".join(
        f'    ${{SJ_Create}} "{h}" "{datadir_var}\\settings\\{t}"\n' for h, t in pairs
    )
    teardown = "".join(f'    ${{SJ_Remove}} "{h}"\n' for h, _ in pairs)
    return MACROS.format(stamp=STAMP, setup=setup, teardown=teardown)


def insert_call(txt: str, macro: str, call: str, at_end: bool) -> str | None:
    """在 !macro <macro> ... !macroend 体内插入 call（按行处理，避免
    空宏体时把 `!macroend` 拆成 `!` + `macroend` 的 off-by-one）。"""
    lines = txt.split("\n")
    start = None
    for i, l in enumerate(lines):
        if re.match(rf"^!macro\s+{re.escape(macro)}\b", l):
            start = i
            break
    if start is None:
        return None
    end = None
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == "!macroend":
            end = j
            break
    if end is None:
        return None
    if at_end:
        lines.insert(end, call)
    else:
        k = start + 1
        while k < end and (not lines[k].strip()
                           or lines[k].lstrip().startswith(";")):
            k += 1
        lines.insert(k, call)
    return "\n".join(lines)


def patch(pkg: str, path: Path, apply: bool) -> str:
    raw = path.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        return "skip-bom"
    txt = raw.decode("utf-8", errors="replace")
    if "SJ_IsJunction" in txt:
        return "already"
    pairs = CONFIG[pkg]
    dd = "$DataDirectory"
    block = build_block(pairs, dd)
    # 1) 宏定义追加到文件末尾
    txt2 = txt.rstrip() + "\n" + block
    # 2) 在 PreExecPrimary 末尾建链；PostPrimary / Unload 开头拆链
    for macro, call, at_end in (
        ("Custom.nsh_PreExecPrimary", "    ${SJ_Setup}", True),
        ("Custom.nsh_PostPrimary", "    ${SJ_Teardown}", False),
        ("Custom.nsh_Unload", "    ${SJ_Teardown}", False),
    ):
        r = insert_call(txt2, macro, call, at_end)
        if r is None:
            return f"no-hook-{macro}"
        txt2 = r
    if apply:
        bak = path.with_suffix(path.suffix + f".bak-dot-{STAMP}")
        if not bak.exists():
            bak.write_bytes(raw)
        path.write_text(txt2, encoding="utf-8", newline="")
    return "patched"


def main() -> int:
    apply = "--apply" in sys.argv
    root = Path(REPO_ROOT)
    stats = {}
    for pkg in CONFIG:
        # 产品树 Custom.nsh：迁移前 <Repo>/<Pkg>/dist/<Pkg>/...，
        # 迁移后 <产品根>/<Pkg>/...（_paths 自动切换）
        prod = _paths.product_dir(pkg) / "App" / "AppInfo" / "Launcher" / "Custom.nsh"
        src = root / pkg / "portableapps" / "App" / "AppInfo" / "Launcher" / "Custom.nsh"
        for p in (prod, src):
            if not p.exists():
                stats["missing"] = stats.get("missing", 0) + 1
                continue
            r = patch(pkg, p, apply)
            stats[r] = stats.get(r, 0) + 1
            try:
                rel = p.relative_to(root)
            except ValueError:
                rel = p                 # 产品根在仓库外
            print(f"  [{r}] {rel}")
    print("\n统计:", stats)
    if not apply:
        print("（dry-run；加 --apply 生效，自动留 .bak-dot 备份）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
