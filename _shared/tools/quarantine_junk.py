# -*- coding: utf-8 -*-
r"""quarantine_junk.py —— 把无用文件**移动**到隔离区（不删除，可整体回滚）

对应提示词「三、清理多余文件」：
  - 删除前保留备份或可回滚记录 → 本工具一律 **move 到隔离区**，不 unlink；
    想彻底删除，确认清单无误后再删隔离区即可。
  - 仅删除明确无用文件 → 三类硬排除，宁可漏删不可误删：

    ★ 排除 1  用户数据：dist/<Pkg>/Data/ 与 portableapps/Data/
              （应用自身产生的日志/缓存/模型/下载物，误删=丢用户数据。
               深度审计曾把 332,052 个文件 / 19.97 GB 误判成垃圾）
    ★ 排除 2  回滚材料：_shared/update/_backups/（更新引擎的旧版本备份，
              删了就没法 rollback）
    ★ 排除 3  dist 子树：即将整体迁移到 D:\Portapps，先删再迁没有意义；
              且 Other/Active.7z 等是更新器的暂存产物

  隔离区默认 <仓库根>/../GreenSoftMake/_cleanup_quarantine_<日期>/，
  可用 --dest 覆盖。目录结构原样保留，另写 manifest.json（原路径/大小/原因/目标）。

用法：
  python _shared/tools/quarantine_junk.py --dry-run   # 只看清单不动文件
  python _shared/tools/quarantine_junk.py --apply     # 执行移动
  python _shared/tools/quarantine_junk.py --rollback <manifest.json>
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = os.environ.get("PORTABLEAPPS_ROOT") or str(HERE.parents[2])
REPO = Path(REPO_ROOT)

# 复用 audit_pre_release 的判定逻辑，避免两套标准漂移
_spec = importlib.util.spec_from_file_location(
    "audit_pre_release", HERE.parent / "audit_pre_release.py")
_apr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_apr)

# 硬排除逻辑统一在 is_excluded()（三类：用户数据 / 回滚备份 / dist 子树），
# 判定标准复用 audit_pre_release，避免两套标准漂移。
# 注：2026-10-18 迁移后产品在仓库外 <产品根>，仓库内 dist/ 不再产生，
# "dist 子树"排除项对回退布局（本地构建）仍然生效，属保留项。


def is_excluded(rel):
    """rel 为 / 分隔的仓库相对路径。"""
    if _apr.is_user_data(rel):
        return "用户数据（禁止清理）"
    if rel.startswith("_shared/update/_backups/"):
        return "更新引擎回滚备份（删了无法 rollback）"
    if re.match(r"^[^/]+/dist/", rel):
        return "dist 子树（将整体迁往 D:\\Portapps，先删再迁无意义）"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="执行移动（默认只看）")
    ap.add_argument("--dry-run", action="store_true", help="同默认")
    ap.add_argument("--dest", default=None,
                    help="隔离区目录，默认 <仓库根>/../GreenSoftMake/"
                         "_cleanup_quarantine_<YYYYMMDD>/")
    ap.add_argument("--rollback", default=None, help="按 manifest.json 回滚")
    args = ap.parse_args()

    if args.rollback:
        return do_rollback(args.rollback)

    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    _apr.scan_junk(True, rows)

    picked, skipped = [], []
    for rel, why, sz, isdir in rows:
        rel = rel.replace("\\", "/")
        reason = is_excluded(rel)
        (skipped if reason else picked).append((rel, why, sz, isdir, reason))

    dest = Path(args.dest) if args.dest else (
        REPO.parent / "GreenSoftMake" /
        ("_cleanup_quarantine_%s" % time.strftime("%Y%m%d")))
    manifest = dest / "manifest.json"

    print("=" * 72)
    print("无用文件隔离（%s）" % ("执行移动" if args.apply else "预演，不动文件"))
    print("隔离区：%s" % dest)
    print("=" * 72)
    tot = sum(r[2] for r in picked)
    print("\n将隔离 %d 项 / %.2f MB：" % (len(picked), tot / 1048576))
    for rel, why, sz, isdir, _ in sorted(picked, key=lambda r: -r[2])[:25]:
        print("  %-64s %-10s %8.1f KB%s"
              % (rel[:64], why, sz / 1024, "/" if isdir else ""))
    if len(picked) > 25:
        print("  ...另有 %d 项" % (len(picked) - 25))

    print("\n保留不动 %d 项：" % len(skipped))
    byreason = {}
    for rel, why, sz, isdir, reason in skipped:
        byreason.setdefault(reason, [0, 0])
        byreason[reason][0] += 1
        byreason[reason][1] += sz
    for reason, (n, b) in byreason.items():
        print("  %-40s %4d 项  %8.1f MB" % (reason, n, b / 1048576))

    if not args.apply:
        print("\n（预演）加 --apply 才真正移动。移动而非删除，可随时回滚。")
        return 0

    dest.mkdir(parents=True, exist_ok=True)
    recs, done, failed = [], 0, []
    for rel, why, sz, isdir, _ in sorted(picked):
        src = REPO / rel.replace("/", os.sep)
        dst = dest / rel.replace("/", os.sep)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                failed.append((rel, "目标已存在，跳过避免覆盖"))
                continue
            shutil.move(str(src), str(dst))
            recs.append({"src": rel, "size": sz, "reason": why,
                         "dest": str(dst)})
            done += 1
        except (OSError, shutil.Error) as e:
            failed.append((rel, str(e)))

    manifest.write_text(json.dumps(
        {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
         "quarantine": str(dest), "count": len(recs),
         "total_bytes": sum(r["size"] for r in recs), "items": recs},
        ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n已移动 %d 项，失败 %d 项。" % (done, len(failed)))
    for rel, err in failed:
        print("  [失败] %s —— %s" % (rel, err))
    print("清单：%s" % manifest)
    print("回滚：python %s --rollback %s" % (HERE, manifest))
    return 0 if not failed else 1


def do_rollback(manifest_path):
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    print("按 %s 回滚 %d 项…" % (manifest_path, len(m["items"])))
    ok = bad = 0
    for it in m["items"]:
        src, dst = REPO / it["src"].replace("/", os.sep), Path(it["dest"])
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                bad += 1
                print("  [跳过，已存在] %s" % it["src"])
                continue
            shutil.move(str(dst), str(src))
            ok += 1
        except (OSError, shutil.Error) as e:
            bad += 1
            print("  [失败] %s —— %s" % (it["src"], e))
    print("回滚完成：恢复 %d，跳过/失败 %d。" % (ok, bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
