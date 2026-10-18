# -*- coding: utf-8 -*-
r"""
scan_host_leak.py —— 「数据保存不对」宿主侧泄漏扫描（严格只读）

便携包的契约是：宿主零残留，用户数据全部落进包内 Data\。
本脚本检查宿主各常用落盘根下，是否存在「真实目录（非 junction）」——
真实目录 = 便携包没接管，数据写进了宿主。

覆盖根：
  %APPDATA% / %LOCALAPPDATA% / %LOCALAPPDATA%\Temp / %ProgramData%
  Documents（读注册表 Shell Folders\Personal，支持重定向）
  %USERPROFILE%

判据：
  junction / symlink → OK（已被便携包接管）
  真实目录 且 体积 > 阈值 → 疑似泄漏
  再按「已知软件厂商关键词」二次匹配，锁定属于哪个便携包

用法：
  python scan_host_leak.py                 # 默认 1MB 阈值
  python scan_host_leak.py --min-mb 10
  python scan_host_leak.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import winreg
from pathlib import Path

# ── 厂商关键词 → 便携包（用于把宿主目录归属到具体包）──────────────────
VENDOR_MAP = {
    "tencent": ["QQPortable", "TIMPortable", "QQNTPortable", "WeixinPortable",
                "WXWorkPortable", "WeMeetPortable"],
    "qq": ["QQPortable", "QQNTPortable"],
    "tencent files": ["QQPortable", "TIMPortable"],
    "tim": ["TIMPortable"],
    "wechat": ["WeixinPortable"],
    "weixin": ["WeixinPortable"],
    "wxwork": ["WXWorkPortable"],
    "wemeet": ["WeMeetPortable"],
    "kingsoft": ["WPSOfficePortable"],
    "wps": ["WPSOfficePortable"],
    "kdesktop": ["WPSOfficePortable"],
    "baidu": ["BaiduNetdiskPortable", "KukuAIPortable", "ComatePortable"],
    "baidunetdisk": ["BaiduNetdiskPortable"],
    "kukuai": ["KukuAIPortable"],
    "comate": ["ComatePortable"],
    "quark": ["QuarkCloudDrivePortable"],
    "feishu": ["FeishuPortable"],
    "lark": ["FeishuPortable"],
    "zoom": ["ZoomPortable"],
    "foxit": ["FoxitPDFPortable"],
    "typora": ["TyporaPortable"],
    "joplin": ["JoplinPortable"],
    "sublime": ["SublimeTextPortable"],
    "cursor": ["CursorPortable"],
    "trae": ["TraeCNPortable"],
    "qoder": ["QoderCNPortable", "QoderCNIDEPortable"],
    "workbuddy": ["WorkBuddyPortable"],
    "codebuddy": ["CodeBuddyCNPortable"],
    "codearts": ["CodeArtsPortable", "CodeArtsAgentPortable"],
    "cherry": ["CherryStudioPortable"],
    "aipy": ["AiPyProPortable"],
    "minimax": ["MiniMaxCodePortable"],
    "lobster": ["LobsterAIPortable"],
    "winclaw": ["WinClawPortable"],
    "joycode": ["JoyCodePortable"],
    "miaoshou": ["MiaoshouPortable"],
    "officeace": ["OfficeAcePortable"],
    "zen": ["ZenBrowserPortable"],
    "ediary": ["eDiaryPortable"],
    "renamer": ["ReNamerPortable"],
    "fscapture": ["FSCapturePortable"],
    "solomd": ["SoloMDPortable"],
    "todaycn": ["TodayCNPortable"],
    "xfolder": ["QQPortable", "TIMPortable"],
    "qimei": ["QQPortable", "TIMPortable", "QQNTPortable"],
}


def shell_folder(name: str) -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion"
                            r"\Explorer\Shell Folders") as k:
            return Path(winreg.QueryValueEx(k, name)[0])
    except Exception:
        return None


def dir_size(p: Path, cap_files: int = 4000) -> tuple[int, int, bool]:
    """返回 (字节数, 文件数, 是否达到采样上限)。"""
    total = 0
    n = 0
    capped = False
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
                    n += 1
                    if n >= cap_files:
                        capped = True
                        break
            except Exception:
                continue
    except Exception:
        pass
    return total, n, capped


def classify(name: str) -> list[str]:
    low = name.lower()
    hits = []
    for kw, pkgs in VENDOR_MAP.items():
        if kw in low:
            for pk in pkgs:
                if pk not in hits:
                    hits.append(pk)
    return hits


def scan_root(root: Path, label: str, min_mb: float, depth: int = 1) -> list[dict]:
    out = []
    if not root.exists():
        return out
    stack = [(root, 0)]
    while stack:
        cur, d = stack.pop()
        try:
            entries = sorted(cur.iterdir())
        except Exception:
            continue
        for e in entries:
            try:
                if not e.is_dir():
                    continue
                is_link = e.is_junction() or e.is_symlink()
            except Exception:
                continue
            if is_link:
                tgt = ""
                try:
                    tgt = str(os.readlink(e))
                except Exception:
                    pass
                out.append({"root": label, "path": str(e), "kind": "junction",
                            "target": tgt, "mb": 0, "pkgs": classify(e.name)})
                continue
            if d < depth:
                stack.append((e, d + 1))
                continue
            sz, n, capped = dir_size(e)
            mb = sz / 1024 / 1024
            if mb >= min_mb:
                out.append({"root": label, "path": str(e), "kind": "real",
                            "mb": round(mb, 1), "files": n, "capped": capped,
                            "pkgs": classify(e.name)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-mb", type=float, default=1.0)
    ap.add_argument("--json", default="")
    ap.add_argument("--depth", type=int, default=1, help="对未接管目录再下探几层")
    args = ap.parse_args()

    env = {k: os.environ.get(k, "") for k in
           ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "USERPROFILE", "TEMP")}
    docs = shell_folder("Personal")

    roots = [
        (Path(env["APPDATA"]), "%APPDATA%", 2),
        (Path(env["LOCALAPPDATA"]), "%LOCALAPPDATA%", 2),
        (Path(env["PROGRAMDATA"]), "%ProgramData%", 1),
        (docs, "Documents", 1) if docs else (Path(""), "", 0),
        (Path(env["USERPROFILE"]), "%USERPROFILE%", 0),
    ]

    all_rows = []
    for p, label, dep in roots:
        if not label or not p.exists():
            continue
        rows = scan_root(p, label, args.min_mb, depth=min(dep, args.depth))
        all_rows.extend(rows)
        print(f"# {label} = {p}  扫描到 {len(rows)} 项")

    junctions = [r for r in all_rows if r["kind"] == "junction"]
    real = sorted([r for r in all_rows if r["kind"] == "real"],
                  key=lambda x: -x["mb"])

    print(f"\n=== 已被便携包接管的 junction（{len(junctions)} 个，正常）===")
    for r in junctions:
        tag = ",".join(r["pkgs"]) if r["pkgs"] else "-"
        print(f"  [J] {r['path']}  -> {r['target']}   ({tag})")

    print(f"\n=== 疑似泄漏：宿主真实目录 > {args.min_mb}MB（{len(real)} 个）===")
    hit = 0
    for r in real:
        tag = ",".join(r["pkgs"]) if r["pkgs"] else ""
        mark = "  ★命中便携包" if tag else ""
        if tag:
            hit += 1
        sz = f">{r['mb']}MB(采样满)" if r["capped"] else f"{r['mb']}MB"
        print(f"  [R] {r['path']}  {sz}  files={r['files']}  {tag}{mark}")

    print(f"\n小结：命中便携包的疑似泄漏 {hit} 项 / 未识别真实目录 {len(real)-hit} 项")

    if args.json:
        Path(args.json).write_text(json.dumps(all_rows, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"JSON -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
