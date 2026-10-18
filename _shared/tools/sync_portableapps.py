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
"""sync_portableapps.py —— 把全部已修复包的 dist Custom.nsh 同步到
portableapps 源树（源树保持最新修复版）。"""
import glob
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

n = 0
for f in sorted(glob.glob(
        REPO_ROOT_F + "/*Portable/dist/*Portable/"
        "App/AppInfo/Launcher/Custom.nsh")):
    src = open(f, encoding="utf-8", errors="replace").read()
    if ".np-helpers.ps1" not in src and "np-taskclean" not in src:
        continue
    # f = <pkg>/dist/<Pkg>/App/AppInfo/Launcher/Custom.nsh
    pkgdir = f.split(os.sep + "dist" + os.sep, 1)[0]
    pkg = os.path.basename(pkgdir)
    dst = os.path.join(pkgdir, "portableapps", "App", "AppInfo", "Launcher",
                       "Custom.nsh")
    if not os.path.exists(os.path.dirname(dst)):
        continue
    if os.path.exists(dst):
        same = open(dst, encoding="utf-8", errors="replace").read() == src
        if same:
            continue
    shutil.copy2(f, dst)
    n += 1
    print(f"[sync] {pkg}")
print(f"\nsynced {n} packages")
