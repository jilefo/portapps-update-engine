# -*- coding: utf-8 -*-
r"""
scan_redirect_coverage.py —— 「数据保存不对」机理分级（只读）

判据（Windows 真实行为）：
  1. Electron / Chromium 取 appData 走 SHGetKnownFolderPath(FOLDERID_RoamingAppData)，
     **不读 %APPDATA% 环境变量** —— 只改环境变量对它无效，必须 junction 接管。
  2. VSCode 系（Trae/Cursor/CodeArts/CodeBuddy...）的 ~/.xxx 走 Node os.homedir()，
     优先读 USERPROFILE 环境变量 —— 改环境变量有效。
  3. TEMP/TMP 一般读环境变量 —— 有效。

本脚本把 39 个包按「接管手段」分级：
  A 级（安全）：junction 接管 + 环境变量重定向
  B 级（有洞）：只有环境变量重定向，Electron 类会绕过 → 宿主残留
  C 级（叠加风险）：还重定向了 USERPROFILE（Electron 可能崩）
"""
from __future__ import annotations

import re
from pathlib import Path

RE_JUNCTION = re.compile(r"(?i)junction|mklink|SymbolicLink|CreateHardLink")
RE_PSHELL = re.compile(r"(?i)powersh""ell|pwsh")


def read_text(p: Path) -> str:
    b = p.read_bytes()
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return b.decode("utf-16", errors="replace")
    return b.decode("utf-8-sig", errors="replace")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    rows = []
    for nsh in sorted(root.glob("*/dist/*/App/AppInfo/Launcher/Custom.nsh")):
        # <Pkg>/dist/<Pkg>/App/AppInfo/Launcher/Custom.nsh
        pkg = nsh.parents[5].name
        txt = read_text(nsh)
        j = len(RE_JUNCTION.findall(txt))
        ps = len(RE_PSHELL.findall(txt))
        ini = nsh.parent / f"{pkg}.ini"
        env = {}
        if ini.exists():
            cur = None
            for line in read_text(ini).splitlines():
                s = line.strip()
                if not s or s.startswith(";") or s.startswith("#"):
                    continue
                m = re.match(r"^\[(.+?)\]$", s)
                if m:
                    cur = m.group(1)
                    continue
                if cur == "Environment" and "=" in s:
                    k, v = s.split("=", 1)
                    env[k.strip().upper()] = v.strip()
        rows.append({
            "pkg": pkg, "junction": j, "ps": ps,
            "up": "USERPROFILE" in env,
            "appdata": "APPDATA" in env,
            "temp": "TEMP" in env,
            "env": env,
        })

    print(f"{'包':<26}{'junction':>9}{'PS':>4}{'UP':>6}{'APPDATA':>8}{'TEMP':>6}   等级")
    print("-" * 78)
    for r in sorted(rows, key=lambda x: (x["junction"], x["pkg"])):
        if r["junction"] == 0 and r["up"]:
            lv = "C 无junction+重定向UP"
        elif r["junction"] == 0:
            lv = "B 无junction（Electron可绕过）"
        elif r["up"]:
            lv = "A- junction+重定向UP"
        else:
            lv = "A junction"
        print(f"{r['pkg']:<26}{r['junction']:>9}{r['ps']:>4}"
              f"{str(r['up']):>6}{str(r['appdata']):>8}{str(r['temp']):>6}   {lv}")

    nB = sum(1 for r in rows if r["junction"] == 0)
    print(f"\n合计 {len(rows)} 包：无 junction 的 {nB} 包（其中重定向 USERPROFILE 的 "
          f"{sum(1 for r in rows if r['junction']==0 and r['up'])} 包）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
