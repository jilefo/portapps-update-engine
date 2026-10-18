# -*- coding: utf-8 -*-
"""build-portable.py —— 构建便携包产物（通用版，包名自动推导）

流程：清理产物目录 → 复制 portableapps/ 源 → 编译启动器 → 结构校验。

产物位置由 _paths.product_dir() 决定：
  迁移后  -> <产品根>/<Pkg>（默认 D:\\Portapps\\<Pkg>）
  未迁移  -> <Repo>/<Pkg>/dist/<Pkg>（自动回退，行为与改造前一致）
两种状态都不需要改任何配置。

工具链定位经 toolchain.py 完成，不再硬编码 monorepo 绝对路径。
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402
import _paths                          # noqa: E402

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toolchain import build_launcher_script, find_toolchain  # noqa: E402



DIST = _paths.product_dir(PKG)
SRC = REPO / "portableapps"


def copy_source() -> None:
    # ★ 数据保护：Data/ 是运行期产生的用户数据，源树 portableapps/ 里没有它，
    #   重建只是重装「配方」。早期版本直接 rmtree(DIST) 把 Data/ 一起端了，
    #   等于每次构建清空一次用户数据；迁移后产物目录在仓库外、是唯一副本，
    #   这个脚会变成数据销毁工具。故：只删配方部分，Data/ 原样保留。
    KEEP = "Data"
    if DIST.exists():
        for item in DIST.iterdir():
            if item.name == KEEP and item.is_dir():
                print(f"    [保留] {item}（用户数据不参与重建）")
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    DIST.mkdir(parents=True, exist_ok=True)
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
    print(f"[1/3] 复制 portableapps/ -> {DIST}（产品根：{_paths.product_root()}）")
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
