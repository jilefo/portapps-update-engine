# -*- coding: utf-8 -*-
"""retry_move.py —— 仅迁移尚未搬完的项目（幂等，可反复执行）

首轮迁移中 5 个项目因目录被占用（WinError 5拒绝访问）失败：
BaiduNetdiskPortable / KukuAIPortable / LobsterAIPortable /
TyporaPortable / WinClawPortable

已成功的项目源目录已不存在，本脚本跳过它们，只处理仍在源目录中的项目。
"""
import os
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[2]          # <仓库根>
SRC = _ROOT.parent / "GreenSoftMake" / "Work"
DST = _ROOT

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

RETRIES = 3


def count_files(p: Path) -> int:
    n = 0
    for _r, _d, files in os.walk(p):
        n += len(files)
    return n


def main() -> int:
    todo = []
    for name in PROJECTS:
        s, d = SRC / name, DST / name
        if s.is_dir() and not d.exists():
            todo.append(name)
        elif d.is_dir() and not s.exists():
            print(f"  [已迁移] {name}")
        elif s.is_dir() and d.is_dir():
            print(f"  [!! 双份存在] {name} —— 需人工核查")
        else:
            print(f"  [缺失] {name}")

    if not todo:
        print("\n[完成] 无待迁移项目。")
        return 0

    print(f"\n[待迁移] {len(todo)}: {todo}\n")
    fail = []
    for name in todo:
        s, d = SRC / name, DST / name
        n_before = count_files(s)
        for attempt in range(1, RETRIES + 1):
            try:
                os.replace(s, d)
                n_after = count_files(d)
                tag = "OK" if n_after == n_before else f"计数漂移 {n_before}->{n_after}"
                print(f"  [{tag}] {name} ({n_after} 文件, 第{attempt}次)")
                break
            except OSError as e:
                if attempt == RETRIES:
                    fail.append((name, str(e)))
                    print(f"  [ERROR] {name}: {e} (已重试 {RETRIES} 次)")
                else:
                    print(f"  [retry {attempt}] {name}: {e}")
                    time.sleep(2)

    print(f"\n[汇总] 成功 {len(todo) - len(fail)} / 待处理 {len(todo)}")
    if fail:
        print("[仍被占用]")
        for n, e in fail:
            print(f"  - {n}: {e}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())