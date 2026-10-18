# -*- coding: utf-8 -*-
r"""toolchain.py —— 便携项目公共工具链定位器（各项目 scripts/ 引用）

【为什么需要】
早期 39 个项目把 PAL 工具链路径写死在各自的 build-portable.py 里
（MONO = REPO.parents[1]），换机器 / 换目录就失效。

【本模块的约定】
项目不硬编码任何绝对路径，改为按以下优先级解析工具链根目录：
  1. 环境变量 PAF_TOOLCHAIN（CI / 特殊构建可用）
  2. <项目>/../../_shared            （标准布局：<仓库根>/_shared）
  3. <项目>/../_shared               （项目直接平铺在仓库根下）
  4. <项目>/toolchain                （单项目自带工具链）
找不到时抛出带修复建议的异常，而不是静默回退到某个写死的路径。

注意：toolchain/ 目录内含第三方代码（PAL 为 GPL、NSIS 为 zlib 授权），
本仓库以 MIT 只开源「配方」，故该目录**不入库**（见根级 .gitignore §14）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 工具链根目录内需存在的标志文件
_MARKER = Path("toolchain") / "PortableApps.comLauncher" / "Other" / "Source"
_MARKER_ALT = Path("toolchain") / "PortableApps.comLauncher" / "App" / "NSIS" / "makensis.exe"

_HINT = """\
[toolchain] 未找到 PortableApps 工具链。

本项目需要 PortableApps.com Launcher 源码树（含 NSIS 与 Other\\Source）来编译启动器。
按以下任一方式提供：

  1) 推荐：把工具链放到仓库共享位置
     <仓库根>/_shared/toolchain/PortableApps.comLauncher/
     （本机默认位置，可由 git 仓库外的脚本/压缩包还原）

  2) 指定环境变量指向工具链根目录（该目录下需含 toolchain/ 子目录）：
     set PAF_TOOLCHAIN=<工具链根目录>

  3) 单项目自带：把工具链放到 <项目>/toolchain/ 下

注意：工具链是第三方代码（PAL 为 GPL、NSIS 为 zlib 授权），
本仓库以 MIT 只开源「配方」，故 toolchain/ 目录**不入库**，
克隆后需自行按上述方式放置。

如需重新获取官方工具链：
  https://portableapps.com/development/launcher/
"""


def find_toolchain(start: Path | None = None) -> Path:
    """返回工具链根目录（含 toolchain/ 子目录），找不到则抛异常。"""
    env = os.environ.get("PAF_TOOLCHAIN")
    candidates = []
    if env:
        candidates.append(Path(env))
    if start:
        base = Path(start).resolve()
        candidates += [
            base.parents[1] / "_shared",   # <项目>\scripts -> <仓库根>\_shared
            base.parent / "_shared",
            base / "toolchain",
        ]

    for c in candidates:
        try:
            c = c.resolve()
        except OSError:
            continue
        if (c / _MARKER).is_dir() or (c / _MARKER_ALT).is_file():
            return c
    sys.stderr.write(_HINT)
    raise FileNotFoundError("PortableApps 工具链未找到")


def pal_dir(toolchain: Path) -> Path:
    """PortableApps.com Launcher 源码树目录。"""
    return toolchain / "toolchain" / "PortableApps.comLauncher"


def build_launcher_script(toolchain: Path) -> Path:
    """公共启动器构建器脚本路径。"""
    return toolchain / "build_launcher.py"


def update_engine_script(toolchain: Path) -> Path:
    """公共更新引擎脚本路径。"""
    return toolchain / "update_engine.py"


def config_for(toolchain: Path, project: str) -> Path:
    """本项目的更新配置 yaml。"""
    return toolchain / "configs" / f"{project}.yaml"


if __name__ == "__main__":
    # 自检：python scripts/toolchain.py
    try:
        tc = find_toolchain(Path(__file__).resolve().parent)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
    print(f"[OK] 工具链根目录: {tc}")
    print(f"     PAL 源码树   : {pal_dir(tc)}")
    print(f"     启动器构建器 : {build_launcher_script(tc)}")
    print(f"     更新引擎     : {update_engine_script(tc)}")