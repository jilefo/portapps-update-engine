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


def list_packages():
    """仓库根下真正的包：含 portableapps/ 或 dist/ 子目录的一级目录。

    用来在包名解析失败时给出可用清单，而不是把用户引向一个
    根本不存在的目录（旧行为：从仓库根跑脚本会推出 PKG=<仓库目录名>，
    然后报一串"缺 appinfo.ini"的假错）。
    """
    out = []
    for d in sorted(REPO_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if (d / "portableapps").is_dir() or (d / "dist").is_dir():
            out.append(d.name)
    return out


PKG = pkg_name()
REPO = REPO_ROOT / PKG

if not REPO.is_dir():
    _sys.stderr.write(
        "[FAIL] 包目录不存在: %s\n"
        "       推导来源可能是当前目录名/PAF_PKG，本脚本是【单包】脚本，\n"
        "       需在包目录内执行，或显式传包名，例如：\n"
        "           python %s %s\n"
        "       可用包（%d 个）：%s\n"
        % (REPO, _Path(_sys.argv[0]).name,
           (list_packages() or ["<Pkg>"])[0],
           len(list_packages()), ", ".join(list_packages())))
    _sys.exit(2)

if __name__ == "__main__":
    print("PKG =", PKG)
    print("REPO =", REPO)
