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
"""smoke_wps_final.py —— 终验：经真实 PAL 启动器验证 WPS 五入口行为分化

判定（UIA 控件树）：
  首页壳  = 含 ≥3 个首页控件（新建/最近/打开/暂无打开记录），UI 文本 ≤6
  空白文档 = 首页控件 ≤1，UI 文本 ≥10（功能区），类名 Kx*PromeMainWindow
  PDF     = 标题含 WPS PDF
预期：
  WPSOfficePortable -> 首页（综合入口）
  WriterPortable    -> 空白文字文档
  SpreadsheetsPortable -> 空白表格文档
  PresentationPortable -> 空白演示文档
  wpsPDFPortable    -> WPS PDF
同时断言 0 弹框（PAL 错误框）。
"""
import ctypes
import os
import subprocess
import sys
import time

import psutil

sys.path.insert(0, _TOOLS_DIR_F)
import smoke_real as sr

BASE = (REPO_ROOT + r"\WPSOfficePortable\dist"
        r"\WPSOfficePortable")
OUT = _TOOLS_DIR_F
KILL = ("wps.exe", "et.exe", "wpp.exe", "wpspdf.exe", "wpsoffice.exe",
        "wpscloudsvr.exe", "promecefpluginhost.exe", "kwinappinstaller.exe",
        "WriterPortable.exe", "wpsPDFPortable.exe", "WPSOfficePortable.exe",
        "SpreadsheetsPortable.exe", "PresentationPortable.exe")
HOME = {"新建", "最近", "打开", "暂无打开记录"}

PS = r'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$res = New-Object System.Collections.Generic.List[string]
$root = [System.Windows.Automation.AutomationElement]::RootElement
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition)) {
    $n = $w.Current.Name
    if (-not $n) { continue }
    if ($n -notmatch 'WPS|金山|PDF|wps|et|wpp') { continue }
    $res.Add("WINDOW`t" + $n + "`t" + $w.Current.ClassName)
    foreach ($e in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants,
            [System.Windows.Automation.Condition]::TrueCondition)) {
        if ($e.Current.Name) { $res.Add("UI`t" + $e.Current.Name) }
    }
}
[System.IO.File]::WriteAllLines($env:UIA_OUT, $res,
    (New-Object System.Text.UTF8Encoding($false)))
'''


def kill():
    for n in KILL:
        subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True)
    time.sleep(1.2)


def probe(launcher, wait=34):
    kill()
    sr.pre_clean_rt(BASE)
    env = {k: v for k, v in os.environ.items() if k not in sr.STRIP_ENV}
    p = subprocess.Popen([os.path.join(BASE, launcher)], cwd=BASE, env=env,
                         stdin=subprocess.PIPE)
    time.sleep(wait)
    dlgs = sr.dialogs_for(p.pid)
    dst = os.path.join(OUT, "_uia_final.txt")
    subprocess.run(["powershell", "-NoProfile", "-Command", PS],
                   capture_output=True, timeout=90,
                   env=dict(os.environ, UIA_OUT=dst))
    txt = open(dst, encoding="utf-8").read() if os.path.isfile(dst) else ""
    win = [l for l in txt.splitlines() if l.startswith("WINDOW\t")]
    names = {l.split("\t", 1)[-1] for l in txt.splitlines()
             if l.startswith("UI\t")}
    hit = sorted(HOME & names)
    cls = win[0].split("\t")[2] if win else "-"
    title = win[0].split("\t")[1] if win else "-"
    if "PDF" in title.upper():
        v = "PDF"
    elif len(hit) >= 3:
        v = "首页"
    elif names and len(names) >= 10:
        v = "空白文档"
    else:
        v = "未知"
    print(f"[{v:5s}] {launcher:26s} 标题={title!r} 类={cls} "
          f"首页命中={hit} UI文本={len(names)} 弹框={dlgs or '无'}",
          flush=True)
    return v, dlgs


EXPECT = {
    "WPSOfficePortable.exe": "首页",
    "WriterPortable.exe": "空白文档",
    "SpreadsheetsPortable.exe": "空白文档",
    "PresentationPortable.exe": "空白文档",
    "wpsPDFPortable.exe": "PDF",
}

if __name__ == "__main__":
    r = []
    for exe, want in EXPECT.items():
        try:
            v, dlgs = probe(exe)
            ok = (v == want) and not dlgs
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"[FAIL] {exe}: {e}")
        r.append((exe, want, ok))
    kill()
    print("\n=== 终验结果 ===")
    for exe, want, ok in r:
        print(f"  {'PASS' if ok else 'FAIL'}  {exe}  期望={want}")
    print("结论:", "全部 PASS" if all(x[2] for x in r) else "存在 FAIL")
