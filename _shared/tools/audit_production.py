# -*- coding: utf-8 -*-
# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
REPO_ROOT_F = REPO_ROOT.replace("\\", "/")
_TOOLS_DIR_F = str(_Path(__file__).resolve().parent).replace("\\", "/")
# <<< 路径自适应
r"""audit_production.py —— 便携软件生产级静态审计（开源完备性 + 数据落地配置）

不启动任何应用，纯静态扫描，可与 3 轮动态冒烟互补。

审计维度：
  A 开源完备性  LICENSE / README / .gitignore / CHANGELOG / CONTRIBUTING /
               CODE_OF_CONDUCT / .editorconfig / docs / .github
  B PAL 结构    dist/<Pkg>.exe、App\AppInfo\appinfo.ini、Launcher\<Pkg>.ini、
               help.html、Other\Source、portableapps 源树
  C 数据落地    [Environment] APPDATA/LOCALAPPDATA 是否指向 %PAL:DataDir%、
               DirectoriesMove/FilesMove、[Activate]Registry、[RegistryKeys]
  D 风险项      USERPROFILE 重定向（Electron 崩溃）、ProgramExecutable 缺失、
               ExtractIcon 目标不存在、无 [Environment] 段

输出：
  reports/生产级审计-<stamp>.md
  reports/生产级审计-<stamp>.json
"""
import configparser
import json
import os
import sys as _sys
from datetime import datetime

# 产品根唯一解析处（dist 迁移到 D:\Portapps 后由它接管路径）。
# 不放 try/except：_paths.py 缺失本身就是必须立刻发现的故障。
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _paths                                     # noqa: E402

ROOT = REPO_ROOT
OUT = REPO_ROOT + r"\docs\reports"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

OSS_FILES = ["LICENSE", "README.md", ".gitignore", "CHANGELOG.md",
             "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", ".editorconfig"]
OSS_DIRS = ["docs", ".github"]

DATA_ENV_KEYS = ("APPDATA", "LOCALAPPDATA")


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
    """编码自适应：UTF-8 / UTF-8-BOM / UTF-16LE 都能解析。

    注意：早先版本遇到 UTF-16 直接返回 None，结果 MiaoshouPortable 被
    误报成「APPDATA/LOCALAPPDATA 未重定向」——实际它两项都配了。
    含中文路径的 launcher ini 必须保持 UTF-16LE（NSIS 按 ANSI 解 UTF-8
    会路径乱码），所以审计工具必须能读 UTF-16，不能把它当错误。
    """
    enc = sniff(path)
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        if enc in ("utf-16", "utf-16-be"):
            with open(path, "rb") as f:
                text = f.read().decode(enc)
            cp.read_string(text)
        else:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                cp.read_file(f)
    except (OSError, configparser.Error, UnicodeDecodeError):
        return None
    return cp


def pkg_dirs():
    out = []
    for e in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, e)
        if e.startswith(("_", ".")):
            continue
        if os.path.isdir(p) and e.endswith("Portable"):
            out.append((e, p))
    return out


def launcher_inis(name, base):
    r"""返回 (产品树, portableapps 源树) 两处的 launcher ini 绝对路径。

    产品树从 _paths.product_dir() 取：迁移后是 D:\Portapps\<Pkg>，
    迁移前回退到 <Repo>/<Pkg>/dist/<Pkg>，两者对审计透明。
    """
    res = []
    prod = _paths.product_dir(name)
    for d in (os.path.join(str(prod), "App", "AppInfo", "Launcher"),
              os.path.join(base, "portableapps", "App", "AppInfo", "Launcher")):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".ini"):
                res.append(os.path.join(d, f))
    return res


def dist_path(name, *rel):
    """产品树下的相对路径。dist 迁移后自动指向 D:\\Portapps\\<Pkg>。"""
    return os.path.join(str(_paths.product_dir(name)), *rel)


def audit_pkg(name, base):
    r = {"name": name, "oss_missing": [], "struct_missing": [],
         "env": {}, "risks": [], "inis": [], "data_ok": True,
         "data_notes": []}
    # A 开源完备性
    for f in OSS_FILES:
        if not os.path.isfile(os.path.join(base, f)):
            r["oss_missing"].append(f)
    for d in OSS_DIRS:
        if not os.path.isdir(os.path.join(base, d)):
            r["oss_missing"].append(d + "/")
    # B PAL 结构
    exe = dist_path(name, name + ".exe")
    if not os.path.isfile(exe):
        r["struct_missing"].append("%s.exe" % name)
    checks = (
        ("%s.exe" % name, exe),
        ("App/AppInfo/appinfo.ini",
         dist_path(name, "App", "AppInfo", "appinfo.ini")),
        ("App/AppInfo/Launcher/%s.ini" % name,
         dist_path(name, "App", "AppInfo", "Launcher", name + ".ini")),
        ("help.html", dist_path(name, "help.html")),
        ("Other/Source", dist_path(name, "Other", "Source")),
        ("portableapps/App/AppInfo/appinfo.ini",
         os.path.join(base, "portableapps", "App", "AppInfo", "appinfo.ini")),
    )
    for rel, p in checks:
        if not os.path.isfile(p) and not os.path.isdir(p):
            r["struct_missing"].append(rel)
    # C 数据落地
    inis = launcher_inis(name, base)
    r["inis"] = [os.path.relpath(p, base).replace(os.sep, "/") for p in inis]
    envmap = {}
    for p in inis:
        enc = sniff(p)
        cp = read_ini(p)
        if not cp:
            r["risks"].append("ini 解析失败(%s): %s"
                              % (enc, os.path.basename(p)))
            continue
        if enc in ("utf-16", "utf-16-be"):
            # 不是缺陷，但要登记：含中文路径时必须保持此编码，禁止转码
            r["data_notes"].append("launcher ini 为 %s（含中文路径须保持，"
                                   "禁止转 UTF-8）" % enc)
        if cp.has_section("Environment"):
            for k, v in cp.items("Environment"):
                envmap[k.upper()] = v
        if not cp.has_section("Launch"):
            r["risks"].append("缺 [Launch]: " + os.path.basename(p))
        elif not cp.get("Launch", "ProgramExecutable", fallback="").strip():
            r["risks"].append("缺 ProgramExecutable: " + os.path.basename(p))
        for sec in ("DirectoriesMove", "FilesMove", "DirectoriesCleanup",
                    "FilesCleanup"):
            if cp.has_section(sec):
                r["data_notes"].append("%s: %s 项" % (sec, len(cp.items(sec))))
    r["env"] = envmap
    for k in DATA_ENV_KEYS:
        v = envmap.get(k, "")
        if not v:
            r["data_ok"] = False
            r["data_notes"].append("%s 未重定向" % k)
        elif "PAL:DataDir" not in v:
            r["data_ok"] = False
            r["data_notes"].append("%s 未指向 DataDir (%s)" % (k, v))
    if "USERPROFILE" in envmap:
        r["risks"].append("★ 重定向 USERPROFILE（Electron 崩溃风险）: %s"
                          % envmap["USERPROFILE"])
    # appinfo ExtractIcon 目标存在性
    ai = os.path.join(base, "portableapps", "App", "AppInfo", "appinfo.ini")
    if not os.path.isfile(ai):
        ai = dist_path(name, "App", "AppInfo", "appinfo.ini")
    if os.path.isfile(ai):
        cp = read_ini(ai)
        if cp and cp.has_option("Control", "ExtractIcon"):
            ic = cp.get("Control", "ExtractIcon").replace("/", os.sep)
            # 应用二进制在产品树下（portableapps 源树只有元数据 +
            # DefaultData，直接查 portableapps 会 100% 误报）
            cands = [dist_path(name, "App", ic),
                     dist_path(name, ic),
                     os.path.join(base, "portableapps", "App", ic)]
            if not any(os.path.isfile(c) for c in cands):
                r["risks"].append("ExtractIcon 目标缺失: %s"
                                  % cp.get("Control", "ExtractIcon"))
    return r


def md(results):
    n = len(results)
    oss_bad = [r for r in results if r["oss_missing"]]
    st_bad = [r for r in results if r["struct_missing"]]
    data_bad = [r for r in results if not r["data_ok"]]
    risk_bad = [r for r in results if r["risks"]]
    L = ["# 便携软件生产级静态审计", "",
         "- 生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "- 包总数：%d" % n,
         "- 产品根：`%s`（来源：%s）"
         % (_paths.product_root(), _paths.product_root_source()),
         "",
         "## 1. 总览", "",
         "| 维度 | 合格 | 缺口 |", "|---|---|---|",
         "| 开源完备性（9 项） | %d | %d |" % (n - len(oss_bad), len(oss_bad)),
         "| PAL 结构完整性 | %d | %d |" % (n - len(st_bad), len(st_bad)),
         "| 数据落地重定向 | %d | %d |" % (n - len(data_bad), len(data_bad)),
         "| 零风险项 | %d | %d |" % (n - len(risk_bad), len(risk_bad)), ""]
    L += ["## 2. 逐包明细", "",
          "| # | 包 | 开源缺口 | 结构缺口 | 数据落地 | 风险 |",
          "|---|---|---|---|---|---|"]
    for i, r in enumerate(results, 1):
        L.append("| %d | %s | %s | %s | %s | %s |" % (
            i, r["name"],
            len(r["oss_missing"]) or "✓",
            len(r["struct_missing"]) or "✓",
            "✓" if r["data_ok"] else "✗",
            len(r["risks"]) or "✓"))
    L += ["", "## 3. 缺口与风险清单", ""]
    for r in results:
        bad = []
        if r["oss_missing"]:
            bad.append("开源: " + ", ".join(r["oss_missing"]))
        if r["struct_missing"]:
            bad.append("结构: " + ", ".join(r["struct_missing"]))
        if not r["data_ok"]:
            bad.append("数据: " + "; ".join(
                x for x in r["data_notes"]
                if ("未" in x) or ("PAL:DataDir" in x)))
        if r["risks"]:
            bad.append("风险: " + "; ".join(r["risks"]))
        if bad:
            L.append("### %s" % r["name"])
            for b in bad:
                L.append("- " + b)
            L.append("")
    return "\n".join(L)


def main():
    os.makedirs(OUT, exist_ok=True)
    pkgs = pkg_dirs()
    results = [audit_pkg(n, p) for n, p in pkgs]
    print("产品根:", _paths.product_root(), "（来源：%s）"
          % _paths.product_root_source())
    mp = os.path.join(OUT, "生产级审计-%s.md" % STAMP)
    jp = os.path.join(OUT, "生产级审计-%s.json" % STAMP)
    with open(mp, "w", encoding="utf-8") as f:
        f.write(md(results))
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("DONE ->", mp)
    print("DONE ->", jp)
    print("包数:", len(results))
    for r in results:
        if r["risks"] or not r["data_ok"]:
            print("  !", r["name"], r["risks"],
                  [x for x in r["data_notes"] if "未" in x])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
