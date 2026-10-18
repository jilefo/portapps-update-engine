# -*- coding: utf-8 -*-
"""migrate_projects.py —— 把 39 个便携项目从旧目录迁移到本仓库（历史脚本）

该迁移已于 2026-10-17 完成并验收，脚本保留作记录与回溯。
源/目标目录不写死，用参数提供（默认按仓库布局推导）。

历史背景：当时 D 盘仅剩 36GB、项目合计 69GB，**必须 move 不能 copy**；
同卷 move 由 os.replace 原子完成（重命名目录项，O(1)），不复制数据。

安全措施（沿用）：
  1. 默认 dry-run，仅打印计划
  2. --execute 才真正执行
  3. 逐个校验源存在、目标不存在冲突
  4. 迁移后立即校验文件数一致，不一致则报告
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[2]           # <仓库根>

_ap0 = argparse.ArgumentParser(add_help=False)
_ap0.add_argument("--src", default="", help="迁移前源目录（含各 *Portable 子目录）")
_ap0.add_argument("--dst", default=str(_ROOT), help="迁移目标仓库根目录")
_A0, _ = _ap0.parse_known_args()

SRC = Path(_A0.src) if _A0.src else _ROOT.parent / "GreenSoftMake" / "Work"
DST = Path(_A0.dst)

PROJECTS = [
    "AiPyProPortable", "BaiduNetdiskPortable", "CherryStudioPortable",
    "CodeArtsAgentPortable", "CodeArtsPortable", "CodeBuddyCNPortable",
    "ComatePortable", "CursorPortable", "eDiaryPortable", "FeishuPortable",
    "FSCapturePortable", "JoplinPortable", "JoyCodePortable",
    "LobsterAIPortable", "MiaoshouPortable", "MiniMaxCodePortable",
    "OfficeAcePortable", "QoderCNIDEPortable", "QoderCNPortable",
    "QQNTPortable", "QQPortable", "QuarkCloudDrivePortable", "ReNamerPortable",
    "SoloMDPortable", "TIMPortable", "TodayCNPortable", "TraeCNPortable",
    "TyporaPortable", "WeixinPortable", "WeMeetPortable", "WinClawPortable",
    "WorkBuddyPortable", "WXWorkPortable", "ZenBrowserPortable", "ZoomPortable",
    "FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable",
    "KukuAIPortable",
]


def count_files(p: Path) -> int:
    n = 0
    for _r, _d, files in os.walk(p):
        n += len(files)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="真正执行迁移")
    args = ap.parse_args()

    DST.mkdir(parents=True, exist_ok=True)
    print(f"[目标] {DST}")
    print(f"[来源] {SRC}")
    print(f"[模式] {'EXECUTE' if args.execute else 'DRY-RUN（加 --execute 生效）'}\n")

    # 预检
    problems = []
    for name in PROJECTS:
        s = SRC / name
        d = DST / name
        if not s.is_dir():
            problems.append(f"{name}: 源不存在 {s}")
        elif d.exists():
            problems.append(f"{name}: 目标已存在 {d}（需人工处理）")
    if problems:
        print("[预检失败]")
        for p in problems:
            print("  -", p)
        return 1
    print(f"[预检通过] {len(PROJECTS)} 个项目待迁移\n")

    if not args.execute:
        for name in PROJECTS:
            print(f"  将移动: {name}  ({count_files(SRC / name)} 个文件)")
        print("\n这是预演。加 --execute 执行。")
        return 0

    log = []
    ok = fail = 0
    for name in PROJECTS:
        s, d = SRC / name, DST / name
        n_before = count_files(s)
        try:
            os.replace(s, d)          # 同卷原子重命名
            n_after = count_files(d)
            status = "OK" if n_after == n_before else "MISMATCH"
            if n_after != n_before:
                fail += 1
            else:
                ok += 1
            log.append({"project": name, "files": n_before, "status": status})
            print(f"  [{status}] {name}: {n_before} 个文件")
        except OSError as e:
            fail += 1
            log.append({"project": name, "status": f"ERROR {e}"})
            print(f"  [ERROR] {name}: {e}")

    print(f"\n[汇总] 成功 {ok} / 失败 {fail} / 共 {len(PROJECTS)}")
    print("[剩余 Work 内容]")
    for e in sorted(os.listdir(SRC)):
        print("   ", e)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())