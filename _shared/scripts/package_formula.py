# -*- coding: utf-8 -*-
r"""package_formula.py —— 把单包「配方」打成 zip（通用版，包名自动推导）

为什么不是 package-paf.py
------------------------
package-paf.py 打的是**产品树**（<产品根>/<Pkg>，含 App/ 下的第三方程序）。
但本仓库是「配方开源 + 二进制不随仓库分发」：

    portableapps/App/Cursor/   装第三方程序的地方 —— 被 .gitignore 排除
    入库的只有 9 个元数据文件（AppInfo / Launcher / 图标）

所以 CI 在新克隆上跑 build-portable.py 得到的，是「有启动器、无程序」的空壳；
把它发布出去没有意义。真正属于本仓库、也真正可发布的，是**配方**本身：

    <Pkg>/portableapps/**              便携化配置（NSIS + PAL 元数据）
    <Pkg>/LICENSE                      MIT
    <Pkg>/THIRD_PARTY_NOTICES.md       第三方权利声明（开源必带）
    <Pkg>/README.md                    包说明

产出
----
    <out>/<Pkg>-formula-<版本>.zip
    <out>/<Out>.../<Pkg>-formula-SHA256SUMS.txt

用法
----
    python _shared/scripts/package_formula.py <Pkg> [--out <目录>]

★ 覆盖度必须自报：打包了几个文件、多大、哪些可选文件不存在，都要打印出来。
  扫到 0 个文件还报「打包完成」，就是典型的假绿。
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402

import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

# 默认产物目录：与根级 release.py prepare 的 build/release 并列，均已被 .gitignore 排除
DEFAULT_OUT = "build/formula"

# 必带：没有就该报错，不该静默打出一个残缺的包
REQUIRED = ["portableapps"]
# 可选：不存在要计数说明，不算失败
OPTIONAL = ["LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"]

# 体积护栏：配方包不该出现大文件（第三方程序的漏网之鱼都体现为这里变大）
MAX_SINGLE = 20 * 1024 * 1024
MAX_TOTAL = 200 * 1024 * 1024


def default_outdir() -> Path:
    return REPO_ROOT / DEFAULT_OUT


def read_version() -> str:
    """取 appinfo.ini 的 PackageVersion；读不到返回 unknown。"""
    ai = REPO / "portableapps" / "App" / "AppInfo" / "appinfo.ini"
    if not ai.is_file():
        return "unknown"
    for enc in ("utf-8-sig", "utf-8", "utf-16-le", "mbcs"):
        try:
            txt = ai.read_text(encoding=enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
        m = re.search(r"(?im)^\s*PackageVersion\s*=\s*([0-9][0-9.\-]*)", txt)
        if m:
            return m.group(1).strip()
    return "unknown"


def artifact_paths(outdir: Path, ver: str):
    """产物路径的唯一定义处（print_artifact_paths.py 直接复用，避免两处各写一份）。"""
    base = f"{PKG}-formula-{ver}"
    return outdir / (base + ".zip"), outdir / (base + ".sha256.txt")


def _git_tracked(rels):
    """只取 git 跟踪的文件 → set(相对仓库根的 posix 路径)；不在 git 仓库时返回 None。

    ★ 为什么不能 rglob：
      早先用 rglob 扫文件系统，结果把本机留下的 Custom.nsh.bak-dot-20261018、
      appinfo.ini.bakfix 这类**未跟踪的本地备份**也打进了公开产物——
      本机跑和 CI 跑得到两份内容不同的 zip，且把垃圾发布了出去。
      以 git 跟踪集为准，才能保证"发布的就是仓库里的东西"、本机与 CI 一致。
    """
    try:
        r = subprocess.run(["git", "ls-files", "--"] + rels, cwd=str(REPO_ROOT),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except OSError:
        return None
    if r.returncode != 0:
        return None
    return {ln.strip().replace("\\", "/") for ln in r.stdout.splitlines() if ln.strip()}


def collect():
    """收集待打包文件 → [(绝对路径, zip 内相对路径)], 必带缺失, 可选缺失, 来源说明。"""
    req_prefix = ["%s/%s/" % (PKG, n) for n in REQUIRED]
    opt_paths = ["%s/%s" % (PKG, n) for n in OPTIONAL]
    tracked = _git_tracked(req_prefix + opt_paths)

    if tracked is None:
        # 不在 git 仓库里（例如把包目录单独拷出来）：退回扫盘，但如实说明
        src = "filesystem"
        items, missing, missing_opt = [], [], []
        for name in REQUIRED:
            d = REPO / name
            if not d.is_dir():
                missing.append(name)
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    items.append((p, "%s/%s" % (PKG, p.relative_to(REPO).as_posix())))
        for name in OPTIONAL:
            f = REPO / name
            (items.append((f, "%s/%s" % (PKG, name))) if f.is_file()
             else missing_opt.append(name))
        return items, missing, missing_opt, src

    src = "git"
    items = []
    for rel in sorted(tracked):
        abs_p = REPO_ROOT / rel
        if abs_p.is_file():
            items.append((abs_p, rel))
    missing = [n for n in REQUIRED
               if not any(r.startswith("%s/%s/" % (PKG, n)) for r in tracked)]
    missing_opt = [n for n in OPTIONAL if "%s/%s" % (PKG, n) not in tracked]
    return items, missing, missing_opt, src


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    outdir = default_outdir()
    if "--out" in sys.argv:
        i = sys.argv.index("--out")
        if i + 1 >= len(sys.argv):
            print("[FAIL] --out 缺参数")
            return 2
        outdir = Path(sys.argv[i + 1])

    if not REPO.is_dir():
        print(f"[FAIL] 包目录不存在: {REPO}")
        return 2

    items, missing, missing_opt, src = collect()
    if missing:
        print("[FAIL] 缺必带内容: %s" % ", ".join(missing))
        return 1
    if not items:
        # 空文件也能打出一个"成功"的 zip —— 这里必须当作失败
        print(f"[FAIL] {PKG}/portableapps/ 下没有可打包文件")
        return 1

    total = sum(p.stat().st_size for p, _ in items)
    big = [(p, p.stat().st_size) for p, _ in items
           if p.stat().st_size > MAX_SINGLE]

    ver = read_version()
    outdir.mkdir(parents=True, exist_ok=True)
    zpath, spath = artifact_paths(outdir, ver)

    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for abs_p, rel in items:
            z.write(abs_p, rel)

    s = sha256_file(zpath)
    spath.write_text("%s  %s\n" % (s, zpath.name), encoding="utf-8")

    print(f"[OK] {zpath}  文件 {len(items)} 个 / {total / 1024:.1f} KiB"
          f"  （来源：{src}）")
    print(f"[OK] {spath}")
    if missing_opt:
        print("    [i] 可选文件不存在（%d 个）：%s"
              % (len(missing_opt), ", ".join(missing_opt)))
    if ver == "unknown":
        print("    [i] appinfo.ini 未读到 PackageVersion，文件名用 unknown")

    if big:
        for p, sz in big[:5]:
            print("[FAIL] 单文件过大 %s（%.1f MiB）——疑似第三方程序混入配方"
                  % (p.relative_to(REPO).as_posix(), sz / 1024 / 1024))
        return 1
    if total > MAX_TOTAL:
        print("[FAIL] 配方包总体积 %.1f MiB 超上限 %d MiB——疑似混入二进制"
              % (total / 1024 / 1024, MAX_TOTAL // 1024 // 1024))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
