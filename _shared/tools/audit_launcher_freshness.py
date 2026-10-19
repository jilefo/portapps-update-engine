# -*- coding: utf-8 -*-
r"""audit_launcher_freshness.py —— 启动器「编译产物新鲜度」审计。

为什么要有这个工具
------------------
便携包有两棵树：`portableapps/`（构建输入，只有元数据）和产品树（可运行产物）。
按仓库硬约定，**改了源树必须重编，改源不重编等于没改**——
`Custom.nsh` 里挂着 junction 建立/拆除的钩子宏，启动器 exe 才是真正在跑的东西。

但这条约定此前没有门禁：
  * `WorkBuddyPortable` 的 exe 停在 2026-10-17，而 Custom.nsh 在 10-18 改过，
    因为当时便携实例正在运行、编译报 `Can't open output file`，就此搁置；
  * 2026-10-19 补扫又扫出 `SublimeTextPortable` 落后 5.6 小时。
  * 两例都是**两棵树 Custom.nsh 已经一致、只是 exe 没跟上**——
    单看文件内容发现不了，必须比时间戳。

本工具查三件事，任一不成立即判负：

  1. **exe 是否比 Custom.nsh 新**（落后 = 改了源没重编）；
  2. **两棵树 Custom.nsh 字节是否一致**（不同 = 源树改动没同步到产品树）；
  3. **exe / Custom.nsh 是否存在**（缺件会让包根本起不来）。

用法
----
  python audit_launcher_freshness.py            # 全量 39 包
  python audit_launcher_freshness.py --pkg X    # 只看一个包
  python audit_launcher_freshness.py --fix      # 对落后的包直接重编（先 .bak- 备份）

退出码：0 = 全部新鲜；1 = 存在落后/不一致/缺件；2 = 一个包都没扫到。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("PORTABLEAPPS_ROOT")
                 or str(Path(__file__).resolve().parents[2])).resolve()
sys.path.insert(0, str(REPO_ROOT / "_shared"))
import _paths  # noqa: E402


def scan(pkg: str):
    """返回 (问题列表, 落后秒数)。问题为空即新鲜。"""
    d = _paths.product_dir(pkg)
    exe = d / ("%s.exe" % pkg)
    nsh = d / "App" / "AppInfo" / "Launcher" / "Custom.nsh"
    src_nsh = (_paths.REPO_ROOT / pkg / "portableapps" / "App" / "AppInfo"
               / "Launcher" / "Custom.nsh")
    bad = []
    lag = 0.0
    if not exe.is_file():
        bad.append("缺 exe")
        return bad, lag
    if not nsh.is_file():
        bad.append("缺产品树 Custom.nsh")
        return bad, lag
    if not src_nsh.is_file():
        bad.append("缺源树 Custom.nsh")
    elif src_nsh.read_bytes() != nsh.read_bytes():
        bad.append("两棵树 Custom.nsh 不一致")
    if exe.stat().st_mtime < nsh.stat().st_mtime:
        lag = nsh.stat().st_mtime - exe.stat().st_mtime
        bad.append("exe 落后 Custom.nsh %.1f 小时" % (lag / 3600))
    return bad, lag


def rebuild(pkg: str) -> bool:
    """重编启动器，先 .bak- 备份旧 exe。"""
    exe = _paths.product_dir(pkg) / ("%s.exe" % pkg)
    if exe.is_file():
        shutil.copy2(exe, str(exe) + ".bak")
    cp = subprocess.run(
        [sys.executable,
         str(_paths.REPO_ROOT / "_shared" / "tools" / "build_launcher.py"),
         str(_paths.product_dir(pkg))],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (cp.stdout or "") + (cp.stderr or "")
    ok = "[OK]" in out or cp.returncode == 0
    if not ok:
        print("      ! %s" % out.strip().splitlines()[-1][:110])
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pkg", default=None)
    ap.add_argument("--fix", action="store_true",
                    help="对落后的包重编（先写 .bak- 备份）")
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    pkgs = [args.pkg] if args.pkg else list(_paths.packages())
    n = 0
    n_bad = 0
    fixed = 0
    for pkg in pkgs:
        n += 1
        bad, _ = scan(pkg)
        if not bad:
            print("  %-26s OK" % pkg)
            continue
        n_bad += 1
        print("  %-26s %s" % (pkg, "；".join(bad)))
        if args.fix and any("落后" in b for b in bad):
            if rebuild(pkg):
                again, _ = scan(pkg)
                if not again:
                    print("      -> 已重编，复查 OK")
                    fixed += 1
                else:
                    print("      -> 重编后仍有问题: %s" % "；".join(again))
            else:
                print("      -> 重编失败")

    print("-" * 64)
    print("扫描 %d 个包：新鲜 %d / 有问题 %d%s"
          % (n, n - n_bad, n_bad, ("，已重编 %d" % fixed) if fixed else ""))
    if n == 0:
        print("FRESHNESS SCAN FAIL（一个包都没扫到）")
        return 2
    if n_bad:
        print("FRESHNESS SCAN FAIL")
        return 1
    print("FRESHNESS SCAN PASS（启动器产物全部与源同步）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
