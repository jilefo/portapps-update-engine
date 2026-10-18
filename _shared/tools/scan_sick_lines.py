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
from pathlib import Path

# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
REPO_ROOT_F = REPO_ROOT.replace("\\", "/")
_TOOLS_DIR_F = str(_Path(__file__).resolve().parent).replace("\\", "/")
# <<< 路径自适应

# 产品树 Custom.nsh 统一由 _paths 枚举（迁移后产品根、迁移前仓库 dist）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

pairs = _paths.custom_nsh_files()
total_lines = 0
for pkg, f in pairs:
    src = open(f, encoding="utf-8", errors="replace").read()
    hits = []
    for i, ln in enumerate(src.splitlines(), 1):
        s = ln.strip()
        # 注释行不算病态：2026-10-17 的修复说明里就含「powershell -Command」
        # 字样，早期版本把它当病态行报出来，35 个包全部误报、真信号被淹没。
        # 与 audit_launch_health.py 同一立场：NSIS 按 ANSI 解的是「有效键值」，
        # 注释它根本不读。
        if s.startswith(";") or s.startswith("#"):
            continue
        if "powershell" in ln and "-Command" in ln and "-File" not in ln:
            hits.append((i, s[:150]))
    if hits:
        total_lines += len(hits)
        print(f"[{pkg}] {len(hits)} sick line(s):")
        for i, t in hits:
            print(f"   L{i}: {t}")
print("\n扫描范围: %d 个产品树 Custom.nsh" % len(pairs))
print("TOTAL sick lines remaining:", total_lines)
