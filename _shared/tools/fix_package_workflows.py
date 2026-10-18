# -*- coding: utf-8 -*-
r"""fix_package_workflows.py —— 修正 111 个包级 GitHub Actions workflow

背景：每个包目录各有一份 .github/workflows/{ci,release,portableapps}.yml，
由 scaffold.py 的 COPY_FROM_TEMPLATE 复制生成，但**路径从未按仓库布局调整**：

  ci.yml            run: python tests/test_structure.py          ← tests/ 不存在
  release.yml       run: python scripts/build-portable.py        ← scripts/ 不在包内
  portableapps.yml  run: python scripts/build-portable.py

实际上：
  - 包内禁止建 scripts/ 与 tests/（仓库精简约定）
  - 通用脚本统一在 _shared/scripts/ 下
  - GitHub Actions 的 run: 工作目录是**仓库根**（$GITHUB_WORKSPACE），
    不是 workflow 文件所在目录，所以路径要从仓库根写、并显式传包名
    （_pkg.py 的推导优先级：命令行参数 > 当前目录名 > PAF_PKG）

修法（39 包 × 3 类 workflow，共 111 个文件）：
  tests/test_structure.py      -> _shared/scripts/test_structure.py <Pkg>
  scripts/build-portable.py    -> _shared/scripts/build-portable.py <Pkg>
  scripts/package-paf.py       -> _shared/scripts/package-paf.py <Pkg>
  dist/  (artifact 路径)       -> <Pkg>/dist/
  dist/*.7z / dist/SHA256SUMS  -> <Pkg>/dist/...
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 纯文本替换（顺序无关，互不重叠）
SUBS: list[tuple[str, str]] = [
    ("python tests/test_structure.py",
     "python _shared/scripts/test_structure.py {pkg}"),
    ("python scripts/build-portable.py",
     "python _shared/scripts/build-portable.py {pkg}"),
    ("python scripts/package-paf.py --checksum-only",
     "python _shared/scripts/package-paf.py {pkg} --checksum-only"),
    # 部分包（CherryStudio / KukuAI）用了不带参数的裸形式，单独覆盖
    ("python scripts/package-paf.py",
     "python _shared/scripts/package-paf.py {pkg}"),
    ("python scripts/gen-sbom.py",
     "python _shared/scripts/gen-sbom.py {pkg}"),
]

# YAML 结构替换：artifact path 与 release files
PATH_SUBS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(\s*)path:\s*dist/\s*$", re.M), r"\1path: {pkg}/dist/"),
    (re.compile(r"^(\s*)name:\s*(\S+)-dist\s*$", re.M), r"\1name: \2"),
]


def fix_text(t: str, pkg: str) -> tuple[str, int]:
    n = 0
    for old, new in SUBS:
        rep = new.format(pkg=pkg)
        c = t.count(old)
        if c:
            t = t.replace(old, rep)
            n += c
    for pat, rep in PATH_SUBS:
        rep2 = rep.format(pkg=pkg)
        t, k = pat.subn(rep2, t)
        n += k
    # release files 段：dist/*.7z、dist/SHA256SUMS、dist/*.zip、dist/sbom.spdx.json
    t2, k = re.subn(
        r"(?m)^(\s*)(dist/(?:\*\.7z|\*\.zip|SHA256SUMS|sbom\.spdx\.json))\s*$",
        lambda m: f"{m.group(1)}{pkg}/{m.group(2)}", t)
    n += k
    return t2, n


def main() -> int:
    dry = "--dry-run" in sys.argv
    changed = 0
    total = 0
    for pkg_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()
                          and p.name.endswith("Portable")):
        wf = pkg_dir / ".github" / "workflows"
        if not wf.is_dir():
            continue
        for yml in sorted(wf.glob("*.yml")):
            raw = yml.read_bytes()
            has_bom = raw[:3] == b"\xef\xbb\xbf"
            try:
                t = raw.decode("utf-8-sig" if has_bom else "utf-8")
            except UnicodeDecodeError:
                print(f"[skip] {yml} 非 UTF-8")
                continue
            new, n = fix_text(t, pkg_dir.name)
            if n == 0 or new == t:
                continue
            changed += 1
            total += n
            if dry:
                print(f"[dry] {yml}  ({n} 处)")
            else:
                data = new.encode("utf-8")
                if has_bom:
                    data = b"\xef\xbb\xbf" + data
                yml.write_bytes(data)
                print(f"[ok] {yml}  ({n} 处)")

    print(f"\n{'将修改' if dry else '已修改'} {changed} 个 workflow，共 {total} 处。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
