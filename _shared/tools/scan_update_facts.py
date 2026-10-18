# -*- coding: utf-8 -*-
r"""scan_update_facts.py —— 扫描全部便携包，收集"生成更新策略"所需的事实。

采集项：
  * 当前版本（appinfo.ini 的 PackageVersion / DisplayVersion）
  * 启动器入口（Launcher/*.ini -> [Launch]ProgramExecutable）
  * App/ 下的程序子目录（排除 AppInfo / DefaultData）
  * 既有 configs/*.yaml 的 version_source 配置

只做只读扫描，输出 JSON 到 stdout + 写入 _shared/update/_facts.json，
供 gen_update_strategies.py 消费。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402
CONFIG_DIR = REPO_ROOT / "_shared" / "configs"
OUT = REPO_ROOT / "_shared" / "update" / "_facts.json"


def decode(raw: bytes):
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "gb18030", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def ini_field(text: str, key: str):
    m = re.search(r"(?im)^\s*%s\s*=\s*(.*)$" % re.escape(key), text)
    return m.group(1).strip() if m else None


def pkg_dirs():
    """真正的包：走 _paths.packages()（迁移后仓库里仍有 portableapps/ 源树，
    产物在仓库外的产品根，老条件 `(p/'dist').is_dir()` 会漏包）。"""
    return sorted(REPO_ROOT / n for n in _paths.packages()
                  if n.endswith("Portable"))


def dist_of(pkgdir: Path):
    """产品目录：迁移后 <产品根>/<Pkg>，迁移前 <Repo>/<Pkg>/dist/<Pkg>。"""
    d = _paths.product_dir(pkgdir.name)
    return d if d.is_dir() else None


def collect(pkgdir: Path):
    name = pkgdir.name
    info = dict(pkg=name)
    d = dist_of(pkgdir)
    # 产品目录可能在仓库外，relative_to 会抛 ValueError，直接存绝对路径
    info["dist"] = str(d) if d else None
    info["product_tree"] = _paths.product_tree_in_use(name)
    if not d:
        info["error"] = "无产品目录（产品根=%s）" % _paths.product_root()
        return info

    # --- appinfo ---
    ai = d / "App" / "AppInfo" / "appinfo.ini"
    if ai.is_file():
        t = decode(ai.read_bytes())
        info["appinfo_version"] = ini_field(t, "PackageVersion")
        info["display_version"] = ini_field(t, "DisplayVersion")
        info["appinfo_name"] = ini_field(t, "Name")
    else:
        info["appinfo_version"] = None

    # --- App 子目录 ---
    app = d / "App"
    if app.is_dir():
        subs = sorted(x.name for x in app.iterdir()
                      if x.is_dir() and x.name not in
                      ("AppInfo", "DefaultData"))
    else:
        subs = []
    info["app_subdirs"] = subs

    # --- Launcher ---
    ld = d / "App" / "AppInfo" / "Launcher"
    launchers = []
    if ld.is_dir():
        for f in sorted(ld.glob("*.ini")):
            t = decode(f.read_bytes())
            exe = ini_field(t, "ProgramExecutable")
            launchers.append(dict(ini=f.stem, exe=exe))
    info["launchers"] = launchers

    # 主入口：优先与包同名（去掉 Portable）的 ini
    base = name[:-len("Portable")] if name.endswith("Portable") else name
    main = None
    for l in launchers:
        if l["ini"].lower() == name.lower():
            main = l
            break
    if main is None:
        for l in launchers:
            if l["ini"].lower() == base.lower():
                main = l
                break
    if main is None and launchers:
        main = launchers[0]
    info["main_launcher"] = main
    info["entry_exe"] = main["exe"] if main else None

    # --- 既有配置 ---
    y = CONFIG_DIR / ("%s.yaml" % name)
    cfg = {}
    if y.is_file():
        t = decode(y.read_bytes())
        for k in ("version_source", "update_policy", "schedule",
                  "package_type", "app_subdir", "entry_exe"):
            m = re.search(r"(?im)^\s*%s\s*:\s*(.*)$" % re.escape(k), t)
            if m:
                cfg[k] = m.group(1).strip()
        # version_source 常是多行块，抓 type / url / regex
        for k in ("type", "url", "repo", "asset_regex", "version_regex",
                  "download_page"):
            m = re.search(r"(?im)^\s*%s\s*[:=]\s*(.*)$" % re.escape(k), t)
            if m:
                cfg["vs_" + k] = m.group(1).strip().strip('"\'')
    info["config"] = cfg
    info["has_config"] = bool(cfg)
    return info


def main():
    rows = [collect(p) for p in pkg_dirs()]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("包数: %d -> %s" % (len(rows), OUT))
    print()
    hdr = "%-24s %-14s %-16s %s" % ("PKG", "VERSION", "ENTRY", "APP_SUBDIRS")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        subs = ",".join(r.get("app_subdirs") or [])
        print("%-24s %-14s %-16s %s"
              % (r["pkg"], r.get("appinfo_version") or "-",
                 (r.get("entry_exe") or "-")[:16], subs[:60]))
    miss = [r["pkg"] for r in rows if not r.get("app_subdirs")]
    if miss:
        print()
        print("无 App 子目录（需人工确认 app_subdir）: %s" % ", ".join(miss))
    return 0


if __name__ == "__main__":
    sys.exit(main())
