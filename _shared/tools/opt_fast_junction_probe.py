# -*- coding: utf-8 -*-
r"""
opt_fast_junction_probe.py —— 卡顿专项：把 junction 三路判定从「每次都叫 PowerShell」
改成「NSIS 原生快速路径」，只有真正冲突时才回退 PowerShell。

为什么这是卡顿主因（本机实测，2026-10-18）
------------------------------------------
    powershell -NoProfile -File xxx.ps1   单次 1.37 s
    cmd /c echo x                        单次 0.082 s     （相差约 16 倍）

QQPortable 一次冷启动派生 24 个子进程调用（其中约 12 次 PowerShell），
光 PowerShell 就要 ~16 s；QQNT ~8 次 ≈ 11 s。用户体感就是"点了半天才出来"。

原实现：只要宿主路径是 reparse point，就无条件叫一次 PowerShell 做三路判定。
新实现（快速路径，两次 NSIS 原生文件操作即可判定 90% 的场景）：
    1. 在 TARGET 里写探针文件 → 若 HOST 下能看到  → 0（本包所有，崩溃残留）
    2. 否则再试在 HOST 里写探针文件 → 写不进去    → 3（联接目标已失效）
    3. 只有"联接存活但不在本包"这一种少见情况才回退 PowerShell 精确判定
       （1 = 兄弟包正在跑，3 = 兄弟包没跑的陈旧联接）
快速路径与包无关（不读包名），因此可无损套用到所有含 NP_JunctionProbe 的包。

安全性：默认 dry-run；--apply 才写盘，且先写 .bak-jprobe-<日期>。
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = os.environ.get("PORTABLEAPPS_ROOT") or str(Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 定位 _paths
import _paths                                   # noqa: E402
STAMP = date.today().strftime("%Y%m%d")

# 捕获整个 NP_JunctionProbe 宏
RE_MACRO = re.compile(
    r"(?P<indent>[ \t]*)!macro\s+NP_JunctionProbe\s+_HOST\s+_TARGET\s+_TAG\s+_RESULT\s*\r?\n"
    r"(?P<body>.*?)"
    r"(?P=indent)!macroend",
    re.S,
)
# 宏体里原来的 PowerShell 调用行（作为回退保留）
RE_PS = re.compile(r"^\s*nsExec::ExecToStack\s+'.*?\.np-helpers\.ps1.*?'\s*$", re.M)
RE_POPS = re.compile(r"^\s*Pop\s+\S+\s*$", re.M)

TEMPLATE = """{i}!macro NP_JunctionProbe _HOST _TARGET _TAG _RESULT
{i}    ; [卡顿优化 {stamp} | 标记 junc-probe-fast] 原实现无条件调用 PowerShell（单次实测 1.37s），
{i}    ; QQ 系一次冷启动要十几次，累计 ~16s。改为 NSIS 原生快速路径：
{i}    ;   ① TARGET 里写探针文件，HOST 下可见      -> 0 本包所有（崩溃残留）
{i}    ;   ② 否则试探 HOST 是否可写，不可写        -> 3 联接目标已失效
{i}    ;   ③ 仅"联接存活但不属本包"（少见）才回退 PowerShell 精判 1/3
{i}    StrCpy ${{_RESULT}} "2"
{i}    CreateDirectory "${{_TARGET}}"
{i}    FileOpen $9 "${{_TARGET}}\\.junc-probe-${{_TAG}}" w
{i}    ${{If}} $9 == ""
{i}        ; TARGET 不可写，无法用文件探针，退回原判定
{fallback}
{i}    ${{Else}}
{i}        FileWrite $9 "x"
{i}        FileClose $9
{i}        ${{If}} ${{FileExists}} "${{_HOST}}\\.junc-probe-${{_TAG}}"
{i}            StrCpy ${{_RESULT}} "0"
{i}            Delete "${{_HOST}}\\.junc-probe-${{_TAG}}"
{i}        ${{Else}}
{i}            Delete "${{_TARGET}}\\.junc-probe-${{_TAG}}"
{i}            FileOpen $9 "${{_HOST}}\\.junc-probe-${{_TAG}}" w
{i}            ${{If}} $9 == ""
{i}                StrCpy ${{_RESULT}} "3"
{i}            ${{Else}}
{i}                FileClose $9
{i}                Delete "${{_HOST}}\\.junc-probe-${{_TAG}}"
{i}                ; 联接存活但不属本包：交给 PowerShell 精确判定
{fallback}
{i}            ${{EndIf}}
{i}        ${{EndIf}}
{i}    ${{EndIf}}
{i}!macroend
"""


def build_new(indent: str, ps_line: str) -> str:
    fb = "\n".join(f"{indent}        {l.strip()}" for l in ps_line.splitlines() if l.strip())
    return TEMPLATE.format(i=indent, stamp=STAMP, fallback=fb)


def patch_file(path: Path, apply: bool) -> str:
    raw = path.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        return "skip(带BOM，先修BOM)"
    txt = raw.decode("utf-8", errors="replace")
    m = RE_MACRO.search(txt)
    if not m:
        return "no-macro"
    body = m.group("body")
    # 幂等标记 = 模板产出的探针名前缀 "junc-probe-"（只在快速路径里出现，
    # 未打补丁的宏体内没有）。早期版本检查 "junc-probe-fast"，但模板注释里
    # 从未吐出该完整串 → 已修补文件被误判为待打，--apply 会重复打补丁。
    if "junc-probe-" in body:
        return "already"
    psl = RE_PS.search(body)
    if not psl:
        return "no-ps-line"
    # 回退块 = 原 PS 调用 + 紧随的两个 Pop（取宏体内全部 Pop 行）
    pops = RE_POPS.findall(body)
    fb_lines = [psl.group(0).strip()] + [p.strip() for p in pops][:2]
    ps_line = "\n".join(fb_lines)
    new = build_new(m.group("indent"), ps_line)
    out = txt[: m.start()] + new + txt[m.end():]
    if apply:
        bak = path.with_suffix(path.suffix + f".bak-jprobe-{STAMP}")
        if not bak.exists():
            bak.write_bytes(raw)
        path.write_text(out, encoding="utf-8", newline="")
    return "patched"


def main() -> int:
    apply = "--apply" in sys.argv
    root = Path(REPO_ROOT)
    stats = {}
    # 产物树 Custom.nsh：迁移前 <Repo>/<Pkg>/dist/<Pkg>/...，
    # 迁移后 <产品根>/<Pkg>/... —— 统一经 _paths.custom_nsh_files() 枚举
    # （老 glob 在迁移后会扫到 0 个文件而假绿）。
    prod_files = _paths.custom_nsh_files()
    print("产物根: %s（来源 %s）| 产品树 Custom.nsh %d 个"
          % (_paths.product_root(), _paths.product_root_source(),
             len(prod_files)))
    for pkg, nsh in prod_files:
        r = patch_file(nsh, apply)
        stats[r] = stats.get(r, 0) + 1
        if r == "patched":
            print(f"  [改] {pkg}/dist")
    for nsh in sorted(root.glob("*/portableapps/App/AppInfo/Launcher/Custom.nsh")):
        r = patch_file(nsh, apply)
        stats[r] = stats.get(r, 0) + 1
        if r == "patched":
            # parents: 0=Launcher 1=AppInfo 2=App 3=portableapps 4=<Pkg>
            print(f"  [改] {nsh.parents[4].name}/source")
    print("\n统计:", stats)
    if not apply:
        print("（dry-run，未写盘；加 --apply 生效，会自动留 .bak-jprobe 备份）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
