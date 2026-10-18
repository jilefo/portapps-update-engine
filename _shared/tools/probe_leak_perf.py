# -*- coding: utf-8 -*-
r"""
probe_leak_perf.py —— 「数据保存不对」+「卡顿」实测探针（一次运行拿两类证据）

与 smoke 的关键区别（刻意不做的事）：
  * **不预清理** PortableApps.comLauncherRuntimeData-*.ini
    —— 真实用户路径，顺带验证刚上的自愈钩子
  * 记录宿主侧快照差分，而不是只看包内 Data

泄漏检测（快速、O(1) 采样，不遍历大目录）：
  对 %APPDATA% / %LOCALAPPDATA% / %ProgramData% / %USERPROFILE% / Documents
  / %TEMP% 下两层目录打快照 {kind, 目录 mtime, 条目数}。
  目录 mtime 在增删条目时会变，因此无需遍历内容即可发现写入。
  差异再按厂商关键词归属到具体便携包。

卡顿检测：
  t_child  = 双击到包内子进程出现（用户体感的"多久看到程序"）
  t_window = 到首个可见窗口
  ps_n     = 启动期间实际派生出的 powershell 进程数（每个 1~2s 冷启动开销）
  t_exit   = 关闭信号到进程全退（收尾卡顿）

用法：
  python probe_leak_perf.py --only TraeCNPortable,CursorPortable
  python probe_leak_perf.py --all            # 全 43 单元（耗时较长）
  python probe_leak_perf.py --set risky      # 内置高风险集
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_clean as sc  # noqa: E402

WM_CLOSE = 0x0010
user32 = ctypes.windll.user32

RISKY = [
    "TraeCNPortable", "CherryStudioPortable", "CursorPortable",
    "CodeArtsPortable", "CodeArtsAgentPortable", "CodeBuddyCNPortable",
    "KukuAIPortable", "MiaoshouPortable", "MiniMaxCodePortable",
    "WXWorkPortable", "QuarkCloudDrivePortable", "ZoomPortable",
    "QQPortable", "TIMPortable", "QQNTPortable", "WPSOfficePortable-Writer",
]

# 宿主上正在跑的其他程序会持续写，标注为噪声，判定时不算泄漏
NOISY = ("\\.workbuddy", "\\.codebuddy", "\\WorkBuddy\\automation-")


def watch_roots():
    roots = {}
    for k in ("APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "USERPROFILE"):
        v = os.environ.get(k)
        if v:
            roots[k] = Path(v)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion"
                            r"\Explorer\Shell Folders") as k:
            d = Path(winreg.QueryValueEx(k, "Personal")[0])
            if d.exists():
                roots["DOCUMENTS"] = d
    except Exception:
        pass
    la = os.environ.get("LOCALAPPDATA")
    if la:
        t = Path(la) / "Temp"
        if t.exists():
            roots["TEMP"] = t
    return roots


def snap(roots, depth=2):
    out = {}
    for label, root in roots.items():
        try:
            l1 = sorted(root.iterdir())
        except Exception:
            continue
        for a in l1:
            try:
                if not a.is_dir():
                    continue
            except Exception:
                continue
            rec_dir(out, label, a)
            if depth >= 2:
                try:
                    l2 = sorted(a.iterdir())
                except Exception:
                    continue
                for b in l2:
                    try:
                        if b.is_dir():
                            rec_dir(out, label, b)
                    except Exception:
                        continue
    return out


def rec_dir(out, label, p):
    try:
        junction = sc.is_junction(p)
        st = os.stat(p)
        n = len(list(p.iterdir()))
    except Exception:
        return
    out[str(p)] = {
        "root": label,
        "junction": bool(junction),
        "mtime": round(st.st_mtime, 2),
        "n": n,
    }


def diff(pre, post):
    add, chg, jbreak = [], [], []
    for p, v in post.items():
        if p not in pre:
            add.append((p, v))
            continue
        o = pre[p]
        if o["junction"] != v["junction"]:
            jbreak.append((p, o, v))
        elif v["mtime"] != o["mtime"] or v["n"] != o["n"]:
            chg.append((p, o, v))
    gone = [p for p in pre if p not in post]
    return add, chg, jbreak, gone


def noisy(p: str) -> bool:
    return any(k.lower() in p.lower() for k in NOISY)


def close_procs(pkg_dir, launcher_pid, wait=18):
    """先 WM_CLOSE 优雅关，超时再 kill。返回收尾耗时。"""
    import psutil
    t0 = time.time()
    try:
        kids = psutil.Process(launcher_pid).children(recursive=True)
    except Exception:
        kids = []
    pids = {k.pid for k in kids}
    # 找主窗口：通过 EnumWindows 逐个对 pid 发 WM_CLOSE
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    sent = set()

    def cb(hwnd, _):
        p = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value in pids and p.value not in sent:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            sent.add(p.value)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    deadline = t0 + wait
    while time.time() < deadline:
        time.sleep(0.5)
        left = sc.pkg_app_procs(pkg_dir, launcher_pid)
        if not left:
            break
    if sc.pkg_app_procs(pkg_dir, launcher_pid):
        for k in kids:
            try:
                k.kill()
            except Exception:
                pass
        try:
            psutil.Process(launcher_pid).kill()
        except Exception:
            pass
        time.sleep(2)
    return round(time.time() - t0, 1)


def run_one(pr, settle=18.0, child_wait=60.0):
    import psutil
    pkg_dir = os.path.dirname(pr["exe"])
    roots = watch_roots()
    t0 = time.time()
    pre = snap(roots)
    rec = {"name": pr["name"], "exe": pr["exe"]}

    try:
        proc = subprocess.Popen([pr["exe"]], cwd=pkg_dir, env=sc.app_env(),
                                stdin=subprocess.PIPE)
    except OSError as e:
        rec["error"] = f"launch-failed: {e}"
        return rec

    t_child = None
    ps_pids = set()      # powershell / pwsh（单次 1.37s）
    cmd_pids = set()     # cmd.exe（单次 0.082s）
    deadline = t0 + child_wait
    while time.time() < deadline:
        time.sleep(0.3)
        try:
            kids = psutil.Process(proc.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            kids = []
        for k in kids:
            try:
                nm = (k.name() or "").lower()
            except Exception:
                continue
            if nm in ("powershell.exe", "pwsh.exe"):
                ps_pids.add(k.pid)
            elif nm == "cmd.exe":
                cmd_pids.add(k.pid)
        inpkg = sc.pkg_app_procs(pkg_dir, proc.pid)
        if inpkg and t_child is None:
            t_child = round(time.time() - t0, 1)
            break
    # 再跑一段，让程序真正落盘
    time.sleep(settle)

    rec["t_child"] = t_child
    rec["ps_spawned"] = len(ps_pids)
    rec["cmd_spawned"] = len(cmd_pids)
    rec["children"] = len(sc.pkg_app_procs(pkg_dir, proc.pid))
    rec["t_exit"] = close_procs(pkg_dir, proc.pid)
    time.sleep(3)

    post = snap(roots)
    add, chg, jbreak, gone = diff(pre, post)
    add = [x for x in add if not noisy(x[0])]
    chg = [x for x in chg if not noisy(x[0])]
    rec["host_new_dirs"] = [a[0] for a in add]
    rec["host_changed_dirs"] = [c[0] for c in chg][:20]
    rec["junction_broken"] = [j[0] for j in jbreak]
    # 残留 junction：宿主侧 junction 的**目标**指向本包 Data 的才算
    mark = pkg_dir.replace("/", "\\").lower()
    left = []
    for p, v in post.items():
        if not v["junction"] or v["root"] == "TEMP":
            continue
        try:
            tgt = (os.readlink(p) or "").lower()
        except OSError:
            tgt = ""
        if mark in tgt or mark in p.lower():
            left.append(p)
    rec["host_junctions_left"] = len(left)
    rec["host_junctions_left_paths"] = left[:10]

    # 泄漏判定：宿主 %TEMP% 抖动不算（任何程序都会用），只看"用户数据区"
    real_add = [a for a in add if a[1]["root"] != "TEMP"]
    real_chg = [c for c in chg if c[1]["root"] != "TEMP"]
    rec["leak_add"] = [a[0] for a in real_add]
    rec["leak_chg"] = [c[0] for c in real_chg]
    rec["temp_add"] = len([a for a in add if a[1]["root"] == "TEMP"])
    rec["leak"] = bool(real_add or real_chg)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="risky", choices=["risky", "all"])
    ap.add_argument("--only", default="")
    ap.add_argument("--settle", type=float, default=18.0)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    projs = sc.load_projects()
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        projs = [p for p in projs if p["name"] in want]
    elif args.set == "risky":
        projs = [p for p in projs if p["name"] in RISKY]

    print(f"探针目标 {len(projs)} 个单元（不预清理运行时数据，走真实用户路径）\n")
    results = []
    for pr in projs:
        print(f"--- {pr['name']} ...", flush=True)
        r = run_one(pr, settle=args.settle)
        results.append(r)
        print(f"    t_child={r.get('t_child')}s  ps={r.get('ps_spawned')} cmd={r.get('cmd_spawned')}  "
              f"children={r.get('children')}  t_exit={r.get('t_exit')}s  "
              f"host新增={len(r.get('host_new_dirs', []))} "
              f"host变更={len(r.get('host_changed_dirs', []))} "
              f"残留junction={r.get('host_junctions_left')}", flush=True)

    print("\n================ 汇总 ================")
    print(f"{'单元':<28}{'首子进程s':>9}{'PS数':>5}{'cmd数':>6}{'收尾s':>7}{'宿主新增':>9}{'宿主变更':>9}")
    for r in results:
        print(f"{r['name']:<28}{str(r.get('t_child')):>9}{r.get('ps_spawned',0):>5}{r.get('cmd_spawned',0):>6}"
              f"{str(r.get('t_exit')):>7}{len(r.get('host_new_dirs',[])):>9}"
              f"{len(r.get('host_changed_dirs',[])):>9}")

    leaky = [r for r in results if r.get("leak")]
    print(f"\n有宿主写入迹象的单元：{len(leaky)}/{len(results)}")
    for r in leaky:
        for p in r.get("host_new_dirs", [])[:8]:
            print(f"  [NEW] {r['name']} -> {p}")
        for p in r.get("host_changed_dirs", [])[:8]:
            print(f"  [CHG] {r['name']} -> {p}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"JSON -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
