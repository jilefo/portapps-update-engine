# -*- coding: utf-8 -*-
r"""fix_package_gitattributes.py —— 统一 39 个包级 .gitattributes

背景：每个包目录各有一份 .gitattributes（从样板 TyporaPortable 复制而来），
内容只有 `* text=auto eol=crlf` + 若干 binary 声明。

问题：git 规定**更深目录的 .gitattributes 优先于根级**。因此根级
`.gitattributes` 里的
    **/App/AppInfo/Launcher/*.ini  -text
（保护 UTF-16LE 的 Launcher ini 不被 autocrlf 改写）被包级的
`* text=auto eol=crlf` 完全压过 —— 已用 `git check-attr` 实测复现：
    仅根级规则  -> text: unset（保护生效）
    加了包级规则 -> text: auto （保护失效）

修法：在包级文件里补一行同义的例外规则。同一文件内后行覆盖前行，
所以必须放在 `* text=auto eol=crlf` **之后**。

顺带去掉了原来的 UTF-8 BOM（diff 里会显示成乱码）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TEMPLATE = """\
# 包级 .gitattributes
# 默认：自动识别文本，检出用 CRLF（Windows 上的 NSIS/PAL 工具链要 CRLF）
* text=auto eol=crlf

# 已知二进制
*.png binary
*.ico binary
*.bmp binary
*.gif binary
*.exe binary
*.dll binary
*.pak binary
*.bin binary
*.dat binary

# ★ 编码敏感：Launcher ini 可能是 UTF-16LE（含中文路径值时必须是），
#   行尾转换会毁掉它 → 按二进制处理。与根级 .gitattributes 同义。
#   注意：必须放在 `* text=auto eol=crlf` 之后，同文件内后行覆盖前行。
portableapps/App/AppInfo/Launcher/*.ini  -text
dist/{pkg}/App/AppInfo/Launcher/*.ini    -text
*.bakfix  -text
"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    n = 0
    for pkg_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()
                          and p.name.endswith("Portable")):
        target = pkg_dir / ".gitattributes"
        new = TEMPLATE.format(pkg=pkg_dir.name).encode("utf-8")
        old = target.read_bytes() if target.exists() else b""
        if old == new:
            continue
        if dry:
            print(f"[dry] {target}")
        else:
            target.write_bytes(new)
            print(f"[ok] {target}")
        n += 1
    print(f"\n{'将改写' if dry else '已改写'} {n} 个包级 .gitattributes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
