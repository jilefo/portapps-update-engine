# -*- coding: utf-8 -*-
"""fix_strip_bom.py —— 剥离 Custom.nsh 的 UTF-8 BOM

为什么必须修：
  NSIS 读到带 BOM 的 .nsh 会把 BOM 三字节当成首个 token，报
  `Invalid command`。本仓库 2026-10-18 结构自检首次抓到
  BaiduNetdiskPortable / CodeArtsAgentPortable 双树共 4 个文件带 BOM
  （此前的 check_custom_nsh.py 只查引号/管道病态，没查 BOM，属漏检）。

做法：备份 .bak-bom-<时间戳> → 字节级剥掉 EF BB BF → 校验 UTF-8 可解码
      → 报告「注释之外是否含非 ASCII」（若有，提醒人工确认）。
"""
import glob
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# >>> 路径自适应：仓库根由本文件位置推导
REPO_ROOT = os.environ.get("PORTABLEAPPS_ROOT") or str(
    Path(__file__).resolve().parents[2])
# <<< 路径自适应

STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
PATS = [
    os.path.join(REPO_ROOT, "*", "dist", "*", "App", "AppInfo", "Launcher",
                 "Custom.nsh"),
    os.path.join(REPO_ROOT, "*", "portableapps", "App", "AppInfo", "Launcher",
                 "Custom.nsh"),
]


def non_ascii_significant(text):
    hits = []
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if s.startswith(";") or s.startswith("#"):
            continue
        if any(ord(c) > 127 for c in ln):
            hits.append(i)
    return hits


def main():
    fixed = 0
    for pat in PATS:
        for f in sorted(glob.glob(pat)):
            raw = Path(f).read_bytes()
            if raw[:3] != b"\xef\xbb\xbf":
                continue
            bak = f + ".bak-bom-" + STAMP
            shutil.copy2(f, bak)
            body = raw[3:]
            text = body.decode("utf-8")  # 解不开就抛错，绝不写坏文件
            Path(f).write_bytes(body)
            hits = non_ascii_significant(text)
            rel = os.path.relpath(f, REPO_ROOT)
            print("  [FIXED] %s  %d -> %d 字节  备份=%s"
                  % (rel, len(raw), len(body), os.path.basename(bak)))
            if hits:
                print("      ⚠ 注释外含非 ASCII，行号 %s —— 请人工确认"
                      % hits[:5])
            fixed += 1
    print("剥离完成：%d 个文件" % fixed)
    # 复核
    left = []
    for pat in PATS:
        for f in glob.glob(pat):
            if Path(f).read_bytes()[:3] == b"\xef\xbb\xbf":
                left.append(f)
    print("复核残留 BOM：%d" % len(left))
    return 1 if left else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
