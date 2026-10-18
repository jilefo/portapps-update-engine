# -*- coding: utf-8 -*-
"""move_children.py —— 顶层目录被占用时的降级迁移方案

背景：5 个项目（BaiduNetdisk / KukuAI / LobsterAI / Typora / WinClaw）的
顶层目录被残留进程占用（冒烟测试遗留：YunDetectService、Install.bat 等），
os.replace 无法重命名整个目录。

方案：不移动被锁的顶层目录，改为**逐个移动其子项**到目标目录下的同名目录。
子项本身未被占用时可正常重命名；迁移完成后源目录仅剩空壳，可延后清理。

本脚本只做移动，不删除任何文件。
"""
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[2]          # <仓库根>
SRC = _ROOT.parent / "GreenSoftMake" / "Work"
DST = _ROOT

TARGETS = ["KukuAIPortable", "LobsterAIPortable", "TyporaPortable",
           "WinClawPortable", "BaiduNetdiskPortable"]


def count_files(p: Path) -> int:
    n = 0
    for _r, _d, files in os.walk(p):
        n += len(files)
    return n


def main() -> int:
    for name in TARGETS:
        s, d = SRC / name, DST / name
        if not s.is_dir():
            print(f"[跳过] {name} 源不存在（可能已完全迁移）")
            continue

        d.mkdir(parents=True, exist_ok=True)
        children = list(s.iterdir())
        moved = blocked = renamed = 0
        errors = []
        for child in children:
            # 先把探测阶段留下的 __x 临时名恢复为原名，再移动
            if child.name.endswith("__x") and not child.is_dir():
                continue
            if child.is_dir() and child.name.endswith("__x"):
                orig = child.with_name(child.name[:-3])
                if not orig.exists():
                    try:
                        child.rename(orig)
                        child = orig
                        renamed += 1
                        print(f"      [恢复名] {child.parent.name}/{orig.name}")
                    except OSError as e:
                        errors.append(f"{child.name} 恢复原名失败: {e}")
                        blocked += 1
                        continue

            target = d / child.name
            if target.exists():
                errors.append(f"{child.name}: 目标已存在")
                blocked += 1
                continue
            for attempt in range(3):
                try:
                    os.replace(child, target)
                    moved += 1
                    break
                except OSError as e:
                    if attempt == 2:
                        errors.append(f"{child.name}: {e}")
                        blocked += 1
                    else:
                        time.sleep(1)

        left = [c.name for c in s.iterdir()]
        status = "OK" if blocked == 0 else f"部分阻塞({blocked})"
        print(f"[{status}] {name}: 移动 {moved} 项"
              + (f"，恢复名 {renamed} 项" if renamed else "")
              + f"，残留 {len(left)} 项 -> {left}")
        for e in errors:
            print(f"      ! {e}")

    print("\n[最终核对]")
    for name in TARGETS:
        s, d = SRC / name, DST / name
        if not s.is_dir():
            print(f"  {name}: 源已清空（完全迁移）")
            continue
        left = [c.name for c in s.iterdir()]
        print(f"  {name}: 源残留 {len(left)} 项 {left if left else ''}")
        if d.is_dir():
            print(f"      目标已含 {count_files(d)} 个文件")


if __name__ == "__main__":
    raise SystemExit(main())