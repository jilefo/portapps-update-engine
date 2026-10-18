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
"""scan_broken_quotes.py —— 扫描 Custom.nsh 中 nsExec 单引号串未闭合的残缺行。"""
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

files = sorted(glob.glob(
    REPO_ROOT_F + "/*Portable/dist/*Portable/"
    "App/AppInfo/Launcher/Custom.nsh"))
bad = []
for f in files:
    pkg = os.path.basename(f.split(os.sep + "dist" + os.sep)[0])
    for i, ln in enumerate(open(f, encoding="utf-8",
                                errors="replace").read().splitlines(), 1):
        s = ln.strip()
        if "nsExec::ExecToStack" in s and s.startswith("nsExec::ExecToStack '"):
            if not s.endswith("'"):
                bad.append((pkg, i, s[-60:]))
print("unterminated nsExec lines:", len(bad))
for pkg, i, tail in bad:
    print(f"  [{pkg}] L{i} ...{tail}")
