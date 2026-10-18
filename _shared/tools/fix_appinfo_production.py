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
r"""fix_appinfo_production.py —— appinfo.ini 生产级缺陷修复

修复两类缺陷（均为静态审计发现）：

1. ExtractIcon 路径指向不存在的 exe（3 个包）
   后果：构建启动器时取不到图标 -> 启动器 exe 落到默认图标（用户视角
   「图标不对」的一类真因）。
   修复：按产品树里真实存在的 exe 改写。
     CodeArtsPortable        App\CodeArtsPortable\CodeArtsPortable.exe
                          -> App\CodeArts\CodeArts.exe
     FoxitPDFPortable        App\FoxitPDFPortable\FoxitPDFPortable.exe
                          -> App\Foxit PDF Editor\FoxitPDFEditor.exe
     QuarkCloudDrivePortable App\QuarkCloudDrivePortable\...
                          -> App\QuarkCloudDrive\quark_cloud_drive.exe

2. 产品树（可运行树）appinfo.ini 缺 [Format] / [Control]（21+1 个包）
   后果：PortableApps 平台读不到 Start/ExtractIcon/Icons，dist 作为交付
   物在平台菜单里信息不全。
   修复：**文本级合并**——保留 dist 原有段与注释，只从 portableapps 源树
   补入缺失的 [Format] / [Control] 段（不整体覆盖，避免丢 dist 专有信息）。

所有改动先写 .bak-appfix-<stamp> 备份。
"""
import configparser
import os
import shutil
import sys
from datetime import datetime

# 产品根唯一解析处（dist 迁移到 D:\Portapps 后由它接管产品路径）。
sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

ROOT = REPO_ROOT
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

# 手工核定的正确路径（已用 os.path.isfile 在产品树验证）
ICON_FIX = {
    "CodeArtsPortable": r"App\CodeArts\CodeArts.exe",
    "FoxitPDFPortable": r"App\Foxit PDF Editor\FoxitPDFEditor.exe",
    "QuarkCloudDrivePortable": r"App\QuarkCloudDrive\quark_cloud_drive.exe",
}
NEED_SECTIONS = ("Format", "Control")


def pkgs():
    out = []
    for e in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, e)
        if os.path.isdir(p) and e.endswith("Portable"):
            out.append((e, p))
    return out


def paths(name, base):
    # "dist" 即产品树：迁移前 <Repo>/<Pkg>/dist/<Pkg>，迁移后 <产品根>/<Pkg>
    return {
        "portableapps": os.path.join(base, "portableapps", "App", "AppInfo",
                                     "appinfo.ini"),
        "dist": os.path.join(str(_paths.product_dir(name)), "App", "AppInfo",
                             "appinfo.ini"),
    }


def split_sections(text):
    """把 ini 文本切成 [(段名, 块文本)]，段名前的前导注释归入该段"""
    blocks, cur_name, cur = [], None, []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if cur_name is not None or cur:
                blocks.append((cur_name, "\n".join(cur)))
            cur_name = s[1:-1]
            cur = [line]
        else:
            cur.append(line)
    if cur_name is not None or cur:
        blocks.append((cur_name, "\n".join(cur)))
    return blocks


def backup(p):
    b = p + ".bak-appfix-" + STAMP
    shutil.copy2(p, b)
    return b


def fix_icons():
    n = 0
    for name, base in pkgs():
        if name not in ICON_FIX:
            continue
        want = ICON_FIX[name]
        # 先确认目标真实存在（产品树里）
        tgt = os.path.join(str(_paths.product_dir(name)), *want.split("\\"))
        if not os.path.isfile(tgt):
            print("  !! 目标仍不存在，跳过:", name, tgt)
            continue
        for tree, p in paths(name, base).items():
            if not os.path.isfile(p):
                continue
            text = open(p, encoding="utf-8-sig", errors="replace").read()
            blocks = split_sections(text)
            changed = False
            for i, (sn, body) in enumerate(blocks):
                if sn != "Control":
                    continue
                new = []
                for line in body.splitlines():
                    k = line.split("=")[0].strip().lower()
                    if k == "extracticon":
                        old = line.split("=", 1)[1].strip()
                        if old != want:
                            new.append("ExtractIcon=%s" % want)
                            changed = True
                            print("  [%s] %s ExtractIcon: %s -> %s"
                                  % (tree, name, old, want))
                        else:
                            new.append(line)
                    else:
                        new.append(line)
                blocks[i] = (sn, "\n".join(new))
            if changed:
                backup(p)
                out = "\n".join(b for _, b in blocks)
                open(p, "w", encoding="utf-8", newline="\r\n").write(out)
                n += 1
    print("ExtractIcon 修复文件数:", n)


def fix_sections():
    n = 0
    for name, base in pkgs():
        ps = paths(name, base)
        src, dst = ps["portableapps"], ps["dist"]
        if not (os.path.isfile(src) and os.path.isfile(dst)):
            continue
        dtext = open(dst, encoding="utf-8-sig", errors="replace").read()
        stext = open(src, encoding="utf-8-sig", errors="replace").read()
        dnames = {s[1:-1] for s in
                  (l.strip() for l in dtext.splitlines())
                  if s.startswith("[") and s.endswith("]")}
        missing = [s for s in NEED_SECTIONS if s not in dnames]
        if not missing:
            continue
        sblocks = dict((k, v) for k, v in split_sections(stext) if k)
        add = [sblocks[s] for s in missing if s in sblocks]
        if not add:
            continue
        backup(dst)
        merged = dtext.rstrip("\r\n") + "\r\n\r\n" + "\r\n\r\n".join(add) \
            + "\r\n"
        open(dst, "w", encoding="utf-8", newline="").write(merged)
        # 校验
        cp = configparser.ConfigParser(strict=False, interpolation=None)
        cp.read(dst, encoding="utf-8-sig")
        ok = all(cp.has_section(s) for s in NEED_SECTIONS)
        print("  [%s] %s 补段 %s  校验=%s"
              % ("OK" if ok else "FAIL", name, ",".join(missing), ok))
        n += 1
    print("补段包数:", n)


if __name__ == "__main__":
    print("=== 1. ExtractIcon 路径修复 ===")
    fix_icons()
    print("\n=== 2. 产品树 appinfo 补 [Format]/[Control] ===")
    fix_sections()
