# -*- coding: utf-8 -*-
"""audit_before_push.py —— 开源推送前的最后一道自检。

1. 用 git add -A --dry-run 取「真正会被追踪的文件」清单（尊重 .gitignore）
2. 统计总体积 / 最大单文件
3. 扫描文本文件里的本机绝对路径与疑似凭证
4. 报告 UTF-16LE / UTF-8 BOM 分布（验证 .gitattributes 覆盖是否到位）
5. 校验关键 .gitattributes 规则名存在

用法：python audit_before_push.py [仓库根]
"""
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    # 仓库根由脚本位置推导（tools/ -> _shared/ -> 仓库根），不写死
    ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[2]

    # 扫描器自身的 pattern 文本会自我命中 → 自排除
    # （audit_pre_release.py / quarantine_junk.py / release.py 里都有
    #  `SECRET = re.compile(...)`、`LEAK = re.compile(...)` 这类字面量，
    #   会被 SECRET_CFG / LEAK 自己命中；不排就是假阳性）
    SELF = {Path(__file__).name, "sanitize_paths.py",
            "audit_pre_release.py", "quarantine_junk.py", "release.py"}

    # ── 1. 取真实入库清单 ──────────────────────────────────────
    # ★ 早先只取 `git add -A --dry-run` 的**未跟踪**文件，于是改动一个
    #   已跟踪文件、往里塞本机路径，门禁看不见——覆盖面虚报。
    #   现在取「已跟踪」与「将要新增」的并集，两者分别计数上报。
    out = subprocess.run(["git", "add", "-A", "--dry-run"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    added = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("add '"):
            added.append(line[5:].rstrip("'"))
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT,
                             capture_output=True, text=True,
                             encoding="utf-8").stdout.splitlines()
    tracked = [t for t in tracked if t.strip()]
    paths = list(dict.fromkeys(added + tracked))     # 保序去重

    # ── 2. 体积 ─────────────────────────────────────────────────
    total = 0
    big = []
    for p in paths:
        fp = ROOT / p.replace("/", os.sep)
        try:
            sz = fp.stat().st_size
        except OSError:
            continue
        total += sz
        if sz > 1024 * 1024:
            big.append((sz, p))

    print("=" * 74)
    print("开源前自检 —— git 实际会追踪的内容")
    print("=" * 74)
    print(f"文件数        : {len(paths)}"
          f"（已跟踪 {len(tracked)} + 待新增 {len(added)}）")
    print(f"总体积        : {total / 1024 / 1024:.2f} MB")
    print(f"最大单文件    : {max((s for s, _ in big), default=0) / 1024 / 1024:.2f} MB"
          f"（>1MB 的文件共 {len(big)} 个）")
    for sz, p in sorted(big, reverse=True)[:10]:
        print(f"    {sz / 1024 / 1024:8.2f} MB  {p}")
    print()

    # ── 3. 泄漏扫描 ────────────────────────────────────────────
    # 只报「真实本机路径」。以下两种情况**不算泄漏**，是文档里有意的写法：
    #   a) C:\Users\<你>\.xxx  —— 泛化示例（占位符 <...>）
    #   b) Find=C:\Users\     —— PAL 的 FileWrite 功能指令本身
    LEAK = re.compile(r"[A-Za-z]:\\(Projects|DevTools|Work)\b|/d/Projects")
    RE_USER = re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9_.\-]+\\")
    SECRET = re.compile(
        r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")
    SECRET_CFG = re.compile(
        r"^\s*(password|passwd|secret|api[_-]?key)\s*[:=]\s*\S",
        re.IGNORECASE | re.MULTILINE)
    SKIP_BIN = {".png", ".ico", ".bmp", ".gif", ".exe", ".bin", ".dll",
                ".pdf", ".zip", ".7z", ".pak", ".jpg", ".jpeg"}

    leaks = Counter()
    secrets = Counter()
    scanned = 0
    for p in paths:
        if Path(p).name in SELF:
            continue
        if Path(p).suffix.lower() in SKIP_BIN:
            continue
        fp = ROOT / p.replace("/", os.sep)
        try:
            t = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for _ in LEAK.finditer(t):
            leaks[p] += 1
        for _ in LEAK.finditer(t):
            leaks[p] += 1
        for _ in RE_USER.finditer(t):
            leaks[p] += 1
        for _ in SECRET.finditer(t):
            secrets[p] += 1
        for _ in SECRET_CFG.finditer(t):
            secrets[p] += 1

    print(f"扫描文本文件  : {scanned} 个")
    print(f"本机路径泄漏  : {sum(leaks.values())} 处")
    for p, n in leaks.most_common():
        print(f"    {n:3d}  {p}")
    print(f"疑似凭证      : {sum(secrets.values())} 处")
    for p, n in secrets.most_common():
        print(f"    {n:3d}  {p}")
    print()

    # ── 4. 编码分布 ────────────────────────────────────────────
    u16, bom = [], []
    for p in paths:
        fp = ROOT / p.replace("/", os.sep)
        try:
            head = fp.open("rb").read(3)
        except OSError:
            continue
        if head[:2] in (b"\xff\xfe", b"\xfe\xff"):
            u16.append(p)
        elif head == b"\xef\xbb\xbf":
            bom.append(p)

    print(f"UTF-16LE/BE   : {len(u16)} 个")
    for p in u16:
        print(f"    {p}")
    print(f"UTF-8 BOM     : {len(bom)} 个（不影响 git，属既有文风）")
    print()

    # ── 5. 结论 ────────────────────────────────────────────────
    problems = []
    if sum(leaks.values()):
        problems.append("存在本机绝对路径泄漏")
    if sum(secrets.values()):
        problems.append("存在疑似凭证")
    if big and max(s for s, _ in big) > 100 * 1024 * 1024:
        problems.append("存在 >100MB 单文件（GitHub 硬限）")
    if total > 1024 * 1024 * 1024:
        problems.append("仓库 >1GB（GitHub 建议上限）")

    print("=" * 74)
    if problems:
        print("结论：**暂不建议推送**，待处理：")
        for x in problems:
            print("  -", x)
    else:
        print("结论：可以推送。体积远低于 GitHub（建议 <1GB / 单文件 <100MB）"
              "与 Gitee（社区版单仓库 500MB / 单文件 50MB）限制。")
    print("=" * 74)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
