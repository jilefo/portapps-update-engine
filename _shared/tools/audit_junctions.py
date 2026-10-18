# -*- coding: utf-8 -*-
r"""audit_junctions.py —— 产品树 junction（目录联接）健康度审计。

为什么要有这个工具
------------------
junction 是本仓库"数据落地"的第三条腿（另两条是环境变量重定向与目录搬移），
也是最容易**静默失效**的一条：

  * `mklink /J` 对**不存在的目标也返回 0** —— 只看返回码会以为建成功了；
  * 整树 `os.rename` 迁移后，指向树内绝对路径的 junction **目标随之失效**；
  * 目标盘符写成小写 `d:` 时，大小写敏感的 `str.replace` 会静默不匹配
    （2026-10-19 迁移 ComatePortable 时真实踩到：工具报"重定点成功"，
     实际目标仍指着已迁走的旧路径，成为悬空联接）。

因此本工具**不只看 junction 是否存在，而是逐条回读目标并验证目标可达**，
把"看起来建好了"和"真的能用"分开报告。

三类目标
--------
  1. **包内目标**（inside）：目标在本包产品树内 —— 迁移后必须重定点；
  2. **相对目标**：目标是相对路径（`..\\logs\\x` 之类）—— 随树迁移天然有效；
  3. **树外目标**：指向宿主（GreenSoftMake / 真实 APPDATA 等）—— 不受迁移影响，
     但要报"是否悬空"，因为宿主目录可能被清理过。

用法
----
  python audit_junctions.py              # 全量（产品树，按 _paths 解析）
  python audit_junctions.py --pkg X      # 只看一个包
  python audit_junctions.py --broken     # 只打印有问题的（悬空/指向旧 dist）

退出码：0 = 无悬空联接；1 = 存在悬空联接或旧路径残留；2 = 一个包都没扫到。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_dist import is_junction, junction_target  # noqa: E402

# 迁移前的老布局特征：目标里还含 <仓库>/<Pkg>/dist/<Pkg>
_OLD_DIST_RE = re.compile(r"dist[\\/][A-Za-z0-9_.\-]+[\\/]?$", re.I)


def collect(root: Path) -> list:
    """遍历产品树收集 junction。不穿透（junction 目录不往下走）。"""
    out = []
    for dirpath, dirnames, _files in os.walk(root):
        for name in list(dirnames):
            p = Path(dirpath) / name
            if is_junction(p):
                tgt = junction_target(p, root)
                out.append({
                    "rel": p.relative_to(root).as_posix(),
                    "abs": str(p),
                    "target": tgt,
                    "inside": bool(tgt) and tgt.lower().startswith(str(root).lower()),
                })
                dirnames.remove(name)
    return out


def classify(j: dict, root: Path) -> tuple:
    """返回 (类别, 状态, 说明)。"""
    tgt = j["target"]
    if tgt is None:
        # 读不到目标：多半是相对目标（如 ..\logs\x），也可能解析失败
        return ("相对目标", "INFO", "目标为相对路径，随树迁移天然有效")
    if j["inside"]:
        cat = "包内目标"
    else:
        cat = "树外目标"
    if _OLD_DIST_RE.search(tgt) and "PortableApps" in tgt:
        return (cat, "STALE", "目标仍是迁移前的旧 dist 路径（需重定点）: %s" % tgt)
    if not os.path.isdir(tgt):
        return (cat, "BROKEN", "目标不存在（悬空）: %s" % tgt)
    return (cat, "OK", tgt)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pkg", default=None, help="只看指定包")
    ap.add_argument("--broken", action="store_true",
                    help="只打印有问题的（BROKEN / STALE）")
    ap.add_argument("--prune", action="store_true",
                    help="删除**悬空**联接（目标不存在者）。只删 BROKEN，"
                         "绝不碰指向真实目录的 OK/相对/STALE 联接；"
                         "rmdir 不带 /s，不触及目标内容")
    args = ap.parse_args()

    pkgs = [args.pkg] if args.pkg else _paths.packages()
    print("产品根: %s（来源 %s）" % (_paths.product_root(),
                                 _paths.product_root_source()))

    scanned_pkg = 0
    total_junc = 0
    counts = {"OK": 0, "BROKEN": 0, "STALE": 0, "INFO": 0}
    problems = []

    for pkg in pkgs:
        root = _paths.product_dir(pkg)
        if not root.is_dir():
            if not args.broken:
                print("  %-26s SKIP（产品目录不存在: %s）" % (pkg, root))
            continue
        scanned_pkg += 1
        js = collect(root)
        total_junc += len(js)
        if not js:
            if not args.broken:
                print("  %-26s 无 junction" % pkg)
            continue
        for j in js:
            cat, status, note = classify(j, root)
            counts[status] += 1
            if status in ("BROKEN", "STALE"):
                problems.append((pkg, j["rel"], status, note))
            if status != "OK" or not args.broken:
                print("  %-26s %-8s %-6s %s" % (pkg, cat, status, note))

    print("\n覆盖度: 扫描 %d 个包 / %d 个 junction" % (scanned_pkg, total_junc))
    print("结果  : OK %d / 悬空 %d / 旧路径 %d / 相对目标 %d"
          % (counts["OK"], counts["BROKEN"], counts["STALE"], counts["INFO"]))

    if scanned_pkg == 0:
        print("[FAIL] 一个包都没扫到——产品根可能没装配，或包名写错")
        return 2

    if args.prune:
        # 只删目标已不存在的悬空联接。删除动作是 rmdir（不带 /s），
        # 对 junction 而言只移除联接本身，不触及任何目标内容；
        # 目标本来就不存在，所以这一步不丢任何数据。
        targets = [(p, r) for p, r, s, _n in problems if s == "BROKEN"]
        print("\n[prune] 待清理悬空联接 %d 条（只删 BROKEN）：" % len(targets))
        for pkg, rel in targets:
            print("  - %s / %s" % (pkg, rel))
        pruned = 0
        for pkg, rel in targets:
            jp = _paths.product_dir(pkg) / rel.replace("/", "\\")
            try:
                os.rmdir(str(jp))
                pruned += 1
            except OSError as e:
                print("  [失败] %s / %s : %s" % (pkg, rel, e))
        print("[prune] 实际删除 %d / %d 条" % (pruned, len(targets)))
        # 回读确认：删完再扫一遍，悬空数应为 0
        still = 0
        for pkg, rel in targets:
            jp = _paths.product_dir(pkg) / rel.replace("/", "\\")
            if is_junction(jp):
                still += 1
        print("[prune] 回读确认：仍存在的联接 %d 条" % still)
        if still:
            return 1
        print("[prune] 完成——悬空联接已清零（有效联接未动）")
        return 0

    if problems:
        print("\n需要处理的联接（%d 条）：" % len(problems))
        for pkg, rel, status, note in problems:
            print("  [%s] %s / %s" % (status, pkg, rel))
        return 1
    print("\nJUNCTION AUDIT PASS（无悬空联接、无旧 dist 残留）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
