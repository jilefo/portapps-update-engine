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
"""sync_portableapps.py —— 把全部已修复包的产品树 Custom.nsh 同步到
portableapps 源树（源树保持最新修复版）。

产品树位置由 _paths.custom_nsh_files() 枚举：迁移后 <产品根>/<Pkg>/...，
迁移前 <Repo>/<Pkg>/dist/<Pkg>/...，自动切换。早期版本用 glob 硬编码
dist 路径，迁移后会扫到 0 个文件、报"synced 0"——假绿。
"""
import os
import shutil
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
n = 0
for pkg, f in pairs:
    src = open(f, encoding="utf-8", errors="replace").read()
    if ".np-helpers.ps1" not in src and "np-taskclean" not in src:
        continue
    pkgdir = os.path.join(REPO_ROOT, pkg)
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
print(f"\n扫描产品树 Custom.nsh {len(pairs)} 个，synced {n} packages")
