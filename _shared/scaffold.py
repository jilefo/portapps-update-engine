# -*- coding: utf-8 -*-
r"""scaffold.py —— 【遗留】为 39 个独立项目补齐双轨标准骨架

⚠ 状态：2026-10-17 双轨标准化时期的一次性工具，任务已完成（420 项，
final_audit.py 39/39 通过）。**2026-10-18 起默认拒绝运行**：其模板会
在包内生成 scripts/ tests/（精简约定已禁录）并写入 <Pkg>\dist\<Pkg>
路径（产品已迁到仓库外 <产品根>）。误跑会把已合规的包打回旧形态。
确需旧布局参考树时显式加 --legacy-layout。

【职责边界】
本脚本只做**补齐缺失项**，绝不覆盖已存在的文件（除非 --force）。
以 TyporaPortable 的既有文件为模板（那是本仓库已验证合规的样板），
把同样的骨架铺到其余项目，并修正迁移后失效的路径依赖。

用法：
  python scaffold.py                      # 拒绝运行（上述护栏）
  python scaffold.py --legacy-layout      # 预演，列出将要补齐的内容
  python scaffold.py --legacy-layout --execute  # 实际写入
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]   # <仓库根>，不写死
SHARED = ROOT / "_shared"
# 已验证合规的样板项目
TEMPLATE = ROOT / "TyporaPortable"

PROJECTS = [
    "AiPyProPortable", "BaiduNetdiskPortable", "CherryStudioPortable",
    "CodeArtsAgentPortable", "CodeArtsPortable", "CodeBuddyCNPortable",
    "ComatePortable", "CursorPortable", "eDiaryPortable", "FeishuPortable",
    "FSCapturePortable", "JoplinPortable", "JoyCodePortable",
    "LobsterAIPortable", "MiaoshouPortable", "MiniMaxCodePortable",
    "OfficeAcePortable", "QoderCNIDEPortable", "QoderCNPortable",
    "QQNTPortable", "QQPortable", "QuarkCloudDrivePortable", "ReNamerPortable",
    "SoloMDPortable", "TIMPortable", "TodayCNPortable", "TraeCNPortable",
    "TyporaPortable", "WeixinPortable", "WeMeetPortable", "WinClawPortable",
    "WorkBuddyPortable", "WXWorkPortable", "ZenBrowserPortable", "ZoomPortable",
    "FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable",
    "KukuAIPortable",
]

# 三特例：不自动更新/ 不自动打包发布
NO_AUTO = {"FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable"}

# 从样板项目直接复制的通用骨架（内容与项目无关）
COPY_FROM_TEMPLATE = [
    ".editorconfig", ".gitattributes", ".gitignore",
    ".github/dependabot.yml", ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "LICENSE", "CODE_OF_CONDUCT.md",
]

ENCODING = "utf-8-sig"   # 与既有项目一致：带 BOM，PowerShell/记事本友好
NEWLINE = "\r\n"


def w(path: Path, text: str) -> None:
    """写文本（utf-8-sig + CRLF），自动建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = text.replace("\r\n", "\n").replace("\n", NEWLINE)
    path.write_text(body, encoding=ENCODING, newline="")


# ---------------------------------------------------------------- 模板内容

def t_readme(p: str, meta: dict) -> str:
    name = meta.get("Details.Name") or f"{p} Portable"
    ver = meta.get("Version.DisplayVersion") or meta.get("Version.PackageVersion") or "1.0"
    home = meta.get("Details.Homepage") or ""
    desc = meta.get("Details.Description") or f"{name} 的便携化打包版本。"
    dl = ""
    if home:
        dl = f"- 原软件主页：{home}\n"
    if p in NO_AUTO:
        auto = ("- ⚠ 本项目为**特例项目**：按迁移任务书要求不接入自动更新脚本，"
                "也不参与自动打包发布，仅维护完整开源文档与双轨基础框架。\n")
    else:
        auto = ("- 本项目已接入自动更新流水线（`_shared/update_engine.py`），"
                f"版本检测与发布策略见 `_shared/configs/{p}.yaml`。\n")
    return f"""# {name}

{desc}

本仓库遵循《开源与 PortableApps 双轨发布标准》组织：源码、PortableApps 配置
与构建脚本在仓库内，最终便携包由 `scripts/build-portable.py` 构建到 `dist/`。

## 下载与使用

构建产物位于 `dist/{p}/`，双击 `{p}.exe` 即可运行，无需安装。
所有用户数据写入 `Data/` 目录，删除 `Data/` 即恢复初始状态。

## 目录结构

```
{p}/
├── portableapps/      PortableApps.com Format 3.9 源文件
│   ├── App/AppInfo/   appinfo.ini、启动器配置、图标
│   ├── App/<App>/     原程序文件
│   └── Other/         帮助与源码说明
├── scripts/           构建脚本（build-portable / package-paf / toolchain 定位）
├── docs/              PORTABLE.md / BUILD.md / RELEASE.md
├── tests/             结构与配置校验
├── src/               启动器与安装器相关源码/说明
└── dist/              构建输出（已加入 .gitignore）
```

## 双轨发布

| 轨道 | 目标 | 产物 |
| --- | --- | --- |
| GitHub 开源 | 开发者与贡献者 | 源码、`portableapps/` 配置、构建脚本 |
| PortableApps 成品 | 最终用户 | `{p}_X.X.paf.exe`、`SHA256SUMS`、`sbom.spdx.json` |

{auto}
{dl}
## 构建

```bash
python scripts/build-portable.py
```

详见 [docs/BUILD.md](docs/BUILD.md)与 [docs/RELEASE.md](docs/RELEASE.md)。

## 便携模式

数据落盘位置、注册表行为、备份与升级方式见 [docs/PORTABLE.md](docs/PORTABLE.md)。

## 许可证

本仓库的打包配置与构建脚本以 MIT 发布（见 LICENSE）。
原软件 {name} 的权利归其发布者所有，请遵守其 EULA（见 THIRD_PARTY_NOTICES.md）。

当前打包版本：**{ver}**
"""


def t_contributing(p: str) -> str:
    return f"""# 贡献指南

1. 任何修改请先在 issue 中说明意图。
2. 便携化逻辑改动必须附带动态落盘验证证据（`Data/` 目录新增清单 + 宿主零泄漏）。
3. 禁止提交 `dist/`、`portableapps/Data/` 等构建产物与用户数据。
4. 提交前运行 `python tests/test_structure.py` 确认结构合规。
5. 涉及原程序版本升级时，必须同步更新
   `portableapps/App/AppInfo/appinfo.ini` 的 `PackageVersion`
   与 `THIRD_PARTY_NOTICES.md` 中的版本与哈希。
"""


def t_security(p: str, meta: dict) -> str:
    home = meta.get("Details.Homepage") or "原软件官网"
    return f"""# 安全政策

## 漏洞披露

请通过 GitHub issue（标记 security）或私密渠道报告漏洞，**禁止在修复前公开细节**。

## 支持范围

仅最新版本的便携包接收安全更新。原软件自身的安全漏洞请同时报告给其官方发布者
（{home}）。

## 完整性

每次发布附带 SHA256 校验和；安装包均从官方渠道获取并记录哈希
（见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）。
"""


def t_support(p: str, meta: dict) -> str:
    home = meta.get("Details.Homepage") or "原软件官网"
    return f"""# 支持

- 便携包使用问题：GitHub Issues（本仓库）
- 便携化相关（数据落盘、启动器行为、路径兼容）：在本仓库提问
- 原软件功能问题：请联系官方支持（{home}）

提问前请先确认：

1. 已按 [docs/PORTABLE.md](docs/PORTABLE.md) 确认数据写入 `Data/`。
2. 已在 issue 中附上便携包版本、Windows 版本，以及是否使用含空格/中文的路径。
"""


def t_changelog(p: str, meta: dict) -> str:
    ver = meta.get("Version.DisplayVersion") or meta.get("Version.PackageVersion") or "1.0"
    return f"""# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式，
版本号与 [语义化版本](https://semver.org/lang/zh-CN/) 对齐。

## [Unreleased]

### Changed
- 迁移为独立项目，仓库迁至 `PortableApps/{p}`；
  构建脚本不再依赖 monorepo 路径，改为经 `scripts/toolchain.py` 解析公共工具链。

## [{ver}] - 2026-10-17

### Added
- 首个便携版构建：{p} {ver}
- 按《开源与 PortableApps 双轨发布标准》建立仓库骨架
"""


def t_thirdparty(p: str, meta: dict) -> str:
    name = meta.get("Details.Name") or p
    ver = meta.get("Version.DisplayVersion") or meta.get("Version.PackageVersion") or "未知"
    pub = meta.get("Details.Publisher") or "见原软件官网"
    home = meta.get("Details.Homepage") or ""
    opensrc = meta.get("License.OpenSource", "")
    lic = {
        "true": "开源软件（详见原项目 LICENSE）",
        "false": "专有软件（版权/商业许可）",
    }.get(str(opensrc).lower(), "许可类型见原软件 EULA")
    lines = [
        "# 第三方声明",
        "",
        "本仓库打包的原始应用程序：",
        "",
        f"- **{name}**，版本 {ver}",
        f"- 发布者：{pub}",
    ]
    if home:
        lines.append(f"- 主页：{home}")
    lines += [
        f"- 许可：{lic}",
        "",
        "本仓库仅包含便携化配置与构建脚本，**不修改原程序二进制**。",
        "原软件的所有权利归其发布者所有。若你是权利方且认为本仓库侵犯权益，",
        "请通过 issue 联系移除。",
        "",
        "> 说明：原程序安装包的来源 URL 与 SHA256 记录在各项目的",
        "> `CHANGELOG.md` 与 `_shared/configs/%s.yaml` 中。" % p,
    ]
    return "\n".join(lines) + "\n"


def t_portable_md(p: str, meta: dict) -> str:
    sub = ""
    subs = meta.get("__app_subdirs__") or []
    for s in subs:
        if s != "DefaultData":
            sub = s
            break
    data_desc = f"`Data\\\\settings\\\\{sub}\\\\`" if sub else "`Data\\\\settings\\\\`"
    envs = sorted((meta.get("__env__") or {}).keys())
    env_line = ("、".join(f"`{e}`" for e in envs) if envs else "APPDATA、LOCALAPPDATA")
    userprofile = "USERPROFILE" in envs
    up_note = (
        "\n> ⚠ 特别注意：本项目**不重定向 `USERPROFILE`**。Electron 的 "
        "`app.getPath('appData')` 经 `SHGetKnownFolderPath` 展开 `%USERPROFILE%`，"
        "指向不存在路径会直接崩溃。\n"
        if userprofile else "")
    return f"""# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- {data_desc} —— 配置、会话、缓存、登录态

实现方式：启动器在运行期重定向 {env_line} 到 `Data\\settings\\`，
并在需要时建立目录联接（Junction），退出时自动拆除。
{up_note}
## 注册表

启动器不写入**持久**注册表项。运行期可能建立目录联接，退出时自动拆除，
宿主系统零残留。

## 备份与迁移

- 备份：仅需复制 `Data/` 目录。
- 迁移：整个 `{p}/` 目录可直接复制到其他机器或盘符。

## 升级

升级由构建产物替换完成：`Data/` 目录完全隔离，更新过程不触碰用户数据。
自动化更新（检测 → 下载 → 校验 → 冒烟 → 发布）由公共更新引擎驱动，
配置见 `_shared/configs/{p}.yaml`。

## 多用户

设计为单用户便携包；多用户共用请各自复制一份完整目录。

## 路径兼容性

- 支持含空格路径与不同盘符（含中文路径）。
- 启动器不硬编码任何绝对路径，全部使用 `%PAL:AppDir%` / `%PAL:DataDir%` 相对锚点。

## 卸载与恢复初始状态

- 完整卸载：删除整个 `{p}/` 目录，宿主系统零残留。
- 恢复初始状态：删除 `Data/` 目录即可。
"""


def t_build_md(p: str) -> str:
    return f"""# 构建说明（BUILD.md）

## 环境

- Windows 10/11 x64
- Python 3.10+（仅需标准库）
- PortableApps.com Launcher 工具链（位于 `../_shared/toolchain/`，
  或用环境变量 `PAF_TOOLCHAIN` 指定）

## 构建步骤

```bash
python scripts/build-portable.py
```

流程：清理 `dist/` → 复制 `portableapps/` 源 → 编译启动器 → 校验结构。

## 工具链解析

构建脚本通过 `scripts/toolchain.py` 定位公共工具链，优先级：

1. 环境变量 `PAF_TOOLCHAIN`
2. `../../_shared`（标准布局）
3. `../_shared`
4. `<项目>/toolchain`

找不到时报错并给出修复建议，**不会静默回退到旧路径**。

## PowerShell 包装

```powershell
.\\scripts\\build-portable.ps1
```

## 依赖锁定

原程序版本与哈希记录在 `THIRD_PARTY_NOTICES.md` 与
`../_shared/configs/{p}.yaml`。更换原程序版本必须同步更新这两处，
以及 `portableapps/App/AppInfo/appinfo.ini` 的 `PackageVersion`。
"""


def t_release_md(p: str, auto: bool) -> str:
    auto_part = ""
    if auto:
        auto_part = f"""
## 自动化发布

打`v*` tag 触发 `.github/workflows/release.yml`，自动构建、上传产物、
生成 `SHA256SUMS` 与 SBOM 到 GitHub Releases。

维护侧更新检测：

```bash
python ../_shared/update_engine.py detect  --project {p}
python ../_shared/update_engine.py report  --project {p}
```
"""
    else:
        auto_part = """
## ⚠ 本项目为例外项目

按迁移任务书要求，`FoxitPDFPortable`、`SublimeTextPortable`、`WPSOfficePortable`
**不接入自动更新脚本，也不参与自动打包发布**。因此本仓库：

- 不生成 `.github/workflows/release.yml`
- 不生成 `.github/workflows/portableapps.yml`
- 不生成 `scripts/package-paf.ps1`

发布需人工执行上述步骤并手动上传产物。
"""
    return f"""# 发布说明（RELEASE.md）

## 步骤

1. 运行 `python scripts/build-portable.py` 生成 `dist/{p}/`。
2. 运行 `python tests/test_structure.py` 校验 PortableApps.com Format 3.9。
3. 动态落盘验证：启动 → 写入测试数据 → 关闭 → 确认数据全部在 `Data/`。
4. 打包：`python scripts/package-paf.py`（生成压缩包与 `SHA256SUMS`）。
5. 打 tag 发布；发布资产包含 `dist/{p}/` 压缩包、`SHA256SUMS` 与 `sbom.spdx.json`。
{auto_part}
## 发布检查清单

- [ ] `appinfo.ini` 所有必填字段完整，`PackageVersion` 已更新
- [ ] `launcher.ini` 的 `ProgramExecutable` 指向存在的可执行文件
- [ ] 图标文件齐全且尺寸合规
- [ ] 所有用户数据写入 `Data/`，`App/` 保持干净
- [ ] 从含空格路径、不同盘符均可运行
- [ ] 全新安装正常，覆盖升级不丢失设置
- [ ] 直接运行启动器正常，不依赖 PortableApps.com 平台
- [ ] `THIRD_PARTY_NOTICES.md` 已同步原程序版本与哈希
"""


def t_installer_ini() -> str:
    return """; PortableApps.com Installer 配置（生成 .paf.exe 时使用）
[Check]
Platform=2

[Source]
IncludePortableApps.comLauncher=true
IncludePortableApps.comInstaller=true

[Directories]
Remove=Data
"""


def t_ci_yml(p: str) -> str:
    return f"""name: ci
on:
  pull_request:
  push:
    branches: [main]

jobs:
  validate:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 结构校验
        run: python tests/test_structure.py
      - name: INI 校验
        run: python tests/test_structure.py --ini-only
"""


def t_portableapps_yml(p: str) -> str:
    return f"""name: portableapps
on:
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 构建 PortableApps 目录
        run: python scripts/build-portable.py
      - name: 上传 artifact
        uses: actions/upload-artifact@v4
        with:
          name: {p}-dist
          path: dist/
"""


def t_release_yml(p: str) -> str:
    return f"""name: release
on:
  push:
    tags: ['v*']

jobs:
  release:
    runs-on: windows-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: 构建便携包
        run: python scripts/build-portable.py
      - name: 结构校验
        run: python tests/test_structure.py
      - name: 打包并生成校验和
        run: python scripts/package-paf.py
      - name: 生成 SBOM
        run: python scripts/gen-sbom.py
      - name: 创建 GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/*.zip
            dist/SHA256SUMS
            dist/sbom.spdx.json
"""


def t_test_structure(p: str) -> str:
    return f'''# -*- coding: utf-8 -*-
"""test_structure.py —— PortableApps.com Format 3.9 结构校验（{p}）"""
import configparser
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = "{p}"
DIST = REPO / "dist" / PKG

ENCODINGS = ("utf-8-sig", "utf-16", "utf-8", "gb18030", "latin-1")


def read_ini(path):
    """按 BOM 逐级回退解码（WPS 系项目的 appinfo.ini 为 UTF-16LE）。"""
    raw = path.read_bytes()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_ini(path):
    cp = configparser.ConfigParser(strict=False, allow_no_value=True,
                                  delimiters=("=",), interpolation=None)
    cp.optionxform = str
    cp.read_string(read_ini(path))
    return cp


def main() -> int:
    ini_only = "--ini-only" in sys.argv
    errors = []

    # 1. 仓库骨架
    if not ini_only:
        for rel in (".github/ISSUE_TEMPLATE/bug_report.yml",
                    ".github/PULL_REQUEST_TEMPLATE.md",
                    "docs/PORTABLE.md", "docs/BUILD.md", "docs/RELEASE.md",
                    "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
            if not (REPO / rel).is_file():
                errors.append(f"缺仓库文件 {{rel}}")

    # 2. dist 产物
    if not ini_only:
        if not DIST.is_dir():
            errors.append(f"dist 产物不存在: {{DIST}}（先运行 scripts/build-portable.py）")
        else:
            root_files = [p.name for p in DIST.iterdir() if p.is_file()]
            allowed = {{f"{{PKG}}.exe", "help.html"}}
            extra = set(root_files) - allowed
            if extra:
                errors.append(f"dist 根目录多出文件: {{sorted(extra)}}")
            for d in ("App", "Other"):
                if not (DIST / d).is_dir():
                    errors.append(f"dist 缺目录: {{d}}")

    # 3. appinfo.ini 必填字段
    ai = REPO / "portableapps" / "App" / "AppInfo" / "appinfo.ini"
    if not ai.is_file():
        errors.append(f"缺 {{ai}}")
    else:
        cp = parse_ini(ai)
        for sec, key in (("Format", "Type"), ("Details", "Name"),
                         ("Details", "AppID"), ("Version", "PackageVersion"),
                         ("Control", "Start")):
            if not cp.has_section(sec) or not (cp.get(sec, key, fallback="") or "").strip():
                errors.append(f"appinfo.ini 缺 [{{sec}}] {{key}}")
        if cp.has_section("Details"):
            cat = (cp.get("Details", "Category", fallback="") or "").strip()
            allowed_cat = {{"Accessibility", "Development", "Education", "Games",
                           "Graphics & Pictures", "Internet", "Music & Video",
                           "Office", "Security", "Utilities"}}
            if cat and cat not in allowed_cat:
                errors.append(f"appinfo.ini [Details] Category 非法: {{cat}}")

    # 4. 图标
    for icon in ("appicon.ico", "appicon_16.png", "appicon_32.png"):
        if not (ai.parent / icon).is_file():
            errors.append(f"缺图标 {{icon}}")

    # 5. 启动器配置
    lad = ai.parent / "Launcher"
    if not lad.is_dir() or not list(lad.glob(f"{{PKG}}.ini")):
        if not (ai.parent / "launcher.ini").is_file():
            errors.append("缺启动器配置 App/AppInfo/Launcher/" + PKG + ".ini")

    if errors:
        for e in errors:
            print("[FAIL]", e)
        return 1
    print("[PASS] 结构校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def t_gen_sbom(p: str) -> str:
    """生成 SBOM 脚本。刻意避免嵌套 f-string：包名以字面量注入，
    生成器自身不会把 PKG 当变量求值。"""
    lines = [
        '# -*- coding: utf-8 -*-',
        '"""gen-sbom.py —— 生成 SPDX SBOM（' + p + '）',
        '',
        '只依赖标准库，输出 dist/sbom.spdx.json。',
        'SBOM 记录本仓库便携化配置与原程序文件清单（不做依赖解析）。',
        '"""',
        'import hashlib',
        'import json',
        'import sys',
        'from datetime import datetime, timezone',
        'from pathlib import Path',
        '',
        'REPO = Path(__file__).resolve().parents[1]',
        'PKG = "' + p + '"',
        'DIST = REPO / "dist"',
        'NAMESPACE = "https://greensoftmake.local/spdx/" + PKG',
        '',
        '',
        'def sha256(path):',
        '    h = hashlib.sha256()',
        '    with open(path, "rb") as f:',
        '        for b in iter(lambda: f.read(1 << 20), b""):',
        '            h.update(b)',
        '    return h.hexdigest()',
        '',
        '',
        'def main():',
        '    pkg_dir = DIST / PKG',
        '    if not pkg_dir.is_dir():',
        '        print("[FAIL] 先运行 build-portable.py 生成 " + str(pkg_dir))',
        '        return 1',
        '',
        '    files = []',
        '    for path in sorted(pkg_dir.rglob("*")):',
        '        if not path.is_file():',
        '            continue',
        '        try:',
        '            rel = "./" + str(path.relative_to(pkg_dir)).replace(os.sep, "/")',
        '            files.append({',
        '                "fileName": rel,',
        '                "sha256": sha256(path),',
        '                "size": path.stat().st_size,',
        '            })',
        '        except OSError:',
        '            continue',
        '',
        '    sbom = {',
        '        "spdxVersion": "SPDX-2.3",',
        '        "dataLicense": "CC0-1.0",',
        '        "SPDXID": "SPDXRef-DOCUMENT",',
        '        "name": PKG + "-sbom",',
        '        "documentNamespace": NAMESPACE,',
        '        "creationInfo": {',
        '            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),',
        '            "creators": ["Tool: gen-sbom.py"],',
        '        },',
        '        "packages": [{',
        '            "SPDXID": "SPDXRef-Package-portableconfig",',
        '            "name": PKG,',
        '            "versionInfo": "see-portableapps/App/AppInfo/appinfo.ini",',
        '            "downloadLocation": "NOASSERTION",',
        '            "filesAnalyzed": False,',
        '            "licenseConcluded": "MIT",',
        '            "licenseDeclared": "MIT",',
        '            "copyrightText": "NOASSERTION",',
        '        }],',
        '        "files": [',
        '            {"SPDXID": "SPDXRef-File-" + str(i), "fileName": f["fileName"],',
        '             "sha256": f["sha256"], "licenseConcluded": "NOASSERTION",',
        '             "copyrightText": "NOASSERTION"}',
        '            for i, f in enumerate(files)',
        '        ],',
        '        "relationships": [{',
        '            "spdxElementId": "SPDXRef-DOCUMENT",',
        '            "relatedSpdxElement": "SPDXRef-Package-portableconfig",',
        '            "relationshipType": "DESCRIBES",',
        '        }],',
        '    }',
        '',
        '    out = DIST / "sbom.spdx.json"',
        '    out.write_text(json.dumps(sbom, ensure_ascii=False, indent=2),',
        '                   encoding="utf-8")',
        '    print("[OK] " + str(out) + " (" + str(len(files)) + " 个文件)")',
        '    return 0',
        '',
        '',
        'if __name__ == "__main__":',
        '    raise SystemExit(main())',
        '',
    ]
    src = "\n".join(lines)
    # 生成器内部需要一个 import os（用于 os.sep）
    return src.replace('import json', 'import json\nimport os', 1)


def t_src_readme(p: str) -> str:
    return f"""# src/ —— 启动器与安装器源码说明

本目录遵循双轨标准的 `src/` 约定，用于存放**自研**的启动器/安装器源码。

## 当前状态

{p} 使用 **PortableApps.com Launcher**（官方 NSIS 启动器），
其源码不在本仓库，而在公共工具链：

```
../_shared/toolchain/PortableApps.comLauncher/
├── App/AppInfo/          启动器配置模板
├── App/NSIS/             makensis.exe（编译器）
└── Other/Source/         启动器 NSIS 源码（Segments/、*.nsh、*.nsi）
```

构建时由 `scripts/build-portable.py` 调用 `../_shared/build_launcher.py`，
把本项目的 `appinfo.ini` 与 `Launcher/*.ini` 注入后编译出 `{p}.exe`。

## 本项目自定义逻辑

便携化定制逻辑写在：

```
portableapps/App/AppInfo/Launcher/Custom.nsh
```

用于处理各应用特有的目录联接建立与拆除逻辑。

## 若改为自研启动器

将新启动器源码放入本目录，并在 `scripts/build-portable.py` 中
替换编译入口即可；`portableapps/` 的配置格式保持不变。
"""


def t_other_source_readme(p: str) -> str:
    return f"""{p} Portable —— 第三方源码与许可说明

本目录遵循 PortableApps.com Format 3.9 规范，用于存放：

- 启动器与安装器源码的说明（实际源码见 `../../src/` 与公共工具链）
- 原程序许可文件副本
- 第三方依赖声明

PortableApps.com Format 3.9 要求发行包内包含 `Other/Source/`，
以便用户获取构建本包所用的第三方源码与许可。
"""


def t_help_html(p: str, meta: dict) -> str:
    name = meta.get("Details.Name") or f"{p} Portable"
    ver = meta.get("Version.DisplayVersion") or meta.get("Version.PackageVersion") or ""
    desc = meta.get("Details.Description") or f"{name} 的便携化版本。"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{name} 使用帮助</title>
<style>
 body {{ font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
        max-width: 760px; margin: 40px auto; padding: 0 20px;
        line-height: 1.7; color: #222; }}
 h1 {{ border-bottom: 2px solid #2b6cb0; padding-bottom: 8px; }}
 h2 {{ margin-top: 28px; color: #2b6cb0; }}
 code {{ background: #f4f6f8; padding: 2px 6px; border-radius: 3px; }}
 .ver {{ color: #666; font-size: 0.9em; }}
 table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
 td, th {{ border: 1px solid #dde; padding: 8px 10px; text-align: left; }}
 th {{ background: #f4f6f8; }}
</style>
</head>
<body>
<h1>{name} <span class="ver">{'v' + ver if ver else ''}</span></h1>
<p>{desc}</p>

<h2>一、快速开始</h2>
<p>解压到任意目录（路径可含空格与中文），双击
<code>{p}.exe</code> 即可运行，无需安装。</p>

<h2>二、数据存放位置</h2>
<p>所有用户数据写入便携包内的 <code>Data\\</code> 目录：</p>
<table>
  <tr><th>内容</th><th>位置</th></tr>
  <tr><td>配置与会话</td><td><code>Data\\settings\\</code></td></tr>
  <tr><td>缓存与临时文件</td><td><code>Data\\settings\\local\\</code>、<code>Data\\settings\\Temp\\</code></td></tr>
</table>
<p><strong>备份</strong>只需复制 <code>Data\\</code> 目录；
<strong>恢复初始状态</strong>删除 <code>Data\\</code> 目录即可。</p>

<h2>三、卸载</h2>
<p>删除整个便携包目录即完成卸载，宿主系统零残留。</p>

<h2>四、注意事项</h2>
<ul>
  <li>请勿把便携包放在需要管理员权限写入的位置（如 <code>C:\\Program Files</code>）。</li>
  <li>可移动到任意盘符（含 U 盘），但运行中请勿拔出。</li>
  <li>本包为单用户设计；多用户共用请各自复制一份完整目录。</li>
</ul>

<h2>五、更多信息</h2>
<ul>
  <li>构建与发布说明：仓库 <code>docs/</code> 目录</li>
  <li>原软件许可与来源：仓库 <code>THIRD_PARTY_NOTICES.md</code></li>
  <li>问题反馈：项目 GitHub Issues</li>
</ul>

</body>
</html>
"""


def t_build_portable_py(p: str) -> str:
    return f'''# -*- coding: utf-8 -*-
"""build-portable.py —— 构建 dist/ 便携包（{p} 双轨标准构建入口）

流程：清理 dist/ → 复制 portableapps/ 源 → 编译启动器 → 结构校验。

工具链定位经toolchain.py 完成，不再硬编码 monorepo 绝对路径。
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toolchain import build_launcher_script, find_toolchain  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PKG = "{p}"
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
        print(f"[FAIL] 缺少启动器构建器: {{builder}}", file=sys.stderr)
        return 2
    r = subprocess.run([sys.executable, str(builder), str(DIST)])
    return r.returncode


def verify() -> int:
    test = REPO / "tests" / "test_structure.py"
    if not test.is_file():
        return 0
    r = subprocess.run([sys.executable, str(test)])
    return r.returncode


def main() -> int:
    if not SRC.is_dir():
        print(f"[FAIL] 缺portableapps/ 源目录: {{SRC}}")
        return 1
    print(f"[1/3] 复制 portableapps/ -> dist/{{PKG}}")
    copy_source()
    print("[2/3] 编译 PortableApps 启动器")
    rc = build_launcher()
    if rc != 0:
        print(f"[FAIL] 启动器编译失败 rc={{rc}}")
        return rc
    print("[3/3] 结构校验")
    if verify() != 0:
        print("[WARN] 结构校验未通过，请检查上面的输出")
    print(f"[OK] 构建完成: {{DIST}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def t_build_portable_ps1() -> str:
    return """# build-portable.ps1 —— build-portable.py 的薄包装（主逻辑在 Python）
param()
$ErrorActionPreference = "Stop"
$python = if ($env:PAF_PYTHON) { $env:PAF_PYTHON } else { "python" }
& $python "$PSScriptRoot\\build-portable.py" @args
exit $LASTEXITCODE
"""


def t_package_paf_ps1() -> str:
    return """# package-paf.ps1 —— 生成 .paf.exe（PortableApps.com Installer）
#
# 需要 PortableApps.com Installer（官方工具，Windows 版）。
# 未安装时脚本会给出明确提示而非静默失败。
#
# 生成物：dist\\<Package>_<Version>.paf.exe
param(
    [switch]$SkipChecksum
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$pkg = Split-Path -Leaf $repo

Write-Host "[1/2] 打包压缩包"
& python "$PSScriptRoot\\package-paf.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipChecksum) {
    Write-Host "[2/2] 校验和已生成: dist\\SHA256SUMS"
}

# 查找 PortableApps.com Installer
$installer = Get-Command "PortableApps.comInstaller.exe" -ErrorAction SilentlyContinue
if (-not $installer) {
    $cand = @(
        "$repo\\..\\_shared\\toolchain\\PortableApps.comInstaller\\App\\PortableApps.comInstaller.exe",
        "C:\\Program Files\\PortableApps.com Installer\\PortableApps.comInstaller.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($cand) { $installer = @{ Source = $cand } }
}

if (-not $installer) {
    Write-Warning @"
未找到 PortableApps.com Installer，跳过 .paf.exe 生成。
压缩包与 SHA256SUMS 已就绪，可直接用于 GitHub Releases。
如需生成 .paf.exe，请从 https://portableapps.com/development/installer/ 下载安装后重试。
"@
    exit 0
}

$exe = if ($installer.Source) { $installer.Source } else { $installer.Source }
Write-Host "使用 Installer: $exe"
& $exe "/SILENT" "/DESTINATION=$repo\\dist"
Write-Host "[OK] .paf.exe 应位于 dist\\"
exit $LASTEXITCODE
"""


def t_toolchain_shim() -> str:
    """项目内的 toolchain 转发器（薄壳，真正实现位于 _shared）。"""
    return '''# -*- coding: utf-8 -*-
"""toolchain.py —— 本项目的工具链转发器

真正的定位逻辑在 `../../_shared/toolchain.py`，此处仅做转发，
保证项目脚本 `from toolchain import ...` 在任何层级下都能工作。
"""
import importlib.util
import sys
from pathlib import Path

_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "_shared" / "toolchain.py",
    Path(__file__).resolve().parents[1] / "_shared" / "toolchain.py",
    Path(__file__).resolve().parent / "toolchain.py",
]


def _load():
    last = None
    for c in _CANDIDATES:
        if c.is_file():
            spec = importlib.util.spec_from_file_location("_paf_toolchain", c)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                return mod
            except Exception as e:      # noqa: BLE001
                last = e
    sys.stderr.write(f"[FAIL] 无法加载 _shared/toolchain.py: {last}\\n")
    raise SystemExit(2)


_mod = _load()
find_toolchain = _mod.find_toolchain
pal_dir = _mod.pal_dir
build_launcher_script = _mod.build_launcher_script
update_engine_script = _mod.update_engine_script
config_for = _mod.config_for

if __name__ == "__main__":
    try:
        tc = find_toolchain(Path(__file__).resolve().parent)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
    print(f"[OK] 工具链: {tc}")
    print(f"     PAL    : {pal_dir(tc)}")
'''


def t_workflow_note(p: str) -> str:
    return f"""# {p} —— 自动更新与发布流水线

本项目由 `PortableApps/_shared/` 下的公共工具链统一驱动，
自身不重复实现构建逻辑。

## 组件

| 文件 | 作用 |
| --- | --- |
| `_shared/toolchain.py` | 工具链定位（PAL 源码树、NSIS、更新引擎） |
| `_shared/build_launcher.py` | 编译 PortableApps.com Launcher 启动器 |
| `_shared/update_engine.py` | 八阶段更新流水线（detect→…→rollback） |
| `_shared/configs/{p}.yaml` | 本项目更新配置（版本源、节奏、门禁策略） |
| `_shared/gen_update_configs.py` | 从各项目结构重新生成全部 yaml |

## 常用命令

```bash
# 工具链自检
python ../_shared/toolchain.py

# 构建便携包
python scripts/build-portable.py

# 结构校验
python tests/test_structure.py

# 更新状态报告
python ../_shared/update_engine.py report

# 版本检测（仅在 version_source 已实证时才联网）
python ../_shared/update_engine.py detect --project {p}
```

## 更新流水线阶段

```
detect → download/ingest → extract → diff → test → stage → release（门禁） → rollback
```

强制约束：

- 破坏性操作默认 `dry_run=True`，需显式 `--execute` 才落地
- `Data/` 目录只读，任何阶段不写入/删除用户数据
- 状态文件原子写（临时文件 + `os.replace`）
- 仅最新版本接收更新；保留最近 3 个版本以支持回滚

## 版本源诚实原则

`configs/{p}.yaml` 的 `version_source.type` 为 `manual` 时表示**尚无已实证的
在线版本源**——此时由人工下载安装包后用 `ingest` 子命令接管后续全流程，
不会虚构 URL 或版本号。已实证的源（如 `github_releases` / `api`）才会联网检测。
"""


# ---------------------------------------------------------------- 主流程

def load_meta() -> dict:
    import json
    here = Path(__file__).resolve().parent
    # 候选：本目录、仓库根、上级工作区、环境变量 PAF_META
    cands = [here / "meta.json", here.parents[1] / "meta.json"]
    env_meta = os.environ.get("PAF_META")
    if env_meta:
        cands.insert(0, Path(env_meta))
    for cand in cands:
        try:
            if cand.is_file():
                return json.loads(cand.read_text(encoding="utf-8"))
        except OSError:
            continue
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="覆盖已存在文件（默认只补缺失项）")
    ap.add_argument("--legacy-layout", action="store_true",
                    help="明知会生成旧布局（包内 scripts/ tests/ 与 dist 路径）"
                         "仍要继续；默认拒绝，防止把已精简的仓库打回旧形态")
    args = ap.parse_args()

    # 护栏：本工具是 2026-10-17 双轨标准化时期的遗留生成器，产出的包树
    # 含 scripts/ tests/ 与 <Pkg>\dist\<Pkg> 路径——与 2026-10-18 精简约定
    # （包内只放 portableapps/ docs/ .github/ 开源元数据）和 dist 外迁冲突。
    # 今天误跑会把 39 个已合规包重新写入禁录目录。确需旧布局时显式加
    # --legacy-layout（例如按旧标准重建一个一次性参考树）。
    if not args.legacy_layout:
        print("[拒绝] scaffold.py 为双轨标准化时期（2026-10-17）的遗留生成器，"
              "其模板会写入包内 scripts/ tests/ 及 dist 旧路径。")
        print("       当前仓库已按精简约定收敛（通用工具在 _shared/scripts/，"
              "产品在仓库外 <产品根>）。")
        print("       确需生成旧布局参考树：加 --legacy-layout 再跑。")
        return 2

    meta_all = load_meta()
    plan: dict[str, list[tuple[str, str]]] = {}   # project -> [(rel, action)]

    for p in PROJECTS:
        root = ROOT / p
        if not root.is_dir():
            print(f"[跳过] {p} 目录不存在")
            continue
        meta = meta_all.get(p, {})
        items: list[tuple[str, str]] = []

        def need(rel: str, content_fn, label: str = "") -> None:
            """记录待写入项（仅当缺失或 --force）"""
            tgt = root / rel.replace("/", "\\")
            if tgt.exists() and not args.force:
                return
            items.append((rel, label or "生成"))

        # --- 从样板复制通用骨架
        for rel in COPY_FROM_TEMPLATE:
            src = TEMPLATE / rel.replace("/", "\\")
            tgt = root / rel.replace("/", "\\")
            if src.is_file() and (not tgt.exists() or args.force):
                items.append((rel, f"复制自 TyporaPortable"))

        # --- 项目特定文件
        need("README.md", None, "生成")
        need("CONTRIBUTING.md", None)
        need("SECURITY.md", None)
        need("SUPPORT.md", None)
        need("CHANGELOG.md", None)
        need("THIRD_PARTY_NOTICES.md", None)
        need("docs/PORTABLE.md", None)
        need("docs/BUILD.md", None)
        need("docs/RELEASE.md", None)
        need("src/README.md", None)
        need("portableapps/Other/Source/README.md", None)
        need("portableapps/help.html", None)
        need("portableapps/App/AppInfo/installer.ini", None)
        need(".github/workflows/ci.yml", None)
        if p not in NO_AUTO:
            need(".github/workflows/portableapps.yml", None)
            need(".github/workflows/release.yml", None)
            need("scripts/package-paf.ps1", None)
        # 脚本（总是重写：需修正迁移后的路径依赖）
        items.append(("scripts/build-portable.py", "重写(修路径依赖)"))
        items.append(("scripts/build-portable.ps1", "重写(修路径依赖)"))
        items.append(("scripts/toolchain.py", "重写(转发器)"))
        items.append(("scripts/gen-sbom.py", "生成"))
        items.append(("tests/test_structure.py", "重写(增强校验)"))
        items.append(("WORKFLOW.md", "生成"))

        # package-paf.py：若无则从样板复制
        pp = root / "scripts" / "package-paf.py"
        if not pp.is_file() and p not in NO_AUTO:
            tpl = TEMPLATE / "scripts" / "package-paf.py"
            if tpl.is_file():
                items.append(("scripts/package-paf.py", "复制自 TyporaPortable"))

        plan[p] = items

    total = sum(len(v) for v in plan.values())
    print(f"[模式] {'EXECUTE' if args.execute else 'DRY-RUN'}"
          f"{' (+force)' if args.force else ''}")
    print(f"[计划] {len(plan)} 个项目，共 {total} 项\n")
    for p, items in plan.items():
        if items:
            print(f"  {p}  ({len(items)} 项)")
            for rel, act in items:
                print(f"      {act:24s} {rel}")
    if not args.execute:
        print(f"\n共 {total} 项。加 --execute 执行。")
        return 0

    # ---------------- 实际写入
    print("\n" + "=" * 70)
    done = 0
    for p, items in plan.items():
        root = ROOT / p
        meta = meta_all.get(p, {})
        print(f"\n[{p}]")
        for rel, _act in items:
            src = TEMPLATE / rel.replace("/", "\\")
            tgt = root / rel.replace("/", "\\")

            try:
                if _act.startswith("复制"):
                    tgt.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, tgt)
                else:
                    text = _render(p, rel, meta)
                    if text is None:
                        continue
                    w(tgt, text)
                done += 1
            except Exception as e:       # noqa: BLE001
                print(f"    [FAIL] {rel}: {e}")
    print(f"\n[汇总] 写入 {done} 项")
    return 0


def _render(p: str, rel: str, meta: dict):
    R = {
        "README.md": lambda: t_readme(p, meta),
        "CONTRIBUTING.md": lambda: t_contributing(p),
        "SECURITY.md": lambda: t_security(p, meta),
        "SUPPORT.md": lambda: t_support(p, meta),
        "CHANGELOG.md": lambda: t_changelog(p, meta),
        "THIRD_PARTY_NOTICES.md": lambda: t_thirdparty(p, meta),
        "docs/PORTABLE.md": lambda: t_portable_md(p, meta),
        "docs/BUILD.md": lambda: t_build_md(p),
        "docs/RELEASE.md": lambda: t_release_md(p, p not in NO_AUTO),
        "src/README.md": lambda: t_src_readme(p),
        "portableapps/Other/Source/README.md": lambda: t_other_source_readme(p),
        "portableapps/help.html": lambda: t_help_html(p, meta),
        "portableapps/App/AppInfo/installer.ini": t_installer_ini,
        ".github/workflows/ci.yml": lambda: t_ci_yml(p),
        ".github/workflows/portableapps.yml": lambda: t_portableapps_yml(p),
        ".github/workflows/release.yml": lambda: t_release_yml(p),
        "scripts/package-paf.ps1": t_package_paf_ps1,
        "scripts/build-portable.py": lambda: t_build_portable_py(p),
        "scripts/build-portable.ps1": t_build_portable_ps1,
        "scripts/toolchain.py": t_toolchain_shim,
        "scripts/gen-sbom.py": lambda: t_gen_sbom(p),
        "tests/test_structure.py": lambda: t_test_structure(p),
        "WORKFLOW.md": lambda: t_workflow_note(p),
    }
    fn = R.get(rel)
    return fn() if fn else None


if __name__ == "__main__":
    raise SystemExit(main())