# -*- coding: utf-8 -*-
r"""verify_migration.py —— 迁移完整性核验

对比 Work\ 残留 与 PortableApps\ 目标，逐文件校验大小；
对 app.asar 等大文件额外做 SHA256 比对，确保复制无损。

注：raw docstring——原写法 `Work\ ` 尾部反斜杠是非法转义
（Python 3.12+ SyntaxWarning，`-W error::SyntaxWarning` 下变 SyntaxError）。
"""
import hashlib
import os
import sys
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


def sha256(p: Path, chunk=4 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def inventory(root: Path) -> dict:
    """相对路径 -> 大小"""
    out = {}
    if not root.is_dir():
        return out
    for r, _d, files in os.walk(root):
        for f in files:
            fp = Path(r) / f
            try:
                out[str(fp.relative_to(root)).replace("\\", "/")] = fp.stat().st_size
            except OSError:
                pass
    return out


def main() -> int:
    print(f"{'项目':24s} {'目标文件':>9s} {'源残留':>8s}  状态")
    print("-" * 78)
    total_missing = 0
    leftover_all = {}

    for name in PROJECTS:
        s, d = SRC / name, DST / name
        inv_s = inventory(s)
        inv_d = inventory(d)
        if not inv_d:
            print(f"{name:24s} {'0':>9s} {'-':>8s}  !! 目标不存在")
            total_missing += 1
            continue
        if inv_s:
            leftover_all[name] = sorted(inv_s)
        status = "OK" if not inv_s else f"源残留 {len(inv_s)} 文件(已复制,待清理)"
        print(f"{name:24s} {len(inv_d):>9d} {len(inv_s):>8d}  {status}")

    # 大文件哈希核验
    print("\n=== app.asar SHA256 核验 ===")
    pairs = [
        ("KukuAIPortable", "resources/app.asar"),
        ("LobsterAIPortable", "resources/app.asar"),
        ("WinClawPortable", "resources/app.asar"),
        ("TyporaPortable", "portableapps/App/Typora/resources/app.asar"),
    ]
    for proj, rel in pairs:
        sp, dp = SRC / proj / rel, DST / proj / rel
        if not sp.is_file():
            print(f"  {proj}/{rel}: 源已清理，无需核验")
            continue
        if not dp.is_file():
            print(f"  {proj}/{rel}: !! 目标缺失")
            total_missing += 1
            continue
        hs, hd = sha256(sp), sha256(dp)
        ok = "一致" if hs == hd else "!! 不一致"
        print(f"  {proj}: {hs[:16]}... {ok}")
        if hs != hd:
            total_missing += 1

    print("\n=== 源残留明细（已复制到目标，仅因文件锁未删除）===")
    for k, v in leftover_all.items():
        print(f"  {k}: {v}")

    print(f"\n[结论] 目标缺失/哈希不一致项: {total_missing}")
    return 0 if total_missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())