# -*- coding: utf-8 -*-
"""fix_strip_bom.py —— 剥离 Custom.nsh 的 UTF-8 BOM

为什么必须修：
  NSIS 读到带 BOM 的 .nsh 会把 BOM 三字节当成首个 token，报
  `Invalid command`。本仓库 2026-10-18 结构自检首次抓到
  BaiduNetdiskPortable / CodeArtsAgentPortable 双树共 4 个文件带 BOM
  （此前的 check_custom_nsh.py 只查引号/管道病态，没查 BOM，属漏检）。

做法：备份 .bak-bom-<时间戳> → 字节级剥掉 EF BB BF → 校验 UTF-8 可解码
      → 报告「注释之外是否含非 ASCII」（若有，提醒人工确认）。

路径：源树（portableapps/，仓库内）+ 产品树（_paths.product_root()/*，
迁移后为 D:\\Portapps\\*，迁移前自动回退仓库内 dist）。两个 glob 按
realpath 去重，迁移前后各扫一遍都不会漏、不会重。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
PATS = [
    os.path.join(REPO_ROOT, "*", "dist", "*", "App", "AppInfo", "Launcher",
                 "Custom.nsh"),
    os.path.join(REPO_ROOT, "*", "portableapps", "App", "AppInfo", "Launcher",
                 "Custom.nsh"),
    # 迁移后的产品树（产品根不存在时 glob 自然为空，回到上面两条）
    os.path.join(str(_paths.product_root()), "*", "App", "AppInfo", "Launcher",
                 "Custom.nsh"),
]


def iter_nsh():
    """按 realpath 去重的 Custom.nsh 全量枚举。"""
    seen, out = set(), []
    for pat in PATS:
        for f in sorted(glob.glob(pat)):
            rp = os.path.realpath(f)
            if rp not in seen:
                seen.add(rp)
                out.append(f)
    return out


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
    for f in iter_nsh():
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
    print("剥离完成：%d 个文件（扫描范围：%d 个 Custom.nsh）"
          % (fixed, len(iter_nsh())))
    # 复核
    left = [f for f in iter_nsh()
            if Path(f).read_bytes()[:3] == b"\xef\xbb\xbf"]
    print("复核残留 BOM：%d" % len(left))
    return 1 if left else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
