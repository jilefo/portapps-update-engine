# -*- coding: utf-8 -*-
r"""runner.py —— 批量驱动「一包一更新脚本」

每个便携包目录里各有一个自包含的 `dist/<Pkg>/update.py`。
本执行器只是「并发地把它们挨个叫起来跑 --check --json，再汇总」，
自己不实现任何更新逻辑 —— 保证单脚本和批量跑的行为完全一致。

用法：
  python _shared/update/runner.py --check --all     检测全部（只读，最常用）
  python _shared/update/runner.py --check --auto    只检测有在线源的
  python _shared/update/runner.py --check --only CursorPortable,FeishuPortable
  python _shared/update/runner.py --check --json    机器可读
  python _shared/update/runner.py --check --report  生成 Markdown 报告
  python _shared/update/runner.py --update --all --execute   全部真更新（慎用）

退出码：0=无异常；1=存在源异常（ERR）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = REPO_ROOT / "docs" / "reports"


def find_scripts():
    out = []
    for pkgdir in sorted(REPO_ROOT.iterdir()):
        if not pkgdir.is_dir():
            continue
        dist = pkgdir / "dist"
        if not dist.is_dir():
            continue
        for d in sorted(dist.iterdir()):
            f = d / "update.py"
            if d.is_dir() and f.is_file():
                out.append((d.name, f))
    return out


def run_one(name, script, extra, timeout=90):
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--json"] + extra,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, cwd=str(script.parent))
        out = (r.stdout or "").strip()
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                d = json.loads(line)
                d["script"] = str(script.relative_to(REPO_ROOT))
                return d
        return dict(pkg=name, source="?", current=None, latest=None,
                    has_update=None, status="ERR",
                    msg="无 JSON 输出：%s" % (out or (r.stderr or ""))[-120:],
                    url=None)
    except subprocess.TimeoutExpired:
        return dict(pkg=name, source="?", current=None, latest=None,
                    has_update=None, status="ERR", msg="超时", url=None)
    except Exception as e:                              # noqa: BLE001
        return dict(pkg=name, source="?", current=None, latest=None,
                    has_update=None, status="ERR", msg=str(e)[:120], url=None)


def build_parser():
    import argparse
    ap = argparse.ArgumentParser(description="便携包更新策略批量执行器")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--all", action="store_true", help="全部包（默认）")
    ap.add_argument("--auto", action="store_true", help="先跑一遍筛选出在线源")
    ap.add_argument("--only", default="", help="逗号分隔的包名")
    ap.add_argument("--execute", action="store_true", help="真正落地")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    return ap


def collect(a):
    items = find_scripts()
    if a.only:
        want = {x.strip() for x in a.only.split(",") if x.strip()}
        items = [x for x in items if x[0] in want]
    return items


def render(rows, elapsed):
    print()
    print("%-24s %-15s %-14s %-14s %-8s %s"
          % ("PKG", "SOURCE", "CURRENT", "LATEST", "STATUS", "NOTE"))
    print("-" * 104)
    for r in rows:
        print("%-24s %-15s %-14s %-14s %-8s %s"
              % (r["pkg"], r["source"], str(r["current"] or "-")[:14],
                 str(r["latest"] or "-")[:14], r["status"],
                 (r.get("msg") or "")[:38]))
    up = [r for r in rows if r["status"] == "UPDATE"]
    er = [r for r in rows if r["status"] == "ERR"]
    mn = [r for r in rows if r["status"] == "MANUAL"]
    lt = [r for r in rows if r["status"] == "LATEST"]
    ca = [r for r in rows if r["status"] == "CACHED"]
    print("-" * 104)
    print("合计 %d：有更新 %d / 最新 %d / 人工 %d / 取新失败用缓存 %d / 异常 %d"
          "  (耗时 %.1fs)"
          % (len(rows), len(up), len(lt), len(mn), len(ca), len(er), elapsed))
    if ca:
        print()
        print("本次取新失败、已退回上次成功结果（多为限流/网络抖动，非策略问题）：")
        for r in ca:
            print("  %-24s %s" % (r["pkg"], (r.get("msg") or "")[:70]))
    if up:
        print()
        print("有可用更新，到对应包的便携目录执行即可：")
        for r in up:
            p = r["pkg"]
            print("  cd %s/dist/%s && python update.py --update --execute"
                  % (p, p))
    else:
        print()
        print("全部已是最新（人工源需自行到官网确认）。")
    return dict(update=up, latest=lt, manual=mn, err=er, rows=rows)


def report(rows, elapsed):
    up = [r for r in rows if r["status"] == "UPDATE"]
    lt = [r for r in rows if r["status"] == "LATEST"]
    mn = [r for r in rows if r["status"] == "MANUAL"]
    er = [r for r in rows if r["status"] == "ERR"]
    ca = [r for r in rows if r["status"] == "CACHED"]
    stamp = datetime.now().strftime("%Y%m%d")
    out = REPORT_DIR / ("更新检测报告-%s.md" % stamp)
    out.parent.mkdir(parents=True, exist_ok=True)
    L = ["# 便携包更新检测报告",
         "",
         "生成时间：%s   耗时：%.1fs   脚本数：%d"
         % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), elapsed, len(rows)),
         "",
         "由 `_shared/update/runner.py` 批量调用各包 `dist/<Pkg>/update.py` 产出。",
         "",
         "| 指标 | 数量 |", "|---|---|",
         "| 包总数 | %d |" % len(rows),
         "| 有可用更新 | %d |" % len(up),
         "| 已是最新 | %d |" % len(lt),
         "| 需人工确认 | %d |" % len(mn),
         "| 取新失败（用上次缓存） | %d |" % len(ca),
         "| 源异常 | %d |" % len(er), ""]
    for title, arr in (("有可用更新", up), ("已是最新", lt),
                       ("需人工下载（--ingest 接管）", mn),
                       ("取新失败（限流/网络抖动，已退回上次结果）", ca),
                       ("源异常（需修策略）", er)):
        if not arr:
            continue
        L += ["## %s（%d）" % (title, len(arr)), "",
              "| 包 | 源类型 | 当前 | 最新 | 说明 |", "|---|---|---|---|---|"]
        for r in arr:
            L.append("| %s | %s | %s | %s | %s |"
                     % (r["pkg"], r["source"], r["current"] or "-",
                        r["latest"] or "-",
                        (r.get("msg") or "").replace("|", "/")[:70]))
        L.append("")
    out.write_text("\n".join(L), encoding="utf-8")
    print("\n报告已写入 %s" % out.relative_to(REPO_ROOT))
    return out


def main():
    a = build_parser().parse_args()
    items = collect(a)
    if not items:
        print("没有匹配的更新脚本")
        return 2
    extra = []
    if a.update:
        extra.append("--update")
    if a.execute:
        extra.append("--execute")
    elif not a.update:
        extra.append("--check")

    # 检测只是几个 HTTP 请求，90s 足够；更新要下几十上百 MB，放宽到 15 分钟。
    # 之前统一 180s，结果一个卡住的请求能把整批拖到 3 分钟。
    timeout = 900 if a.update else 90
    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_one, n, s, extra, timeout): n for n, s in items}
        for f in as_completed(futs):
            rows.append(f.result())
    rows.sort(key=lambda r: r["pkg"])
    el = time.time() - t0

    # 没有策略脚本的包提示
    have = {n for n, _ in items}
    allpkg = {p.name for p in REPO_ROOT.iterdir()
              if p.is_dir() and (p / "dist").is_dir()}
    gap = sorted(allpkg - have)
    if gap and a.all:
        print("[警告] 这些包还没有更新脚本：%s" % ", ".join(gap))

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 1 if any(r["status"] == "ERR" for r in rows) else 0

    summary = render(rows, el)
    if a.report:
        report(rows, el)
    return 1 if summary["err"] else 0


if __name__ == "__main__":
    sys.exit(main())
