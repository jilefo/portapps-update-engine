# -*- coding: utf-8 -*-
r"""final_audit.py —— 39 个独立项目的双轨标准合规审计

校验项来自《开源与 PortableApps 双轨发布标准》第四部分的
「GitHub 完整结构」与「PortableApps 必需文件与配置」两张清单。

退出码：0 = 全部通过；1 = 有不合规项（明细见输出）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths

ROOT = _paths.REPO_ROOT

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

NO_AUTO = {"FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable"}

# 轨道一：GitHub 开源必需文件
GITHUB_TRACK = [
    ".editorconfig", ".gitattributes", ".gitignore",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/CODEOWNERS", ".github/dependabot.yml",
    ".github/workflows/ci.yml",
    "LICENSE", "README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
    "SECURITY.md", "CHANGELOG.md", "SUPPORT.md", "THIRD_PARTY_NOTICES.md",
    "docs/PORTABLE.md", "docs/BUILD.md", "docs/RELEASE.md",
    "WORKFLOW.md",
    "src",
    "portableapps/help.html",
    "portableapps/App/AppInfo/appinfo.ini",
    "portableapps/App/AppInfo/installer.ini",
    "portableapps/App/AppInfo/appicon.ico",
    "portableapps/App/AppInfo/appicon_16.png",
    "portableapps/App/AppInfo/appicon_32.png",
    "portableapps/App/AppInfo/appicon_128.png",
    "portableapps/Other/Source", "portableapps/Other/Help",
]

# 集中工具链（2026-10-18 精简后由各包 scripts/ tests/ 上收到 _shared/scripts/，
# 全仓库 39 包共用一份；缺失对所有项目同时失效，故单独整体校验一次）
CENTRAL_TOOLCHAIN = [
    "_shared/scripts/build-portable.py",
    "_shared/scripts/build-portable.ps1",
    "_shared/scripts/toolchain.py",
    "_shared/scripts/gen-sbom.py",
    "_shared/scripts/test_structure.py",
    # 非特例项目（36/39）的打包链；集中存在不违反三特例禁令
    # （禁令约束的是包内 .github/workflows/release.yml 与包内 scripts/）。
    "_shared/scripts/package-paf.py",
    "_shared/scripts/package-paf.ps1",
]

# 轨道二：仅非特例项目需要
RELEASE_TRACK = [
    ".github/workflows/release.yml",
    ".github/workflows/portableapps.yml",
]

# 三特例必须**不存在**这些文件
MUST_NOT_HAVE = [
    ".github/workflows/release.yml",
    ".github/workflows/portableapps.yml",
]

CATEGORIES = {"Accessibility", "Development", "Education", "Games",
              "Graphics & Pictures", "Internet", "Music & Video",
              "Office", "Security", "Utilities"}


def read_text(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def audit_appinfo(path: Path) -> list[str]:
    """校验 appinfo.ini。

    本仓库存在两种**都合规**的段布局：
      A. Format 3.9 标准式：[Format]/[Details]/[License]/[Version]/[Control]/
      B. 官方Launcher 生成式：[AppInfo]/[Launch]/[ClientControl]/[Setup]/
                              [Category]/[Details]/[Version]

    两种都必须有 [Details] Name+AppID 与 [Version] PackageVersion——
    这正是 PortableApps 启动器 Segments\\Core.nsh 在 .onInit 里读取的字段，
    缺失会导致启动器弹「is missing」并直接 Quit。
    [Format]/[Control] 缺失时按缺失项报错（可由构建器fix_appinfo 补齐）。
    """
    import configparser
    errs = []
    cp = configparser.ConfigParser(strict=False, allow_no_value=True,
                                  delimiters=("=",), interpolation=None)
    cp.optionxform = str
    try:
        cp.read_string(read_text(path))
    except configparser.Error as e:
        return [f"appinfo.ini 解析失败: {e}"]

    def g(sec, key):
        if not cp.has_section(sec):
            return ""
        return (cp.get(sec, key, fallback="") or "").strip()

    # 两种布局都必须具备的核心字段
    if not g("Details", "Name"):
        errs.append("appinfo.ini 缺 [Details] Name（启动器必需）")
    if not g("Details", "AppID"):
        errs.append("appinfo.ini 缺 [Details] AppID（启动器必需）")
    if not g("Version", "PackageVersion"):
        errs.append("appinfo.ini 缺 [Version] PackageVersion（启动器必需）")

    # [Format]：缺失或不对时报错
    fmt_type = g("Format", "Type")
    if not fmt_type:
        errs.append("appinfo.ini 缺 [Format] Type")
    elif fmt_type != "PortableApps.comFormat":
        errs.append(f"appinfo.ini [Format] Type 应为 PortableApps.comFormat，实为 {fmt_type}")

    # [Control] Start：三特例（WPS）允许多启动器，Start 仍为必填
    if not g("Control", "Start"):
        errs.append("appinfo.ini 缺 [Control] Start")

    # [Details] Category 必须是 PortableApps 合法枚举
    cat = g("Details", "Category")
    if not cat:
        # 退化检查：官方 Launcher 生成式里 Category 写在 [AppInfo] 段
        cat = g("AppInfo", "Category")
        if not cat:
            errs.append("appinfo.ini 缺 Category（[Details] 或 [AppInfo]）")
    if cat and cat not in CATEGORIES:
        errs.append(f"appinfo.ini Category 非法: {cat}")

    # AppID 应与目录名一致
    appid = g("Details", "AppID") or g("AppInfo", "ID")
    if appid and appid != path.parents[3].name:
        errs.append(f"appinfo.ini AppID={appid} 与目录名 {path.parents[3].name} 不一致")

    return errs


def _locate_executable(root: Path, pkg: str, pe: str) -> tuple[bool, str]:
    """定位 ProgramExecutable 指向的真实可执行文件。

    本仓库存在两种**都合规**的 payload 布局（双轨标准明确
    「原程序占位或下载脚本，不建议提交大二进制」）：

      A. 内嵌式：portableapps\\App\\<App>\\<exe>   —— 小体量软件，源码随源入库
      B. 占位式：portableapps\\App\\<App>\\DOWNLOAD.txt 仅占位说明，
                 大二进制在产品目录（迁移前 <Repo>/<Pkg>/dist/<Pkg>，
                 迁移后 <产品根>/<Pkg>）的 App\\<App>\\ 下，构建时注入

    返回 (是否找到, 布局标记)
    """
    rel = pe.replace("\\", "/").replace("/", os.sep)
    in_src = root / "portableapps" / "App" / rel
    if in_src.is_file():
        return True, "内嵌"
    # 迁移前产品树 = <Repo>/<Pkg>/dist/<Pkg>，迁移后 = <产品根>/<Pkg>，
    # 由 _paths.product_dir() 按两种布局自动切换。
    in_prod = _paths.product_dir(pkg) / "App" / rel
    if in_prod.is_file():
        return True, "占位"
    return False, "缺失"


def audit_launcher(root: Path, pkg: str) -> list[str]:
    errs = []
    info = root / "portableapps" / "App" / "AppInfo"
    cands = [info / "launcher.ini", info / "Launcher" / f"{pkg}.ini"]
    found = next((c for c in cands if c.is_file()), None)
    if not found:
        return ["缺启动器配置 App/AppInfo/Launcher/<AppID>.ini"]
    import configparser
    cp = configparser.ConfigParser(strict=False, allow_no_value=True,
                                  delimiters=("=",), interpolation=None)
    cp.optionxform = str
    try:
        cp.read_string(read_text(found))
    except configparser.Error as e:
        return [f"launcher ini 解析失败: {e}"]
    if not cp.has_section("Launch"):
        return ["启动器配置缺 [Launch] 段"]
    pe = (cp.get("Launch", "ProgramExecutable", fallback="") or "").strip()
    if not pe:
        errs.append("启动器配置缺 [Launch] ProgramExecutable")
        return errs
    ok, layout = _locate_executable(root, pkg, pe)
    if not ok:
        errs.append(f"ProgramExecutable 指向的文件不存在: App\\{pe}")
    return errs


def audit_project(pkg: str) -> tuple[list[str], dict]:
    root = ROOT / pkg
    errs: list[str] = []
    info: dict = {}

    if not root.is_dir():
        return [f"项目目录不存在: {root}"], info

    required = list(GITHUB_TRACK)
    if pkg not in NO_AUTO:
        required += RELEASE_TRACK

    for rel in required:
        if not (root / rel.replace("/", os.sep)).exists():
            errs.append(f"缺 {rel}")

    # 三特例：确保自动发布文件不存在
    if pkg in NO_AUTO:
        for rel in MUST_NOT_HAVE:
            if (root / rel.replace("/", os.sep)).exists():
                errs.append(f"特例项目不应存在 {rel}")

    # 产品目录（迁移前 <Repo>/<Pkg>/dist/<Pkg>，迁移后 <产品根>/<Pkg>）
    pdir = _paths.product_dir(pkg)
    if not pdir.is_dir():
        errs.append("缺产品目录: %s" % pdir)

    # appinfo 内容
    ai = root / "portableapps" / "App" / "AppInfo" / "appinfo.ini"
    if ai.is_file():
        errs += audit_appinfo(ai)
        info["appinfo"] = True
    else:
        info["appinfo"] = False

    # 启动器
    errs += audit_launcher(root, pkg)

    # payload 目录
    appd = root / "portableapps" / "App"
    subs = [d for d in os.listdir(appd)
            if os.path.isdir(appd / d) and d != "AppInfo"] if appd.is_dir() else []
    if not subs:
        errs.append("缺 portableapps/App/<AppName>/ 程序文件目录")
    else:
        info["payload"] = subs

    # 工具链可达性：集中 toolchain shim（精简后各包 scripts/ 已上收 _shared/）
    tc = ROOT / "_shared" / "scripts" / "toolchain.py"
    if tc.is_file():
        info["toolchain_shim"] = True

    # 更新配置存在性（特例项目也要有，只是策略为 manual_only）
    cfg = ROOT / "_shared" / "configs" / f"{pkg}.yaml"
    info["update_config"] = cfg.is_file()
    if not info["update_config"]:
        errs.append("缺 _shared/configs/<项目>.yaml 更新配置")

    return errs, info


def main() -> int:
    rows = []
    total_err = 0
    for pkg in PROJECTS:
        errs, info = audit_project(pkg)
        total_err += len(errs)
        rows.append((pkg, errs, info))

    # 集中工具链整体校验（39 包共用；缺失对所有项目同时生效，故单独报一次）
    missing_central = [rel for rel in CENTRAL_TOOLCHAIN
                       if not (ROOT / rel).is_file()]
    if missing_central:
        total_err += len(missing_central)
        print("[集中工具链] 缺：")
        for rel in missing_central:
            print(f"      - {rel}")
    else:
        print("[集中工具链] _shared/scripts 下 %d 个必需脚本齐全"
              % len(CENTRAL_TOOLCHAIN))

    print(f"{'项目':24s} {'结果':6s} 说明")
    print("-" * 78)
    for pkg, errs, info in rows:
        status = "PASS" if not errs else f"FAIL({len(errs)})"
        note = ""
        if not info.get("appinfo"):
            note = "无 appinfo.ini"
        elif info.get("payload"):
            note = f"payload={','.join(info['payload'][:2])}"
        if pkg in NO_AUTO:
            note += " [特例]"
        print(f"{pkg:24s} {status:6s} {note}")
        for e in errs:
            print(f"      - {e}")

    print("\n" + "=" * 78)
    ok = sum(1 for _, e, _ in rows if not e)
    print(f"[汇总] 通过 {ok} / {len(PROJECTS)}，不合规项 {total_err}")
    return 0 if total_err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())