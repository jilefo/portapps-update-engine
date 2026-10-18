# -*- coding: utf-8 -*-
r"""_paths.py —— 「产品根」路径的唯一解析处。

背景
----
便携产物原本在仓库内：`<Repo>/<Pkg>/dist/<Pkg>/`。
2026-10-18 按任务书整体迁移到 `<产品根>/<Pkg>/`（默认 `D:\Portapps`），
于是仓库里 63 处 `.../dist/...` 路径假设全部失效。本模块把它们收敛到一处，
避免 33 个文件各写一份、下次再迁又要改 33 遍。

解析顺序（先命中先用）
----------------------
  1. 环境变量 `PORTAPPS_ROOT`（或别名 `PORTABLEAPPS_PRODUCT_ROOT`）
  2. 与本模块同级的 `portapps_root.txt`（第一行非注释内容）
  3. 内置默认 `DEFAULT_PRODUCT_ROOT`（迁移后为 `D:\Portapps`）
  4. **回退**：`<Repo>/<Pkg>/dist/<Pkg>`（未迁移的老布局）

⚠ 命名冲突警告：另有一批旧工具（enum_portable_projects.py 等）用
`PORTABLEAPPS_ROOT` 表示**仓库根**。因此产品根**故意不复用**这个名字，
改用 `PORTAPPS_ROOT` / `PORTABLEAPPS_PRODUCT_ROOT`，避免两个含义打架。

第 4 条是关键：迁移前不设任何变量时，`D:\Portapps` 不存在 → 自动回退到
仓库内老布局，工具链行为与改造前完全一致；迁移后 `D:\Portapps` 存在 →
自动切到新布局。**不需要改任何配置，两个状态都能跑。**

约定
----
  * 任何脚本都不要再写 `<Pkg>/dist/<Pkg>` 这类硬编码路径，一律调
    `product_dir(pkg)` / `product_root()`。
  * 仓库根 `REPO_ROOT` 仍由本文件位置推导，禁止写死绝对路径。
"""
from __future__ import annotations

import os
from pathlib import Path

# ------------------------------------------------------------------ 仓库根
REPO_ROOT = Path(__file__).resolve().parents[1]        # _shared/ -> 仓库根

# ------------------------------------------------------------------ 产品根
DEFAULT_PRODUCT_ROOT = Path(r"D:\Portapps")

_ENV_VARS = ("PORTAPPS_ROOT", "PORTABLEAPPS_PRODUCT_ROOT")
_FILE_NAME = "portapps_root.txt"


def _from_env():
    for v in _ENV_VARS:
        s = os.environ.get(v)
        if s:
            return Path(s)
    return None


def _from_file():
    """读 _shared/portapps_root.txt。格式：第一行非空且非 # 开头的内容。

    存在但读不出来时返回 None（不抛异常）——配置文件损坏不该让所有工具崩，
    而该让它回退到默认值并在 source() 里如实反映。
    """
    p = REPO_ROOT / "_shared" / _FILE_NAME
    if not p.is_file():
        return None
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                return Path(s)
    except OSError:
        return None
    return None


def product_root() -> Path:
    """产品根目录。解析失败（都不存在）时返回候选值而非 None，
    由调用方决定是否报错——但 source() 会说明它是猜的。"""
    for getter in (_from_env, _from_file):
        p = getter()
        if p is not None and p.is_dir():
            return p
    if DEFAULT_PRODUCT_ROOT.is_dir():
        return DEFAULT_PRODUCT_ROOT
    return DEFAULT_PRODUCT_ROOT          # 不存在，让调用方看到明确路径


def product_root_source() -> str:
    """说明当前产品根是哪儿来的。门禁要把这个打印出来，
    否则"明明是 D:\\Portapps 却读到老 dist"这类问题查都没法查。"""
    if _from_env() is not None:
        return "%s 环境变量" % " / ".join(_ENV_VARS)
    if _from_file() is not None:
        return "_shared/%s" % _FILE_NAME
    if DEFAULT_PRODUCT_ROOT.is_dir():
        return "内置默认值"
    return "内置默认值（该目录当前不存在，已回退仓库内 dist）"


def legacy_dist(pkg: str) -> Path:
    """迁移前的产品目录：<Repo>/<Pkg>/dist/<Pkg>。"""
    return REPO_ROOT / pkg / "dist" / pkg


def product_dir(pkg: str) -> Path:
    """产品目录。新布局优先，不存在则回退老布局。

    这是 63 处硬编码要替换成的唯一入口。
    """
    new = product_root() / pkg
    if new.is_dir():
        return new
    old = legacy_dist(pkg)
    if old.is_dir():
        return old
    return new


def product_tree_in_use(pkg: str) -> str:
    """供报告/门禁说明本包当前读的是哪棵树。"""
    new = product_root() / pkg
    if new.is_dir():
        return "new"
    if legacy_dist(pkg).is_dir():
        return "legacy"
    return "missing"


def repo_dist_parent(pkg: str) -> Path:
    """仓库内的 dist 父目录：<Repo>/<Pkg>/dist（迁移后通常为空或不存在）。"""
    return REPO_ROOT / pkg / "dist"


def artifact_root(pkg: str) -> Path:
    """打包产物的暂存根 = 产品目录的父目录。

    迁移前  -> <Repo>/<Pkg>/dist     （package-paf/gen-sbom 的老位置）
    迁移后  -> <产品根>               （zip / SHA256SUMS / sbom 与产品同级）
    两类产物都不进 git，放这里两边都不会污染仓库。
    """
    return product_dir(pkg).parent


def packages() -> list:
    """仓库根下真正的包：含 portableapps/ 或 dist/ 的一级目录。"""
    out = []
    for d in sorted(REPO_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if (d / "portableapps").is_dir() or (d / "dist").is_dir():
            out.append(d.name)
    return out


def custom_nsh_files() -> list:
    """全部产品树 Custom.nsh：[(包名, 路径)]。

    迁移后 <产品根>/<Pkg>/...，迁移前 <Repo>/<Pkg>/dist/<Pkg>/...，
    由 product_dir() 自动切换；产品树缺失的包不进列表（调用方据此报覆盖度）。
    """
    out = []
    for pkg in packages():
        p = product_dir(pkg) / "App" / "AppInfo" / "Launcher" / "Custom.nsh"
        if p.is_file():
            out.append((pkg, p))
    return out


if __name__ == "__main__":
    print("REPO_ROOT          :", REPO_ROOT)
    print("产品根             :", product_root())
    print("产品根来源         :", product_root_source())
    print("包数               :", len(packages()))
    for pkg in packages()[:3]:
        print("  %-24s -> %s  [%s]" % (pkg, product_dir(pkg),
                                       product_tree_in_use(pkg)))
