# -*- coding: utf-8 -*-
r"""fix_exceptions.py —— 三特例项目剔除自动更新/自动发布文件

【任务书依据】
第1 节：「排除特例：FoxitPDFPortable、SublimeTextPortable、WPSOfficePortable
这三个项目不需要自动更新脚本，也不参与自动打包发布。但必须保持独立目录结构、
完整开源文档和双轨标准基础框架。」

因此这三个项目**不应存在**：
  .github/workflows/release.yml        （自动发布）
  .github/workflows/portableapps.yml   （自动打包）
  scripts/package-paf.py/.ps1（自动打包入口）

保留：ci.yml（结构校验）、全部社区健康文件、docs/、portableapps/ 配置。

【安全约束】不删除，移到 Backups/ 下留档，可随时回滚。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]          # <仓库根>，不写死
BACKUP = ROOT.parent / "GreenSoftMake" / "Backups" / "exception-removed"

NO_AUTO = ["FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable"]

REMOVE = [
    ".github/workflows/release.yml",
    ".github/workflows/portableapps.yml",
    "scripts/package-paf.py",
    "scripts/package-paf.ps1",
]


def main() -> int:
    execute = "--execute" in sys.argv
    print(f"[模式] {'EXECUTE' if execute else 'DRY-RUN'}\n")
    total = 0
    for pkg in NO_AUTO:
        root = ROOT / pkg
        for rel in REMOVE:
            src = root / rel.replace("/", "\\")
            if not src.is_file():
                continue
            total += 1
            if execute:
                dst = BACKUP / pkg / rel.replace("/", "\\")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                print(f"  [移出] {pkg}/{rel}  ->  {dst}")
            else:
                print(f"  [将移出] {pkg}/{rel}")
    print(f"\n合计 {total} 个文件{'已移出并留档于 ' + str(BACKUP) if execute else '待移出'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())