# -*- coding: utf-8 -*-
# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path

REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
# <<< 路径自适应
r"""check_custom_nsh.py —— Custom.nsh 的 PowerShell 病态扫描

历史教训（勿再踩）：2026-10-17 之前，各包用 nsExec 内联
  nsExec::ExecToStack 'powershell -Command "..."'
起 PowerShell，踩两重坑：
  ① NSIS 把内联脚本里的 $l/$t/$p/$own 等当未声明变量吞掉（要写 $$）；
  ② PowerShell 5.1 -Command 的引号规则与预期不符（'' / "" 均 ParserError），
     且 ^| 在 PS 里不表示管道（PS 不认 ^ 转义）。
处置：全量改为 FileWrite 生成 .ps1 + -File 传参，两道坑被结构性绕开。

**但本工具此后长期在扫空集**：过滤条件仍是
  "ExecToStack" in 行 and "Command" in 行
而所有 ExecToStack 行都是 -File 形态、不含 Command 字样 →
每个包都报「无病态（ps 内联行 0 行）」，一道永远绿的假门禁。
故本次按**当前真实形态**重建扫描面：

  A 行分类（句柄感知）：
      FileOpen  $N "<path>"   → 记录 $N 的目标文件
      FileClose $N            → 注销
      FileWrite $N "..."      → 按目标后缀归类：
          .ps1  → PowerShell 规则（见下）
          其他   → 配置文件/日志，NSIS 变量展开是**故意**的，跳过
      nsExec::Exec* / ExecWait / ExecShell → 执行器行规则（见下）

  B PowerShell 规则（仅对写 .ps1 的行）：
      裸 $var   必须写 $$var，否则 NSIS 把它当未声明变量吞掉，ps1 残缺
                （白名单：$EXEDIR/$DataDirectory 等 NSIS 路径常量允许单写）
      ''        NSIS 单引号串会被提前截断
      ^|        PowerShell 不认 ^ 转义

  C 执行器规则：
      -Command  内联回归 —— 已知两重坑，必须走 -File
      ''        NSIS 单引号串截断
      ^|        PowerShell 不认 ^ 转义

扫描两棵树并按包去重（dist 优先，它是实际构建产物）：
  <Pkg>/portableapps/App/AppInfo/Launcher/Custom.nsh
  <Pkg>/dist/<Pkg>/App/AppInfo/Launcher/Custom.nsh

退出码：0 = 无病态；1 = 有病态，或扫到 0 个文件。
扫到 0 个文件必须判失败：否则「路径不存在 → 零输出 → exit 0」是假绿。
"""
import re
import sys

REPO = _Path(REPO_ROOT)

# 允许以单 $ 形式出现的 NSIS 路径常量（其余裸 $变量 一律要求 $$）
NSIS_VARS = {
    "EXEDIR", "INSTDIR", "DATADIRECTORY", "APPDATA", "LOCALAPPDATA",
    "COMMONFILES", "PROGRAMFILES", "SYSTEM", "WINDIR", "TEMP", "PROFILE",
    "DOCUMENTS", "DESKTOP", "SMPROGRAMS", "CMDLINE", "OUTDIR",
}

FILE_OPEN_RE = re.compile(r"\bFileOpen\s+\$(\w+)\s+[\"']([^\"']+)")
FILE_CLOSE_RE = re.compile(r"\bFileClose\s+\$(\w+)")
FILE_WRITE_RE = re.compile(r"\bFileWrite\s+\$(\w+)\s+(.+)$")
EXEC_RE = re.compile(r"\b(?:nsExec::Exec\w*|ExecWait|ExecShell)\b")
BARE_VAR_RE = re.compile(r"(?<!\$)\$(?!\$)([A-Za-z_][A-Za-z0-9_]*)")

# 每种树的目录布局（相对仓库根），两棵树都认 App/ 与 <Pkg>/App/ 两种布局
TREES = {
    "portableapps": (
        "*/portableapps/App/AppInfo/Launcher/Custom.nsh",
        "*/portableapps/*/App/AppInfo/Launcher/Custom.nsh",
    ),
    "dist": (
        "*/dist/*/App/AppInfo/Launcher/Custom.nsh",
    ),
}


def collect():
    """返回 {包名: (树名, Path)}，同一包只留一个（dist 优先于 portableapps）。"""
    found = {}
    for tree in ("dist", "portableapps"):   # dist 先扫 → 优先
        for g in TREES[tree]:
            for p in sorted(REPO.glob(g)):
                pkg = p.relative_to(REPO).parts[0]
                if pkg not in found:
                    found[pkg] = (tree, p)
    return found


def scan_file(path):
    """扫描单个 Custom.nsh。

    返回 (hits, stats)：
      hits  —— [(行号, [问题标签, ...]), ...]
      stats —— {"ps_lines": 写 .ps1 的行数, "exec_lines": 执行器行数}
    """
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError as e:
        return [(0, ["读取失败: %s" % e])], {"ps_lines": 0, "exec_lines": 0}

    hits = []
    handles = {}                       # $句柄 → 目标文件路径
    stats = {"ps_lines": 0, "exec_lines": 0}

    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if not s or s.startswith(";"):
            continue

        m = FILE_OPEN_RE.search(ln)
        if m:
            handles[m.group(1)] = m.group(2)
            continue
        m = FILE_CLOSE_RE.search(ln)
        if m:
            handles.pop(m.group(1), None)
            continue

        m = FILE_WRITE_RE.search(ln)
        if m:
            target = handles.get(m.group(1), "")
            if not target.lower().endswith(".ps1"):
                continue            # 配置文件/日志：NSIS 展开是故意的
            stats["ps_lines"] += 1
            payload = m.group(2)
            probs = []
            for v in BARE_VAR_RE.findall(payload):
                if v.upper() in NSIS_VARS:
                    continue
                probs.append("裸$%s（应写$$%s，否则 NSIS 吞掉该变量）" % (v, v))
            if "''" in payload and payload.lstrip().startswith("'"):
                probs.append("''引号（NSIS 单引号串被提前截断）")
            if "^|" in payload:
                probs.append("^|管道（PowerShell 不认 ^ 转义）")
            if probs:
                hits.append((i, probs))
            continue

        if EXEC_RE.search(ln):
            stats["exec_lines"] += 1
            if not re.search(r"powershell", ln, re.I):
                continue
            probs = []
            if "-Command" in ln:
                probs.append("-Command 内联回归（应改 FileWrite 生成 ps1 + -File）")
            if "''" in ln:
                probs.append("''引号（NSIS 单引号串被提前截断）")
            if "^|" in ln:
                probs.append("^|管道（PowerShell 不认 ^ 转义）")
            if probs:
                hits.append((i, probs))

    return hits, stats


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    found = collect()
    if not found:
        print("!! 未扫描到任何 Custom.nsh（仓库根：%s）" % REPO_ROOT)
        print("!! 0 个文件被检查 —— 本工具拒绝在这种状态下判绿，按失败处理")
        print("!! 若包布局有变，请同步更新本文件里的 TREES 路径模式。")
        return 1

    bad_pkgs = 0
    tot_ps = tot_exec = 0
    for pkg in sorted(found):
        tree, p = found[pkg]
        hits, st = scan_file(p)
        tot_ps += st["ps_lines"]
        tot_exec += st["exec_lines"]
        if hits:
            bad_pkgs += 1
            print("[%s][%s] 病态 %d 处:" % (pkg, tree, len(hits)))
            for lineno, probs in hits:
                print("      L%-4d %s" % (lineno, "；".join(probs)))
        else:
            print("[%s][%s] 无病态（写 .ps1 %d 行 / 执行器 %d 行）"
                  % (pkg, tree, st["ps_lines"], st["exec_lines"]))

    print("-" * 64)
    print("扫描 %d 个 Custom.nsh（同包 dist 优先于 portableapps）；"
          "写 .ps1 行合计 %d，执行器行合计 %d" % (len(found), tot_ps, tot_exec))
    if tot_ps == 0 and tot_exec == 0:
        print("!! 未检查到任何 PowerShell 相关行 —— 过滤条件可能又对不上形态，"
              "按失败处理")
        return 1
    if bad_pkgs:
        print("病态包 %d 个 —— 修 Custom.nsh 后重跑" % bad_pkgs)
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
