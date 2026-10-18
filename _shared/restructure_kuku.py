# -*- coding: utf-8 -*-
r"""restructure_kuku.py —— 把 KukuAIPortable 重构为双轨标准结构

【现状】
迁移前 KukuAIPortable 的原始程序**直接摊在项目根目录**：
99 个顶层项（GenFlowPro.exe、resources/、AutoUpdate/、locales/、*.dll …），
完全没有 portableapps/ 目录、没有 appinfo.ini、没有图标，
不符合 PortableApps.com Format 3.9，也不符合双轨标准。

【目标结构】
KukuAIPortable/
├── portableapps/
│   ├── App/
│   │   ├── AppInfo/       appinfo.ini、Launcher/、图标（本次生成）
│   │   └── KukuAI/        原程序全部文件（从项目根搬入）
│   ├── help.html
│   └── Other/{Help,Source}
├── dist/KukuAIPortable/   构建产物
├── docs/ scripts/ tests/ src/
└── …社区健康文件（由 scaffold.py 铺好）

【安全约束】
1. 用 os.replace 同卷移动，不复制数据。
2. KUKU\ 目录为空，一并搬入。
3. 顶层日志类文件（install.log、*.reg、库库AI 日志*.txt）属安装残留，
   **不搬入** App/，改存evidence/ 留档。
4. 每步打印结果，便于核对。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"<仓库根>/KukuAIPortable")
APPDIR = ROOT / "portableapps" / "App" / "KukuAI"

# 安装/卸载残留：不进App/，留档到 evidence/
RESIDUE_PATTERNS = ("install.log", ".reg", "日志")

VERSION = "1.6.18"
PKG_VERSION = "1.6.18.0"
APPID = "KukuAIPortable"


def is_residue(name: str) -> bool:
    low = name.lower()
    return any(p in low for p in RESIDUE_PATTERNS)


def main() -> int:
    if not ROOT.is_dir():
        print(f"[FAIL] 目录不存在: {ROOT}")
        return 1
    APPDIR.mkdir(parents=True, exist_ok=True)
    (ROOT / "portableapps" / "Other" / "Help" / "Images").mkdir(parents=True, exist_ok=True)
    (ROOT / "portableapps" / "Other" / "Source").mkdir(parents=True, exist_ok=True)
    (ROOT / "evidence").mkdir(parents=True, exist_ok=True)

    moved = residue = 0
    for item in sorted(ROOT.iterdir()):
        # 跳过已经是标准结构的目录与本次操作要建的目录
        if item.name in ("portableapps", "evidence", "dist", "docs", "scripts",
                         "tests", "src", ".github") or item.is_dir() and \
                item.name in ("docs", "scripts", "tests", "src", "dist"):
            continue
        if item.is_file() and is_residue(item.name):
            shutil.move(str(item), str(ROOT / "evidence" / item.name))
            residue += 1
            print(f"  [留档] {item.name}")
            continue
        dst = APPDIR / item.name
        if dst.exists():
            print(f"  [跳过-目标已存在] {item.name}")
            continue
        os.replace(item, dst)
        moved += 1
        if moved <= 8 or item.is_dir():
            print(f"  [搬入] {item.name}")

    n = sum(len(f) for _r, _d, f in os.walk(APPDIR))
    print(f"\n搬入 {moved} 项 / 留档 {residue} 项")
    print(f"portableapps\\App\\KukuAI\\现有 {n} 个文件")
    left = [p.name for p in ROOT.iterdir()]
    print(f"项目根剩余: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())