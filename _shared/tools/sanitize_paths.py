# -*- coding: utf-8 -*-
r"""sanitize_paths.py —— 把待入库文件里的本机绝对路径替换为中性占位符。

适用范围：注释、文档、docstring、历史报告等「叙述性」内容。
功能代码里的硬编码路径已在别处手工改为按 __file__ 推导，不依赖本脚本。

安全约束：
  - 检测到 UTF-16LE 的文件**直接跳过**（仓库铁律：不转码）
  - 保留原文件的 UTF-8 BOM（有则写回时带回）
  - `C:\Users\<...>`（示例占位）与 `Find=C:\Users\`（PAL 功能指令）不动

用法：
  python sanitize_paths.py --dry-run    # 只列将改动的行
  python sanitize_paths.py              # 落地
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _p(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE)


# 顺序即优先级：先具体后兜底
REPLACE: list[tuple[re.Pattern, str]] = [
    # 仓库根（当前）
    (_p(r"[Dd]:\\Projects\\PortableApps(?=[\\/])"), "<仓库根>"),
    (_p(r"[Dd]:/Projects/PortableApps(?=/)"), "<仓库根>"),
    # 旧工作区（迁移前）
    (_p(r"[Dd]:\\Projects\\GreenSoftMake\\Work(?=[\\/])"), "<旧工作区>"),
    (_p(r"[Dd]:\\Projects\\GreenSoftMake(?=[\\/])"), "<旧工作区>"),
    (_p(r"[Dd]:/Projects/GreenSoftMake(?=/)"), "<旧工作区>"),
    # 本机工具目录
    (_p(r"[Dd]:\\DevTools(?=[\\/])"), "<本机工具目录>"),
    (_p(r"[Dd]:/DevTools(?=/)"), "<本机工具目录>"),
    # Git-Bash 风格
    (_p(r"/d/Projects/PortableApps(?=/)"), "<仓库根>"),
    (_p(r"/d/Projects/GreenSoftMake(?=/)"), "<旧工作区>"),
    (_p(r"/d/Projects(?=/)"), "<旧工作区>"),
    # 兜底：其余 D:\Projects（含无下级的「迁移到 D:\Projects 后」）
    (_p(r"[Dd]:\\Projects(?=[\\/]|\b)"), "< Projects >"),
    (_p(r"[Dd]:/Projects(?=/|\b)"), "< Projects >"),
]

# 真实用户目录（含真实用户名）→ %USERPROFILE%
# 说明：`C:\Users\<你>` 这种占位不会匹配（[A-Za-z0-9_.-]+ 不认 `<`），
#       `Find=C:\Users\` 后面没有用户名，也不会匹配 —— 两者都是有意保留的。
RE_USER = re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9_.\-]+\\")


def has_bom(b: bytes) -> bool:
    return b[:3] == b"\xef\xbb\xbf"


def is_utf16(b: bytes) -> bool:
    return b[:2] in (b"\xff\xfe", b"\xfe\xff")


def sanitize_text(t: str) -> tuple[str, int]:
    """返回 (新文本, 替换次数)。"""
    n = 0
    for pat, rep in REPLACE:
        t, k = pat.subn(rep, t)
        n += k
    t, k = RE_USER.subn(lambda _m: "%USERPROFILE%\\", t)
    n += k
    return t, n


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "add", "-A", "--dry-run"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    return [l.strip()[5:].rstrip("'") for l in out.stdout.splitlines()
            if l.strip().startswith("add '")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    changed = 0
    total_hits = 0
    skipped_u16 = 0
    self_name = Path(__file__).name          # 本脚本的 pattern 表含路径字面量，自排除
    for rel in tracked_files():
        if Path(rel).name == self_name:
            continue
        fp = ROOT / rel.replace("/", "\\")
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        if is_utf16(raw):          # 编码敏感，铁律：不转码、不改写
            skipped_u16 += 1
            continue
        bom = has_bom(raw)
        try:
            t = raw.decode("utf-8-sig" if bom else "utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        new, hits = sanitize_text(t)
        if hits == 0 or new == t:
            continue
        changed += 1
        total_hits += hits
        if args.dry_run:
            for i, (a, b) in enumerate(zip(t.splitlines(), new.splitlines()), 1):
                if a != b:
                    print(f"  {rel}:{i}")
                    print(f"    - {a.strip()[:110]}")
                    print(f"    + {b.strip()[:110]}")
        else:
            data = new.encode("utf-8")
            if bom:
                data = b"\xef\xbb\xbf" + data
            fp.write_bytes(data)
            print(f"[ok] {rel}  ({hits} 处)")

    print(f"\n{'将修改' if args.dry_run else '已修改'} {changed} 个文件，"
          f"共 {total_hits} 处路径；跳过 UTF-16LE 文件 {skipped_u16} 个。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
