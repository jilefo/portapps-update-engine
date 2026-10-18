# -*- coding: utf-8 -*-
r"""
audit_launch_health.py —— 便携包「启动/数据/卡顿」健康度静态审计（只读）

针对用户关注的三大类问题做全量扫描：
  A. 启动异常    —— Launcher ini 缺失 / ProgramExecutable 指不到真文件 / 入口 exe 无 ini
  B. 数据保存不对 —— 环境变量重定向不全 / Data 目录缺失 / 数据写进 App 程序目录
  C. 卡顿        —— Custom.nsh 里 PowerShell / nsExec 调用次数（每次 1~2s）

用法：
  python audit_launch_health.py                 # 审计产品树（默认）
  python audit_launch_health.py --tree source   # 审计 portableapps 源树
  python audit_launch_health.py --json out.json # 导出 JSON

退出码：0 = 无 ERROR 级问题；1 = 存在 ERROR。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 产品根唯一解析处（dist 迁移到 D:\Portapps 后由它接管路径）。
# 不放 try/except：_paths.py 缺失本身就是必须立刻发现的故障。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402


# ── 仓库根推导（与既有脚本一致）──────────────────────────────────────────
def repo_root() -> Path:
    env = os.environ.get("PORTABLEAPPS_ROOT")
    if env:
        return Path(env).resolve()
    return _paths.REPO_ROOT


MARK_SELFHEAL = "Custom.nsh_Init"

# 环境变量：必须重定向（否则数据落宿主）
MUST_HAVE = ("APPDATA", "LOCALAPPDATA")
# 建议重定向
SHOULD_HAVE = ("TEMP", "TMP")
# 高危：重定向 USERPROFILE 会让 Electron/Chromium 崩溃或行为异常
RISKY = ("USERPROFILE", "HOMEDRIVE", "HOMEPATH")

# 数据类目录名（出现在 App 程序目录下 = 数据泄进程序目录）
DATA_DIR_HINTS = {
    "data", "settings", "config", "configs", "userdata", "user data",
    "cache", "logs", "log", "temp", "tmp", "db", "databases",
    "profiles", "profile", "sessions", "storage", "crashdumps", "crashpad",
}


# ── ini 读取（兼容 UTF-8 / UTF-16LE / GBK）─────────────────────────────
def read_ini(path: Path) -> tuple[str, str]:
    """返回 (文本, 编码名)。读不出返回 ('', '?')。"""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        for enc in ("utf-16", "utf-16-le"):
            try:
                return raw.decode(enc), enc
            except Exception:
                pass
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", "replace"), "utf-8-bom"
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return "", "?"


def ini_section(text: str, section: str) -> dict[str, str]:
    """极简 ini 取段（不去重，后写覆盖先写）。"""
    out: dict[str, str] = {}
    cur = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(";") or s.startswith("#"):
            continue
        m = re.match(r"^\[(.+?)\]\s*$", s)
        if m:
            cur = m.group(1).strip()
            continue
        if cur and cur.lower() == section.lower() and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def has_bom(path: Path) -> bool:
    return path.read_bytes()[:3] == b"\xef\xbb\xbf"


def is_utf16(path: Path) -> bool:
    return path.read_bytes()[:2] in (b"\xff\xfe", b"\xfe\xff")


# ── 单包审计 ──────────────────────────────────────────────────────────
def audit_pkg(pkg_dir: Path, tree: str = "dist", pkg_name: str = "") -> dict:
    # 源树目录统一叫 portableapps，包名要取父目录
    name = pkg_name or (pkg_dir.parent.name if tree == "source" else pkg_dir.name)
    R: dict = {"pkg": name, "path": str(pkg_dir), "error": [], "warn": [], "info": []}
    add_e = lambda m: R["error"].append(m)
    add_w = lambda m: R["warn"].append(m)
    is_dist = (tree == "dist")

    appinfo_dir = pkg_dir / "App" / "AppInfo"
    launcher_dir = appinfo_dir / "Launcher"
    app_dir = pkg_dir / "App"
    data_dir = pkg_dir / "Data"

    # ── 1. 入口 exe vs Launcher ini 配对 ────────────────────────────────
    exes = sorted(p for p in pkg_dir.glob("*.exe") if p.is_file())
    if not exes:
        if is_dist:
            add_e("包根没有 *.exe（产物不完整）")
        # 源树本就没有 exe，跳过配对检查
        exes = []
    if not is_dist:
        exes = []
    inis = sorted(launcher_dir.glob("*.ini")) if launcher_dir.is_dir() else []
    ini_base = {p.stem for p in inis}

    for exe in exes:
        if exe.stem not in ini_base:
            add_e(f"入口 {exe.name} 没有对应的 Launcher/{exe.stem}.ini（PAL 按 $BaseName 定位，必然启动失败）")
    if is_dist:
        for p in inis:
            if not (pkg_dir / f"{p.stem}.exe").exists() and p.stem.lower() != "appinfo":
                add_w(f"Launcher/{p.name} 没有同名 exe（多入口残留，PAL 永远读不到它）")

    # ── 2. 逐个 ini 深查 ────────────────────────────────────────────────
    env_all: dict[str, str] = {}
    for ini in inis:
        if ini.stem.lower() == "appinfo":
            continue
        txt, enc = read_ini(ini)
        R["info"].append(f"{ini.name} 编码={enc}")
        # 编码护栏（关键：注释行里的中文是安全的，只有「NSIS 真会读的键值」
        # 含非 ASCII 才会被 NSIS 按 ANSI 解成乱码 → 路径错 → 启动失败）
        payload = "\n".join(
            l for l in txt.splitlines()
            if l.strip() and not l.lstrip().startswith((";", "#"))
        )
        if any(ord(c) > 127 for c in payload):
            if not is_utf16(ini):
                add_e(f"{ini.name} 的「有效键值」含非 ASCII 但不是 UTF-16LE（实为 {enc}）→ NSIS 按 ANSI 解会乱码、启动失败")
        if has_bom(ini):
            first = txt.splitlines()[0].strip() if txt.splitlines() else ""
            if first.startswith("["):
                add_e(f"{ini.name} 带 UTF-8 BOM 且首行是段名 [{first.strip('[]')}] → 该段整体读不到")
            else:
                add_w(f"{ini.name} 带 UTF-8 BOM（首行是注释，暂不影响；但段名若上移会立刻失效）")

        launch = ini_section(txt, "Launch")
        env = ini_section(txt, "Environment")
        env_all.update(env)

        pe = launch.get("ProgramExecutable", "")
        if not pe:
            add_w(f"{ini.name} 缺 [Launch].ProgramExecutable")
        else:
            # 变量展开
            cand = pe.replace("%PAL:AppDir%", str(app_dir)).replace("%AppDir%", str(app_dir))
            cand = os.path.expandvars(cand)
            if not os.path.isabs(cand):
                cand = str(app_dir / cand)
            # 源树只有元数据，程序在 dist 树；存在性只在 dist 判
            if is_dist and not Path(cand).exists():
                add_e(f"{ini.name} 的 ProgramExecutable 指向不存在的文件：{pe}")
        if not launch.get("DirectoryMoveOK"):
            add_w(f"{ini.name} 未设置 DirectoryMoveOK")

    # ── 3. 环境变量重定向完整性 ─────────────────────────────────────────
    have = {k.upper(): v for k, v in env_all.items()}
    for k in MUST_HAVE:
        if k not in have:
            add_e(f"[Environment] 缺 {k} 重定向 → 用户数据落宿主 %%{k}%%（数据保存不对）")
    for k in SHOULD_HAVE:
        if k not in have:
            add_w(f"[Environment] 缺 {k} 重定向 → 临时文件落宿主")
    for k in RISKY:
        if k in have:
            add_w(f"[Environment] 重定向了 {k}（高风险：Electron/Chromium 可能崩或取不到路径）")

    # ── 4. Data 目录 ────────────────────────────────────────────────────
    if not data_dir.exists():
        if is_dist:
            add_w("包内没有 Data/ 目录（首次启动会建，若长期为空说明重定向失效）")
    else:
        try:
            n = sum(1 for _ in data_dir.iterdir())
            R["info"].append(f"Data/ 顶层条目 {n}")
        except Exception:
            pass

    # ── 5. 数据泄进 App 程序目录 ────────────────────────────────────────
    leaks = []
    if is_dist and app_dir.is_dir():
        for sub in app_dir.iterdir():
            if not sub.is_dir() or sub.name == "AppInfo":
                continue
            # 最多下探 2 层，避免扫大目录
            for lvl1 in list(sub.iterdir())[:200]:
                if lvl1.is_dir() and lvl1.name.lower() in DATA_DIR_HINTS:
                    sz = 0
                    cnt = 0
                    try:
                        for f in lvl1.rglob("*"):
                            if f.is_file():
                                try:
                                    sz += f.stat().st_size
                                except Exception:
                                    pass
                                cnt += 1
                                if cnt >= 3000:   # 采样上限，避免扫大目录超时
                                    sz = max(sz, 1024 * 1024 + 1)
                                    break
                    except Exception:
                        sz = -1
                    if sz > 1024 * 1024:  # > 1MB 才算真泄漏
                        leaks.append(f"{lvl1.relative_to(pkg_dir)} ({sz//1024//1024}MB)")
    if leaks:
        add_w("App/ 程序目录下发现数据目录（>1MB，可能随包带走/更新时被覆盖）：" + "; ".join(leaks[:5]))

    # ── 6. Custom.nsh：自愈钩子 + PowerShell 调用次数 ───────────────────
    nsh = launcher_dir / "Custom.nsh"
    if not nsh.exists():
        add_w("没有 Custom.nsh")
    else:
        raw = nsh.read_bytes()
        if has_bom(nsh):
            add_e("Custom.nsh 带 UTF-8 BOM → NSIS Invalid command")
        try:
            txt = raw.decode("utf-8")
        except Exception:
            txt = raw.decode("utf-8", "replace")
            add_e("Custom.nsh 不是合法 UTF-8")
        if MARK_SELFHEAL not in txt:
            add_e("Custom.nsh 缺自愈钩子 Custom.nsh_Init（异常退出残留会让下次启动弹窗且不启动）")
        ps = len(re.findall(r"(?i)powershell|pwsh", txt))
        ns = len(re.findall(r"nsExec::Exec", txt))
        R["ps_calls"] = ps
        R["nsexec_calls"] = ns
        if ps >= 4:
            add_w(f"Custom.nsh 内 PowerShell 调用 {ps} 次（每次约 1~2s 冷启动开销，卡顿主因）")
        R["nsh_lines"] = len(txt.splitlines())

    return R


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default="dist", choices=["dist", "source", "both"])
    ap.add_argument("--json", default="")
    ap.add_argument("--only", default="", help="只审计指定包（逗号分隔）")
    args = ap.parse_args()

    root = repo_root()
    trees = []
    if args.tree in ("dist", "both"):
        # 产品树统一走 _paths.product_dir()：迁移后自动读 D:\Portapps\<Pkg>，
        # 未迁移时自动回退仓库内 dist/<Pkg>，两个状态行为一致。
        dist_dirs = []
        for pkg in _paths.packages():
            d = _paths.product_dir(pkg)
            if d.is_dir() and (d / "App").is_dir():
                dist_dirs.append(d)
        trees.append(("dist", dist_dirs))
    if args.tree in ("source", "both"):
        trees.append(("source", [p / "portableapps" for p in sorted(root.iterdir()) if (p / "portableapps" / "App").is_dir()]))

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    results = []
    for tname, dirs in trees:
        for d in dirs:
            # source 树的目录名统一是 portableapps，过滤要用父目录的真实包名
            nm = d.parent.name if tname == "source" else d.name
            if only and nm not in only:
                continue
            r = audit_pkg(d, tname, nm)
            r["tree"] = tname
            results.append(r)

    # 汇总（自报覆盖度：读了哪个产品根、审了几个包，不悄悄报 OK）
    n_err = sum(len(r["error"]) for r in results)
    n_warn = sum(len(r["warn"]) for r in results)
    if any(t == "dist" for t, _ in trees):
        print("产品根: %s（来源：%s）" % (_paths.product_root(),
                                        _paths.product_root_source()))
    print(f"审计 {len(results)} 个包 —— ERROR {n_err} 条 / WARN {n_warn} 条\n")

    bad = [r for r in results if r["error"]]
    for r in bad:
        print(f"[ERROR] {r['tree']}/{r['pkg']}")
        for m in r["error"]:
            print(f"    - {m}")
    if bad:
        print()

    wn = [r for r in results if r["warn"]]
    for r in wn:
        print(f"[WARN ] {r['tree']}/{r['pkg']}")
        for m in r["warn"]:
            print(f"    - {m}")

    # 卡顿榜
    print("\n=== 卡顿风险榜（Custom.nsh PowerShell 调用次数，降序）===")
    perf = [r for r in results if r.get("ps_calls", 0) > 0]
    for r in sorted(perf, key=lambda x: -x.get("ps_calls", 0))[:12]:
        print(f"  {r['tree']}/{r['pkg']:<24} ps={r.get('ps_calls')} nsExec={r.get('nsexec_calls')} lines={r.get('nsh_lines')}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON -> {args.json}")

    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
