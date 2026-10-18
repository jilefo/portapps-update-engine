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
"""smoke_3rounds.py —— 全库便携软件 3 轮排查（干净环境版）

背景：用户报告 QQPortable / TIMPortable / WPSOfficePortable / WeixinPortable
打不开，要求对所有便携软件做 3 轮排查。本脚本复用 smoke_clean 的
test_project 探针（预清RT→快照→剥污染环境变量启动→轮询子进程/窗口→
写入对照→有序收场→清残留→判定 PASS/WARN/FAIL），连续跑 3 轮。

单元：smoke_clean.load_projects() 的 42 个（37 标准 + KukuAI + WPS 4 分体）
      + WPSOfficePortable 主入口（此前缺失 launcher ini，已补）= 43 个。

QQ 系（QQPortable/TIMPortable/QQNTPortable）共享宿主目录（Tencent 等），
轮内依次测试会互相看到对方的 junction 残留；探针已有「owner 进程死→
自动接管」语义，但为使每题都是独立冷启动，QQ 系单元测试前执行
qq_cold_clean()：杀 QQ 系进程 + 拆全部 PortableApps junction（含重定向
后的真实 Documents）。

输出：
  reports/便携项目三轮冒烟明细-<stamp>.json   逐轮逐单元完整记录
  reports/便携项目三轮排查报告-<stamp>.md     3 轮矩阵 + 汇总
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, _TOOLS_DIR_F)
import smoke_clean as sc

ROUNDS = 3
QQ_FAMILY = {"QQPortable", "TIMPortable", "QQNTPortable"}
REPORT_DIR = os.path.join(REPO_ROOT, "docs", "reports")
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

QQ_PROCS = ("qq.exe", "qqex.exe", "tim.exe", "QQPortable.exe",
            "TIMPortable.exe", "QQNTPortable.exe", "QQExternal.exe",
            "QQScreenTool.exe", "txplatform.exe")


def real_documents():
    """真实 Documents（本机重定向到 D 盘，注册表取值）"""
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
        v, _ = winreg.QueryValueEx(k, "Personal")
        winreg.CloseKey(k)
        return v
    except OSError:
        return os.path.expandvars(r"%USERPROFILE%\Documents")


STRIP_ROOTS = [
    os.path.expandvars(r"%APPDATA%\Tencent"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tencent"),
    os.path.expandvars(r"%PROGRAMDATA%\Tencent"),
    os.path.expandvars(r"%APPDATA%"),
    os.path.expandvars(r"%LOCALAPPDATA%"),
    os.path.expandvars(r"%PROGRAMDATA%"),
]


def strip_pkg_junctions():
    """拆掉全部指向 PortableApps 的 junction（含真实 Documents）"""
    import ctypes
    g = ctypes.windll.kernel32.GetFileAttributesW
    RP = 0x400
    n = 0
    for root in STRIP_ROOTS + [real_documents()]:
        if not root or not os.path.isdir(root):
            continue
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for e in names:
            p = os.path.join(root, e)
            a = g(p)
            if a in (-1, 0xFFFFFFFF) or not (a & RP):
                continue
            try:
                if "PortableApps" in os.readlink(p):
                    os.rmdir(p)
                    n += 1
            except OSError:
                pass
    return n


def qq_cold_clean():
    """QQ 系单元测试前：杀进程 + 拆 junction + 清 RT，保证独立冷启动"""
    for n in QQ_PROCS:
        subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True)
    time.sleep(0.5)
    n = strip_pkg_junctions()
    if n:
        print(f"    [qq-cold] 拆残留 junction {n} 条", flush=True)


def build_units():
    projs = sc.load_projects()
    wps_main = dict(
        name="WPSOfficePortable-Main",
        exe=os.path.join(sc.ROOT, "WPSOfficePortable", "dist",
                         "WPSOfficePortable", "WPSOfficePortable.exe"),
        cmd="wpsoffice.exe")
    if os.path.isfile(wps_main["exe"]):
        projs.append(wps_main)
    else:
        print("!! WPSOfficePortable 主 exe 缺失", flush=True)
    return projs


def run_round(rnd, projs, all_results):
    print(f"\n########## 第 {rnd} 轮开始 {datetime.now():%H:%M:%S} "
          f"（{len(projs)} 单元）##########", flush=True)
    rnd_results = []
    for i, pr in enumerate(projs, 1):
        if pr["name"] in QQ_FAMILY:
            qq_cold_clean()
        print(f"[R{rnd} {i}/{len(projs)}] {pr['name']} ...", end=" ",
              flush=True)
        try:
            r = sc.test_project(pr)
        except Exception as e:  # noqa: BLE001
            r = dict(name=pr["name"], exe=pr["exe"],
                     error=f"probe-exception: {e}", verdict="FAIL")
        r["round"] = rnd
        rnd_results.append(r)
        print(f"{r.get('verdict')} {r.get('elapsed', '?')}s "
              f"子进程={r.get('children_count', '?')} "
              f"首窗={r.get('first_window_s', '-')} "
              f"新增={r.get('fresh_files', '?')} "
              f"RT残留={r.get('rt_left', '?')}", flush=True)
        all_results.append(r)
        # 每单元落盘，防长跑中断丢数据
        with open(os.path.join(REPORT_DIR, f"三轮冒烟明细-{STAMP}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=1)
    return rnd_results


def md_report(rounds):
    """rounds: list[list[rec]]"""
    names = [r["name"] for r in rounds[0]]
    lines = [
        f"# 便携软件全库 3 轮排查报告",
        f"",
        f"- 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 单元数：{len(names)}；轮数：{len(rounds)}",
        f"- 方法：干净环境启动探针（剥离 Electron/Node 污染变量），"
        f"判定 = 应用进程/窗口 + Data 新写 双维度；"
        f"QQ 系单元测试前强制冷启动（杀进程+拆 junction）",
        f"",
        f"## 1. 3 轮判定矩阵",
        f"",
        f"| # | 单元 | R1 | R2 | R3 | 一致 |",
        f"|---|---|---|---|---|---|",
    ]
    verdict_map = {}
    for rnd in rounds:
        for r in rnd:
            verdict_map.setdefault(r["name"], []).append(r.get("verdict"))
    bad = []
    for i, nm in enumerate(names, 1):
        vs = verdict_map.get(nm, ["-"] * len(rounds))
        consistent = "✓" if len(set(vs)) == 1 else "✗"
        lines.append(f"| {i} | {nm} | {' | '.join(vs)} | {consistent} |")
        if any(v != "PASS" for v in vs):
            bad.append(nm)
    lines += ["", "## 2. 汇总", "",
              f"- 全 PASS 且 3 轮一致：{len(names) - len(bad)}/{len(names)}"]
    if bad:
        lines.append(f"- 存在非 PASS 的单元：{', '.join(bad)}")
    lines += ["", "## 3. 非 PASS 单元明细", ""]
    any_bad = False
    for rnd in rounds:
        for r in rnd:
            if r.get("verdict") == "PASS":
                continue
            any_bad = True
            lines.append(
                f"### R{r['round']} {r['name']} — {r.get('verdict')}")
            lines.append(f"- 子进程: {r.get('children') or '无'}")
            lines.append(f"- 首窗: {r.get('first_window_s', '-')}s "
                         f"标题: {r.get('window_titles') or '无'}")
            lines.append(f"- Data 新写: {r.get('fresh_files', '?')} 文件")
            if r.get("leaks"):
                lines.append(f"- 泄漏: {'; '.join(r['leaks'][:5])}")
            lines.append(f"- junction 残留: {r.get('junction_left', '?')}；"
                         f"RT 残留: {r.get('rt_left', '?')}")
            if r.get("error"):
                lines.append(f"- 错误: {r['error']}")
            lines.append("")
    if not any_bad:
        lines.append("（无——全部单元 3 轮均 PASS）")
    return "\n".join(lines)


def main():
    os.makedirs(REPORT_DIR, exist_ok=True)
    projs = build_units()
    print(f"3 轮排查开始 {datetime.now():%Y-%m-%d %H:%M:%S}，"
          f"共 {len(projs)} 单元 × {ROUNDS} 轮", flush=True)
    all_results = []
    rounds = []
    for rnd in range(1, ROUNDS + 1):
        rounds.append(run_round(rnd, projs, all_results))
        # 轮间冷却：杀干净 + 拆 junction
        for n in QQ_PROCS:
            subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True)
        n = strip_pkg_junctions()
        print(f"[轮间冷却] 拆 junction {n} 条，休息 10s", flush=True)
        time.sleep(10)
    mp = os.path.join(REPORT_DIR, f"便携项目三轮排查报告-{STAMP}.md")
    with open(mp, "w", encoding="utf-8") as f:
        f.write(md_report(rounds))
    jp = os.path.join(REPORT_DIR, f"三轮冒烟明细-{STAMP}.json")
    with open(jp, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=1)
    print(f"\nDONE -> {jp}", flush=True)
    print(f"DONE -> {mp}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
