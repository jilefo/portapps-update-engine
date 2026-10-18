# -*- coding: utf-8 -*-
"""gen_update_configs.py —— 从各便携包现有结构生成 Configs\\<项目>.yaml

数据源（只读）：
  - Work\\<包>\\App\\AppInfo\\appinfo.ini   → current_version / publisher
  - Work\\<包>\\App\\AppInfo\\Launcher\\*.ini → entry_exe / app_subdir

分类与策略（方案第 11 节维护节奏分级 + 落地决策）：
  - P0 周检：Cursor / Qoder 系 / CodeArts 系 / CodeBuddy / Comate / JoyCode /
             WorkBuddy / TraeCN
  - 月检：AiPyPro / Miaoshou / MiniMaxCode / OfficeAce / TodayCN /
           FoxitPDF / WeMeet / QuarkCloudDrive / Zoom / Joplin
  - blocked：WinClaw / LobsterAI（稳定并建立版本快照前不接入）

版本源诚实原则：仅 JoplinPortable 已验证 GitHub releases 源；其余一律
manual + needs_manual，不虚构 URL，人工下载后 ingest 接管。
"""
from __future__ import annotations

import configparser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent      # ...\PortableApps\_shared
WORK = ROOT.parent                          # ...\PortableApps（各项目父目录）
CONFIGS = ROOT / "configs"

P0_WEEKLY = {"CursorPortable", "QoderCNPortable", "QoderCNIDEPortable",
             "CodeArtsPortable", "CodeArtsAgentPortable",
             "CodeBuddyCNPortable", "ComatePortable", "JoyCodePortable",
             "WorkBuddyPortable", "TraeCNPortable"}
BLOCKED = {"WinClawPortable", "LobsterAIPortable"}
# 注：FoxitPDFPortable 原为用户指定「不纳入更新体系」（EXCLUDED），
# 但 2026-10-17 统一项目化后，迁移任务书要求 39 个项目**全部**具备独立更新
# 维护能力，故不再排除扫描——其 yaml 的 release_policy=manual_only、
# schedule=none（见 NO_AUTO_RELEASE），即「有配置但不自动推送」。
# 若确需完全排除，把下面这行改为 EXCLUDED = {"FoxitPDFPortable"}。
EXCLUDED: set = set()
# 三特例（不自动更新/不自动发布，见迁移任务书第1 节）：
# 仍生成 yaml 以便统一管理，但release_policy=manual_only 且 schedule=none，
# 且各项目的 release.yml / portableapps.yml 不会被生成。
NO_AUTO_RELEASE = {"FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable"}

# 已验证的在线版本源（均经实证，未实证的一律 manual）
VERIFIED_SOURCES = {
    "JoplinPortable": {
        "type": "github_releases",
        "repo": "laurent22/joplin",
        "asset_regex": r"Joplin-Setup-.*\.exe$",
        "note": "2026-10-15 建包时已实证 NSIS 双层解包链路",
    },
    "CursorPortable": {
        "type": "api",
        "url": "https://www.cursor.com/api/download",
        "params": {"platform": "win32-x64", "releaseTrack": "latest"},
        "version_field": "version",
        "url_field": "downloadUrl",
        "note": "2026-10-16 实证可用；stable 通道=3.24.18，latest=3.25.6",
    },
    "SoloMDPortable": {
        "type": "github_releases",
        "repo": "zhitongblog/solomd",
        "asset_regex": r"SoloMD_.*_x64-portable\.zip$",
        "last_verified_at": "2026-10-16",
        "note": "实证命中，v5.0.1；sha256 与官方 SHA256SUMS.txt 匹配",
    },
    "FeishuPortable": {
        "type": "api",
        "url": "https://www.feishu.cn/api/package_info",
        "params": {"platform": "16"},
        "version_field": "data.version_number",
        "version_regex": r"V(\d+\.\d+\.\d+)",
        "url_field": "data.download_link",
        "last_verified_at": "2026-10-16",
        "note": "实证命中，8.2.14；download_link 为一次性签名直链"
                "（x-expires/x-signature），detect 只读版本号",
    },
    # 网盘分享页源（第三方分发，2026-10-16 实证）
    "ReNamerPortable": {
        "type": "lanzou_folder",
        "url": "https://gndown.lanzoub.com/b048rm8vg",
        "version_regex": r"_(\d+\.\d+(?:\.\d+)*)-",
        "last_verified_at": "2026-10-16",
        "note": "果核剥壳(ghpym)蓝奏云文件夹分享，第三方分发页（非 den4b 官方源）；"
                "实证命中 renamer_pro_7.10-Portable.7z（7.10）；detect 复现其 "
                "filemoreajax 接口取文件列表，分享页不提供稳定直链",
    },
    # WPSPDFPortable（独立雨糖特别版）已于 2026-10-16 废弃：T2 云档隔离触发
    # “核心支持库加载失败”，且与 WPSOffice 内置 wpsPDF 能力重复；用户已删除程序包，
    # VERIFIED_SOURCES 不再收录，PDF 统一走 WPSOfficePortable
    "ZenBrowserPortable": {
        "type": "github_releases",
        "repo": "zen-browser/desktop",
        "asset_regex": r"zen\.installer\.exe$",
        "last_verified_at": "2026-10-16",
        "note": "实证命中，1.23.2b；排除 zen.installer-arm64.exe",
    },
    "FSCapturePortable": {
        "type": "lanzou_folder",
        "url": "https://osssr.lanzoum.com/b01u8ekhg",
        "version_regex": r"FastStoneCapture\.(\d+\.\d+(?:\.\d+)*)\.",
        "last_verified_at": "2026-10-16",
        "note": "OSSSR(欧阳)蓝奏云文件夹分享，第三方便携重打包源（非 FastStone 官网）；"
                "实证命中 FastStoneCapture.11.3.Portable OSSSR.7z（11.3，6.7MB）；"
                "该分享页带 acw_sc__v2 反爬，detect 已内置解盾后经 filemoreajax 取列表，"
                "分享页不提供稳定直链",
    },
    # FoxitPDFPortable：用户要求不纳入更新体系（2026-10-16），VERIFIED_SOURCES 不再收录
}

# 已验证可静态解包的包类型（Joplin=electron-builder 双层 NSIS，
# Cursor/Typora=Inno 经 innounp 实证，SoloMD/Sublime/FSCapture=官方便携 zip，
# ReNamer=蓝奏云分享的纯 7z，Feishu/Zen=7z SFX 自解压单层；
# WPSPDFPortable 已废弃（2026-10-16），不收录）
VERIFIED_PACKAGE = {
    "JoplinPortable": ("electron_installer", "static_unpack"),
    "CursorPortable": ("inno", "static_unpack"),
    "TyporaPortable": ("inno", "static_unpack"),
    "SoloMDPortable": ("zip", "static_unpack"),
    "SublimeTextPortable": ("zip", "static_unpack"),
    "FeishuPortable": ("7z_sfx", "static_unpack"),
    # 蓝奏云分享内的 renamer_pro_*-Portable.7z 为纯 7z 包
    "ReNamerPortable": ("7z", "static_unpack"),
    "FSCapturePortable": ("zip", "static_unpack"),
    "ZenBrowserPortable": ("7z_sfx", "static_unpack"),
    # WPSPDFPortable：包已废弃删除（2026-10-16），不再收录
}


def _parser() -> configparser.ConfigParser:
    # strict=False：个别包 ini 存在重复键（如 CodeArts 的 RemoveFile）
    cp = configparser.ConfigParser(strict=False)
    cp.optionxform = str  # 保留键大小写
    return cp


def read_appinfo(pkg: Path) -> dict:
    ini = pkg / "App" / "AppInfo" / "appinfo.ini"
    if not ini.is_file():
        return {}
    # 走 _read_ini_file：WPSOfficePortable 的 appinfo.ini 是 UTF-16LE 带 BOM，
    # 直接 cp.read(encoding="utf-8-sig") 会抛 UnicodeDecodeError。
    cp = _read_ini_file(ini)
    out = {}
    if cp.has_section("AppInfo"):
        out["version"] = cp.get("AppInfo", "Version", fallback="")
        out["publisher"] = cp.get("AppInfo", "Publisher", fallback="")
    if cp.has_section("Version"):
        out["package_version"] = cp.get("Version", "PackageVersion",
                                        fallback="")
    return out


def _read_ini_file(path: Path) -> configparser.ConfigParser:
    """自动识别 utf-8-sig / utf-16（含 BOM）"""
    cp = _parser()
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        txt = raw.decode("utf-16", errors="replace")  # 自动剥 BOM
    else:
        txt = raw.decode("utf-8-sig", errors="replace")
    cp.read_string(txt)
    return cp


def read_entry_exe(pkg: Path) -> str:
    lad = pkg / "App" / "AppInfo" / "Launcher"
    if not lad.is_dir():
        return ""
    for f in sorted(lad.glob("*.ini")):
        cp = _read_ini_file(f)
        if cp.has_section("Launch"):
            return cp.get("Launch", "ProgramExecutable", fallback="")
    return ""


def build_config(pkg: Path, name: str | None = None,
                 dir_value: str | None = None) -> dict:
    name = name or pkg.name
    dir_value = dir_value or name
    info = read_appinfo(pkg)
    entry_exe = read_entry_exe(pkg)
    app_subdir = entry_exe.replace("\\", "/").split("/")[0] if entry_exe \
        else ""
    version = info.get("version") or info.get("package_version") or "0.0.0"

    if name in BLOCKED:
        category, schedule, policy = "紧急修复", "monthly", "blocked"
    elif name in NO_AUTO_RELEASE:
        category, schedule, policy = "不自动更新", "none", "manual_only"
    elif name in P0_WEEKLY:
        category, schedule, policy = "高频高危", "weekly", "manual_confirm"
    else:
        category, schedule, policy = "常规", "monthly", "manual_confirm"

    ptype, strategy = VERIFIED_PACKAGE.get(name, ("unknown",
                                                  "manual_fallback"))
    cfg = {
        "project": name,
        "dir": dir_value,
        "category": category,
        "publisher": info.get("publisher", ""),
        "current_version": version,
        "update_channel": "stable",
        "version_source": VERIFIED_SOURCES.get(
            name, {"type": "manual",
                   "note": "无已验证在线版本源；人工下载后 ingest 接管"}),
        "package_type": ptype,
        "extract_strategy": strategy,
        "entry_exe": entry_exe,
        "app_subdir": app_subdir,
        "launcher_args": [],
        "data_dir": "Data",
        "protected_paths": ["Data", "App/AppInfo", f"{name}.exe"],
        "extensions_dir": "",
        "updater_disable": {"args": [], "components": "auto_scan"},
        "test_profile": {"scenarios": ["S01", "S02", "S03", "S08", "S12"],
                         "soak_seconds": 30},
        "full_regression_trigger": ["major_version_jump",
                                    "high_risk_diff",
                                    "smoke_fail_fixed"],
        "rollback_policy": {"keep_versions": 3},
        "release_policy": policy,
        "schedule": schedule,
        "delta_update": False,
        "proxy": "",
        "last_checked_at": "",
    }
    return cfg


def main() -> int:
    CONFIGS.mkdir(parents=True, exist_ok=True)
    #迁移后统一为双轨布局：<Project>\portableapps\App\AppInfo\appinfo.ini
    # 兼容三种历史布局：
    #   双轨：<Project>\portableapps\App\AppInfo\appinfo.ini   （标准）
    #   平铺：<Project>\App\AppInfo\appinfo.ini              （老 22 包）
    #   产物：<Project>\dist\<Pkg>\App\AppInfo\appinfo.ini    （已构建产物）
    found: list[tuple[Path, str, str]] = []  # (包根, 包名, dir 值)
    for repo in sorted(WORK.iterdir()):
        if not repo.is_dir() or repo.name in EXCLUDED or repo.name.startswith("_"):
            continue
        paf = repo / "portableapps" / "App" / "AppInfo" / "appinfo.ini"
        if paf.is_file():
            found.append((paf.parent.parent.parent, repo.name,
                          f"{repo.name}\\dist\\{repo.name}"))
            continue
        flat = repo / "App" / "AppInfo" / "appinfo.ini"
        if flat.is_file():
            found.append((repo, repo.name, repo.name))
            continue
        dist = repo / "dist"
        if dist.is_dir():
            for d in sorted(dist.iterdir()):
                if (d / "App" / "AppInfo" / "appinfo.ini").is_file():
                    found.append((d, repo.name,
                                  f"{repo.name}\\dist\\{d.name}"))
    written = []
    for pkg, name, dir_value in found:
        cfg = build_config(pkg, name, dir_value)
        out = CONFIGS / f"{name}.yaml"
        # utf-8-sig：带 BOM，避免中文乱码（项目工程约定）
        out.write_text(yaml.safe_dump(cfg, allow_unicode=True,
                                      sort_keys=False),
                       encoding="utf-8-sig")
        written.append((name, cfg["current_version"],
                        cfg["release_policy"], cfg["schedule"],
                        cfg["version_source"]["type"]))
    print(f"已生成 {len(written)} 份配置 → {CONFIGS}")
    for name, ver, policy, sched, vs in written:
        print(f"  {name:28s} v{ver:16s} {policy:15s} {sched:8s} {vs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
