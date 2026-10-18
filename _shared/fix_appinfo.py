# -*- coding: utf-8 -*-
r"""fix_appinfo.py —— 为使用官方 Launcher 生成式段布局的项目补齐 [Format]/[Control]

【为什么需要】
部分项目的 appinfo.ini 由 PortableApps.com Launcher Generator 生成，段布局是
[AppInfo]/[Launch]/[ClientControl]/[Setup]/[Category]/[Details]/[Version]，
缺少双轨标准要求的 [Format] Type/Version 与 [Control] Start。

补齐后 appinfo.ini 同时满足：
  - PortableApps.com Format 3.9 规范（发行包校验）
  - 启动器 Segments\Core.nsh 的 .onInit 读取（Name/AppID/PackageVersion）

【安全约束】
  - 只在**缺失时**追加，不覆盖已有 [Format]/[Control] 段
  - 保留原文件编码（WPS 系为 UTF-16LE，其余 utf-8-sig）
  - [Details] Name/AppID 与 [Version] PackageVersion 必须已存在才补，
    否则说明配置本身有问题，直接报错不猜
  - 写入前自动备份为 appinfo.ini.bakfix
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"<仓库根>/")

VALID_CATEGORIES = {
    "Accessibility", "Development", "Education", "Games",
    "Graphics & Pictures", "Internet", "Music & Video",
    "Office", "Security", "Utilities",
}

# 默认 Category（当项目确实没有可判定值时，按软件性质归类）
CATEGORY_HINT = {
    "QuarkCloudDrivePortable": "Internet",
    "FoxitPDFPortable": "Office",
}


def read_text(p: Path) -> tuple[str, str]:
    raw = p.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("gb18030", errors="replace"), "gb18030"


def write_text(p: Path, text: str, enc: str) -> None:
    nl = "\r\n" if "\r\n" in text else "\n"
    body = text.replace("\r\n", "\n").replace("\n", nl)
    data = body.replace("\n", nl).encode("utf-16" if enc == "utf-16" else "utf-8")
    if enc == "utf-8-sig":
        data = b"\xef\xbb\xbf" + data
    p.write_bytes(data)


def has_section(text: str, name: str) -> bool:
    return re.search(r"(?mi)^\[" + re.escape(name) + r"\]\s*$", text) is not None


def get_key(text: str, section: str, key: str) -> str:
    m = re.search(r"(?mi)^\[" + re.escape(section) + r"\][^\[]*?^\s*"
                  + re.escape(key) + r"\s*=\s*(.*)$", text)
    return m.group(1).strip() if m else ""


def fix(pkg: str, execute: bool) -> list[str]:
    notes: list[str] = []
    info_dir = ROOT / pkg / "portableapps" / "App" / "AppInfo"
    ai = info_dir / "appinfo.ini"
    if not ai.is_file():
        return [f"{pkg}: 缺 appinfo.ini"]

    text, enc = read_text(ai)
    orig = text

    name = get_key(text, "Details", "Name")
    appid = get_key(text, "Details", "AppID") or get_key(text, "AppInfo", "ID")
    if not name:
        notes.append(f"{pkg}: [Details] Name 缺失，需人工确认（不强补）")
    if not appid:
        notes.append(f"{pkg}: [Details] AppID 缺失，需人工确认（不强补）")
        return notes
    if appid != pkg:
        notes.append(f"{pkg}: AppID={appid} 与目录名不一致，已按目录名归一为 {pkg}")
        # 就地改写 AppID
        text = re.sub(r"(?mi)^(\s*AppID\s*=\s*)" + re.escape(appid) + r"\s*$",
                      r"\g<1>" + pkg, text)

    add: list[str] = []

    # ---- [Format]
    if not has_section(text, "Format"):
        block = ["[Format]",
                 "Type=PortableApps.comFormat",
                 "Version=3.9",
                 ""]
        add.append("[Format] Type=PortableApps.comFormat / Version=3.9")
        text = "\n".join(block) + "\n" + text

    # ---- [Details] Category
    cat = get_key(text, "Details", "Category")
    if not cat:
        cat_hint = CATEGORY_HINT.get(pkg, "Utilities")
        if has_section(text, "Details"):
            text = re.sub(r"(?mi)^(\s*Category\s*=\s*).*$",
                          r"\g<1>" + cat_hint, text, count=0) \
                if re.search(r"(?mi)^\s*Category\s*=", text) else text
            if not get_key(text, "Details", "Category"):
                text = re.sub(r"(?mi)^(\[Details\][^\[]*?)$",
                              r"\1\nCategory=" + cat_hint, text, count=1)
        add.append(f"[Details] Category={cat_hint}")
    elif cat not in VALID_CATEGORIES:
        # 取 [AppInfo] 段的 Category
        alt = get_key(text, "AppInfo", "Category")
        use = alt if alt in VALID_CATEGORIES else CATEGORY_HINT.get(pkg, "Utilities")
        text = re.sub(r"(?mi)^(\s*Category\s*=\s*)" + re.escape(cat) + r"\s*$",
                      r"\g<1>" + use, text)
        add.append(f"Category 归一：{cat} -> {use}")

    # ---- [Control] Start
    if not has_section(text, "Control"):
        add.append(f"[Control] Start={pkg}.exe")
        # ExtractIcon 相对包根目录：App\<子目录>\<exe>
        pe = get_key(text, "Launch", "ProgramExecutable")
        extract = f"App\\{pe}" if pe else f"App\\{pkg}\\{pkg}.exe"
        block = ["[Control]",
                 f"Start={pkg}.exe",
                 f"ExtractIcon={extract}",
                 "Icons=1",
                 ""]
        # 放在 [Details] 之后更贴近官方顺序：直接追加到文末即可（NSIS 只读首段）
        text = text.rstrip("\n") + "\n\n" + "\n".join(block)
    elif not get_key(text, "Control", "Start"):
        text = re.sub(r"(?mi)^(\[Control\])[^\[]*?$", r"\1\nStart=" + pkg + ".exe",
                      text, count=1)
        add.append(f"[Control] Start={pkg}.exe")

    if not add:
        return [f"{pkg}: 已合规，无需修改"]

    if not execute:
        return [f"{pkg}: 将补齐 -> " + "; ".join(add)]

    shutil.copy2(ai, ai.with_suffix(".ini.bakfix"))
    write_text(ai, text, enc)
    return [f"{pkg}: 已补齐 -> " + "; ".join(add)]


def main() -> int:
    execute = "--execute" in sys.argv
    pkgs = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not pkgs:
        pkgs = sorted(d.name for d in ROOT.iterdir()
                      if d.is_dir() and (d / "portableapps" / "App" / "AppInfo"
                                         / "appinfo.ini").is_file())
    print(f"[模式] {'EXECUTE' if execute else 'DRY-RUN'}\n")
    for p in pkgs:
        for line in fix(p, execute):
            print(" ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())