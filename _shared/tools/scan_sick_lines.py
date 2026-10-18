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
"""scan_sick_lines.py —— 精确扫描 Custom.nsh 中仍带内联 -Command 的病态行。"""
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

files = sorted(glob.glob(
    REPO_ROOT_F + "/*Portable/dist/*Portable/"
    "App/AppInfo/Launcher/Custom.nsh"))
total_lines = 0
for f in files:
    pkg = os.path.basename(f.split(os.sep + "dist" + os.sep)[0])
    src = open(f, encoding="utf-8", errors="replace").read()
    hits = []
    for i, ln in enumerate(src.splitlines(), 1):
        if "powershell" in ln and "-Command" in ln and "-File" not in ln:
            hits.append((i, ln.strip()[:150]))
    if hits:
        total_lines += len(hits)
        print(f"[{pkg}] {len(hits)} sick line(s):")
        for i, t in hits:
            print(f"   L{i}: {t}")
print("\nTOTAL sick lines remaining:", total_lines)
