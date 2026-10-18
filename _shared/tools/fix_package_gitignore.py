# -*- coding: utf-8 -*-
"""fix_package_gitignore.py —— 重写 39 个包级 .gitignore

背景：原包级 .gitignore 第 1 行是 `dist/`（且带 UTF-8 BOM），把整个 dist 树
一刀切排除。但根级 .gitignore 的注释明确写着
    「dist/<Pkg>/update.py 是**策略源码**，要入库」
两者矛盾 —— 结果 39 个 update.py（合计约 1.1MB）全被漏掉。

新内容：默认仍排除整个 dist 树（程序二进制 + 构建产物 + 运行期数据），
但显式放行 update.py 与 version.json。顺带去掉了 BOM（git 能容忍，
但 diff 里会显示成乱码）。

用法：python fix_package_gitignore.py [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path

# 本文件位于 <仓库根>/_shared/tools/ → 上溯 2 层即仓库根
ROOT = Path(__file__).resolve().parents[2]

TEMPLATE = """\
# 包级 .gitignore —— 只入库「配方」，不入库「产物」
#
# dist/ 是可运行产物：里面是第三方程序二进制、PAL 构建出的启动器 exe、
# help.html 以及运行期数据，全部可由 portableapps/ + _shared/ 重新生成。
# 默认整棵树排除，只放行两类**源码/元数据**：
#   update.py    —— 本包的更新策略（由 _shared/update_engine.py
#                   + _shared/configs/{pkg}.yaml 装配，是配方的一部分）
#   version.json —— 版本元数据
dist/*
!dist/{pkg}/
dist/{pkg}/*
!dist/{pkg}/update.py
!dist/{pkg}/version.json

# 构建中间产物
build/
*.paf.exe

# portableapps/ 是构建输入树：AppInfo 等元数据要入库；
# App/<程序>/（第三方二进制）与 Data/（运行期数据）由根级 .gitignore 统一排除
portableapps/Data/
portableapps/DefaultData/
portableapps/App/AppInfo/Launcher/*.ini.bak

# 通用临时 / 备份（.bakfix 是 appinfo 修复脚本的备份，*.bak 规则匹配不到）
*.log
*.tmp
*.bak
*.bakfix
.vscode/
.idea/
"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    n = 0
    for pkg_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()
                          and p.name.endswith("Portable")
                          and (p / "dist").is_dir()):
        pkg = pkg_dir.name
        target = pkg_dir / ".gitignore"
        old = target.read_bytes() if target.exists() else b""
        new = TEMPLATE.format(pkg=pkg).encode("utf-8")
        if old == new:
            continue
        if dry:
            print(f"[dry] {target}")
        else:
            target.write_bytes(new)
            print(f"[ok] {target}")
        n += 1
    print(f"\n{'将改写' if dry else '已改写'} {n} 个包级 .gitignore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
