# -*- coding: utf-8 -*-
"""build-portable.py —— 构建 dist/ 便携包（通用版，包名自动推导）

流程：清理 dist/ → 复制 portableapps/ 源 → 编译启动器 → 结构校验。

工具链定位经toolchain.py 完成，不再硬编码 monorepo 绝对路径。
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toolchain import build_launcher_script, find_toolchain  # noqa: E402



DIST = REPO / "dist" / PKG
SRC = REPO / "portableapps"


def copy_source() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    for item in SRC.iterdir():
        dst = DIST / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)


def build_launcher() -> int:
    try:
        tc = find_toolchain(Path(__file__).resolve().parent)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 2
    builder = build_launcher_script(tc)
    if not builder.is_file():
        print(f"[FAIL] 缺少启动器构建器: {builder}", file=sys.stderr)
        return 2
    r = subprocess.run([sys.executable, str(builder), str(DIST)])
    return r.returncode


def verify() -> int:
    test = _Path(__file__).resolve().parent / "test_structure.py"
    if not test.is_file():
        return 0
    r = subprocess.run([sys.executable, str(test)])
    return r.returncode


def main() -> int:
    if not SRC.is_dir():
        print(f"[FAIL] 缺portableapps/ 源目录: {SRC}")
        return 1
    print(f"[1/3] 复制 portableapps/ -> dist/{PKG}")
    copy_source()
    print("[2/3] 编译 PortableApps 启动器")
    rc = build_launcher()
    if rc != 0:
        print(f"[FAIL] 启动器编译失败 rc={rc}")
        return rc
    print("[3/3] 结构校验")
    if verify() != 0:
        print("[WARN] 结构校验未通过，请检查上面的输出")
    print(f"[OK] 构建完成: {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
