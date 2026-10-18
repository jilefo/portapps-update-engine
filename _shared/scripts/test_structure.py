# -*- coding: utf-8 -*-
"""test_structure.py —— PortableApps.com Format 3.9 结构校验（通用版，包名自动推导）"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402

import configparser
import sys
from pathlib import Path



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
                errors.append(f"缺仓库文件 {rel}")

    # 2. dist 产物
    if not ini_only:
        if not DIST.is_dir():
            errors.append(
                f"dist 产物不存在: {DIST}"
                f"（先运行 _shared/scripts/build-portable.py {PKG}）")
        else:
            root_files = [p.name for p in DIST.iterdir() if p.is_file()]
            # version.json = 更新引擎写入的版本元数据（current/previous/
            # released_at/run_id/channel），运行期有追踪价值，属允许项。
            # 曾经误报为「多出文件」，故显式列入白名单。
            # update.py = 本包自带的更新脚本（一包一个，自包含，可随包拷走），
            # 由 _shared/tools/gen_update_strategies.py 生成，属允许项。
            allowed = {f"{PKG}.exe", "help.html", "version.json",
                       "update.py"}
            extra = set(root_files) - allowed
            # 多入口包允许额外的分体启动器：如 WPSOfficePortable 除主入口外
            # 还有 Writer/Spreadsheets/Presentation/wpsPDF 四个 *Portable.exe。
            # 早期版本忽略这点，导致 WPS 被误判 FAIL。
            extra = {e for e in extra if not e.endswith("Portable.exe")}
            if extra:
                errors.append(f"dist 根目录多出文件: {sorted(extra)}")
            for d in ("App", "Other"):
                if not (DIST / d).is_dir():
                    errors.append(f"dist 缺目录: {d}")

    # 3. appinfo.ini 必填字段
    ai = REPO / "portableapps" / "App" / "AppInfo" / "appinfo.ini"
    if not ai.is_file():
        errors.append(f"缺 {ai}")
    else:
        cp = parse_ini(ai)
        for sec, key in (("Format", "Type"), ("Details", "Name"),
                         ("Details", "AppID"), ("Version", "PackageVersion"),
                         ("Control", "Start")):
            if not cp.has_section(sec) or not (cp.get(sec, key, fallback="") or "").strip():
                errors.append(f"appinfo.ini 缺 [{sec}] {key}")
        if cp.has_section("Details"):
            cat = (cp.get("Details", "Category", fallback="") or "").strip()
            allowed_cat = {"Accessibility", "Development", "Education", "Games",
                           "Graphics & Pictures", "Internet", "Music & Video",
                           "Office", "Security", "Utilities"}
            if cat and cat not in allowed_cat:
                errors.append(f"appinfo.ini [Details] Category 非法: {cat}")

    # 4. 图标
    for icon in ("appicon.ico", "appicon_16.png", "appicon_32.png"):
        if not (ai.parent / icon).is_file():
            errors.append(f"缺图标 {icon}")

    # 5. 启动器配置
    lad = ai.parent / "Launcher"
    if not lad.is_dir() or not list(lad.glob(f"{PKG}.ini")):
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
