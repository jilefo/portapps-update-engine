# -*- coding: utf-8 -*-
# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
REPO_ROOT_F = REPO_ROOT.replace("\\", "/")
_TOOLS_DIR_F = str(_Path(__file__).resolve().parent).replace("\\", "/")
# <<< 路径自适应
"""检查 QQPortable / TIMPortable / 其他含 Custom.nsh 的包的 powershell 内联病态
（'' 引号 + 裸 $PS变量），输出每个包的问题行号与片段。"""
import glob
import os
import re

BASE = REPO_ROOT_F
PSNAMES = ("l", "t", "p", "tp", "own", "lt", "k", "v", "root", "n")
bad_var_re = re.compile(r"\$(%s)(?![A-Za-z_])" % "|".join(PSNAMES))

for f in sorted(glob.glob(os.path.join(BASE, "*Portable", "dist", "*Portable",
                                       "App", "AppInfo", "Launcher", "Custom.nsh"))):
    # 路径层级：.../<Pkg>/dist/<Pkg>/App/AppInfo/Launcher/Custom.nsh
    # 需上溯 6 层才到包目录（原实现只上溯 5 层，落在 dist 上，输出全是 [dist]）
    _p = f
    for _ in range(6):
        _p = os.path.dirname(_p)
    pkg = os.path.basename(_p)
    t = open(f, encoding="utf-8", errors="replace").read()
    hits = []
    for i, ln in enumerate(t.splitlines(), 1):
        if "ExecToStack" not in ln or "Command" not in ln:
            continue
        problems = []
        if "''" in ln:
            problems.append("''引号")
        stripped = ln.replace("$$", "")
        m = bad_var_re.search(stripped)
        if m:
            problems.append("裸$" + m.group(1))
        if "^|" in ln:
            problems.append("^|管道")
        if problems:
            hits.append((i, problems))
    if hits:
        print(f"[{pkg}] 病态 {len(hits)} 处: {hits}")
    else:
        ps = sum(1 for ln in t.splitlines() if "ExecToStack" in ln and "Command" in ln)
        print(f"[{pkg}] 无病态（ps 内联行 {ps} 行）")
