# -*- coding: utf-8 -*-
r"""_pkg.py —— 包名/包根目录定位（收敛 39 份重复脚手架脚本的关键）

推导优先级：
  1. 命令行第一个非开关参数  ->  python build-portable.py CursorPortable
  2. 当前工作目录名          ->  cd CursorPortable && python <通用脚本>
  3. PAF_PKG 环境变量
"""
import os as _os
import sys as _sys
from pathlib import Path as _Path

REPO_ROOT = _Path(__file__).resolve().parents[2]   # _shared/scripts -> 仓库根


def pkg_name():
    for a in _sys.argv[1:]:
        if not a.startswith("-"):
            return a
    cwd = _Path.cwd().resolve()
    if cwd.name.endswith("Portable") and cwd.parent == REPO_ROOT:
        return cwd.name
    return _os.environ.get("PAF_PKG") or cwd.name


PKG = pkg_name()
REPO = REPO_ROOT / PKG

if __name__ == "__main__":
    print("PKG =", PKG)
    print("REPO =", REPO)
