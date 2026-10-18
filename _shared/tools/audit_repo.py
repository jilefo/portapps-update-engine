# -*- coding: utf-8 -*-
r"""audit_repo.py —— CI 友好的仓库结构自检（不依赖任何第三方二进制）

与 audit_production.py 的分工：
  audit_production.py  面向「本机已装配好的 39 个可运行包」，会检查
                       dist/<Pkg>/<Pkg>.exe、App\ 下的真实程序文件。
  audit_repo.py        面向「GitHub 上的开源仓库」——App\ 二进制被 .gitignore
                       排除，CI 里根本不存在，所以只校验**元数据与文本约定**，
                       不碰二进制。任何人在新机器上 clone 后都能跑通。

检查项：
  A 元数据完备性（9 项：LICENSE/README/CHANGELOG/CONTRIBUTING/CODE_OF_CONDUCT/
                 .editorconfig/.gitignore/docs/.github）
  B appinfo.ini  存在 + 可解析 + 含 [Format]Type 与 [Control]Name
  C Launcher ini 存在 + 可解析 + [Launch]ProgramExecutable 非空
                + [Environment] APPDATA/LOCALAPPDATA 指向 %PAL:DataDir%
  D Custom.nsh   UTF-8 无 BOM（有 BOM → NSIS Invalid command）
                + 无 PowerShell 内联病态（'' 引号 / 裸 $变量 / ^| 管道）
  E 编码铁律     含非 ASCII 的 Launcher ini 必须 UTF-16LE

退出码：0 = 全通过；1 = 有硬失败。
用法：python _shared/tools/audit_repo.py [--tree dist|portableapps|both]
"""
import configparser
import os
import re
import sys
from pathlib import Path

# >>> 路径自适应：仓库根由本文件位置推导，可用 PORTABLEAPPS_ROOT 覆盖
REPO_ROOT = os.environ.get("PORTABLEAPPS_ROOT") or str(
    Path(__file__).resolve().parents[2])
# <<< 路径自适应

META_FILES = ["LICENSE", "README.md", ".gitignore", "CHANGELOG.md",
              "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", ".editorconfig"]
META_DIRS = ["docs", ".github"]

BAD_VAR_RE = re.compile(r"\$(l|t|p|tp|own|lt|k|v|root|n)(?![A-Za-z_])")


def sniff(path):
    with open(path, "rb") as f:
        b = f.read(4)
    if b[:2] == b"\xff\xfe":
        return "utf-16"
    if b[:2] == b"\xfe\xff":
        return "utf-16-be"
    if b[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def read_ini(path):
    enc = sniff(path)
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        if enc in ("utf-16", "utf-16-be"):
            text = Path(path).read_bytes().decode(enc)
            cp.read_string(text)
        else:
            cp.read_string(Path(path).read_text(encoding="utf-8-sig",
                                                errors="replace"))
    except (OSError, configparser.Error, UnicodeDecodeError) as e:
        return None, "解析失败(%s): %s" % (enc, e)
    return cp, enc


def packages():
    root = Path(REPO_ROOT)
    return sorted(p for p in root.iterdir()
                  if p.is_dir() and p.name.endswith("Portable")
                  and not p.name.startswith(("_", ".")))


def check_meta(pkg, fails):
    for f in META_FILES:
        if not (pkg / f).is_file():
            fails.append("缺元数据文件 %s" % f)
    for d in META_DIRS:
        if not (pkg / d).is_dir():
            fails.append("缺元数据目录 %s/" % d)


def appinfo_path(pkg, tree):
    """dist 树为 dist/<Pkg>/App/AppInfo/，源树为 portableapps/App/AppInfo/"""
    for p in (pkg / tree / "App" / "AppInfo" / "appinfo.ini",
              pkg / tree / pkg.name / "App" / "AppInfo" / "appinfo.ini"):
        if p.is_file():
            return p
    return None


def non_ascii_significant(path):
    """是否存在「注释之外」的非 ASCII 字符。

    关键区分：中文**注释**被 NSIS 按 ANSI 误读只是显示乱码，不影响启动；
    中文**路径/值**（如 ProgramExecutable=妙手\\妙手.exe）被误读则直接打不开。
    所以只有后者才触发 UTF-16LE 强制要求。
    """
    enc = sniff(path)
    raw = Path(path).read_bytes()
    try:
        text = raw.decode(enc) if enc in ("utf-16", "utf-16-be") \
            else raw.decode("utf-8-sig", errors="replace")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(";") or s.startswith("#"):
            continue
        if any(ord(c) > 127 for c in ln):
            return True
    return False


def check_appinfo(pkg, tree, fails):
    p = appinfo_path(pkg, tree)
    if p is None:
        fails.append("[%s] 缺 appinfo.ini" % tree)
        return
    cp, info = read_ini(p)
    if cp is None:
        fails.append("[%s] appinfo.ini %s" % (tree, info))
        return
    # 真实 PAL 字段：[Format]Type / [Details]Name 或 [AppInfo]Name /
    # [Control]Start + ExtractIcon（注意：[Control] 里没有 Name）
    if cp.get("Format", "Type", fallback="").strip() != "PortableApps.comFormat":
        fails.append("[%s] appinfo.ini [Format]Type 非 PortableApps.comFormat"
                     % tree)
    nm = (cp.get("Details", "Name", fallback="").strip()
          or cp.get("AppInfo", "Name", fallback="").strip())
    if not nm:
        fails.append("[%s] appinfo.ini 缺 [Details]Name/[AppInfo]Name" % tree)
    if not cp.get("Control", "Start", fallback="").strip():
        fails.append("[%s] appinfo.ini 缺 [Control]Start" % tree)


def check_launcher(pkg, tree, fails, notes):
    name = pkg.name
    d = pkg / tree / "App" / "AppInfo" / "Launcher"
    if not d.is_dir():
        d = pkg / tree / name / "App" / "AppInfo" / "Launcher"
    if not d.is_dir():
        fails.append("[%s] 缺 Launcher 目录" % tree)
        return
    inis = sorted(d.glob("*.ini"))
    if not inis:
        fails.append("[%s] Launcher 下无 ini" % tree)
        return
    for ini in inis:
        cp, info = read_ini(ini)
        if cp is None:
            fails.append("[%s] %s %s" % (tree, ini.name, info))
            continue
        enc = info
        non_ascii = non_ascii_significant(ini)
        if enc in ("utf-16", "utf-16-be"):
            notes.append("%s: %s（%s）" % (ini.name, enc,
                                          "含中文路径，必须保持"
                                          if non_ascii else "可考虑转 UTF-8"))
        elif non_ascii:
            fails.append("[%s] %s 含非 ASCII 却是 %s —— 必须 UTF-16LE，"
                         "否则 NSIS 按 ANSI 解码导致中文路径乱码"
                         % (tree, ini.name, enc))
        if not cp.has_section("Launch"):
            fails.append("[%s] %s 缺 [Launch]" % (tree, ini.name))
        elif not cp.get("Launch", "ProgramExecutable", fallback="").strip():
            fails.append("[%s] %s 缺 ProgramExecutable" % (tree, ini.name))
        if cp.has_section("Environment"):
            env = {k.upper(): v for k, v in cp.items("Environment")}
            for k in ("APPDATA", "LOCALAPPDATA"):
                if k not in env:
                    fails.append("[%s] %s 未重定向 %s" % (tree, ini.name, k))
                elif "%PAL:DataDir%" not in env[k]:
                    fails.append("[%s] %s 的 %s 未指向 %%PAL:DataDir%%：%s"
                                 % (tree, ini.name, k, env[k]))
        else:
            fails.append("[%s] %s 缺 [Environment]" % (tree, ini.name))


def check_custom_nsh(pkg, tree, fails):
    p = pkg / tree / "App" / "AppInfo" / "Launcher" / "Custom.nsh"
    if not p.is_file():
        p = pkg / tree / pkg.name / "App" / "AppInfo" / "Launcher" / "Custom.nsh"
    if not p.is_file():
        return
    raw = p.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        fails.append("[%s] Custom.nsh 带 UTF-8 BOM（NSIS 会报 Invalid command）"
                     % tree)
        return
    if b"\x00" in raw[:64]:
        fails.append("[%s] Custom.nsh 疑似 UTF-16（必须 UTF-8 无 BOM）" % tree)
        return
    text = raw.decode("utf-8", errors="replace")
    hits = []
    for i, ln in enumerate(text.splitlines(), 1):
        if "ExecToStack" not in ln or "Command" not in ln:
            continue
        bad = []
        if "''" in ln:
            bad.append("''引号")
        if BAD_VAR_RE.search(ln.replace("$$", "")):
            bad.append("裸$变量")
        if "^|" in ln:
            bad.append("^|管道")
        if bad:
            hits.append((i, bad))
    if hits:
        fails.append("[%s] Custom.nsh 病态 %d 处: %s" % (tree, len(hits), hits[:3]))


def main():
    trees = ["dist", "portableapps"]
    if "--tree" in sys.argv:
        t = sys.argv[sys.argv.index("--tree") + 1]
        trees = [t] if t in trees else ["dist", "portableapps"]
    pkgs = packages()
    all_fail, all_note = {}, {}
    for pkg in pkgs:
        fails, notes = [], []
        check_meta(pkg, fails)
        for tree in trees:
            check_appinfo(pkg, tree, fails)
            check_launcher(pkg, tree, fails, notes)
            check_custom_nsh(pkg, tree, fails)
        all_fail[pkg.name] = fails
        all_note[pkg.name] = notes

    ok = sum(1 for v in all_fail.values() if not v)
    print("=" * 64)
    print("仓库结构自检（CI 模式，不依赖二进制）")
    print("仓库根：%s   树：%s" % (REPO_ROOT, "+".join(trees)))
    print("=" * 64)
    for n in sorted(all_fail):
        f = all_fail[n]
        flag = "OK " if not f else "FAIL"
        print("  [%s] %s" % (flag, n))
        for x in f:
            print("        - %s" % x)
    print("-" * 64)
    print("通过 %d / %d" % (ok, len(pkgs)))
    noted = {n: v for n, v in all_note.items() if v}
    if noted:
        print("\n编码登记（非缺陷）：")
        for n in sorted(noted):
            for x in noted[n]:
                print("  %s -> %s" % (n, x))
    return 0 if ok == len(pkgs) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
