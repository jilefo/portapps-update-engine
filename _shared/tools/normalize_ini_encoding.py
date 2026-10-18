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
r"""normalize_ini_encoding.py —— 把 UTF-16LE 的 AppInfo ini 归一化为 UTF-8

背景：全库 39 包中 36 包 appinfo.ini / 43 个 launcher ini 均为 UTF-8（无 BOM），
唯 2 包是 UTF-16LE：
  WPSOfficePortable   App\AppInfo\appinfo.ini          （dist + portableapps）
  MiaoshouPortable    App\AppInfo\Launcher\MiaoshouPortable.ini（dist+portableapps）
NSIS3 虽能读 UTF-16LE BOM，但混用编码不利于开源协作与工具链统一，
且 Python 侧 configparser 会直接解析失败（Miaoshou 即因此被审计误判为
「APPDATA 未重定向」）。

做法：先写 .bak-utf16-<stamp> 备份，再**纯转码**（不是重新序列化）——
逐字符保留原文（含全部注释，Miaoshou 那份有大段可行性分析注释），
仅改字节编码。写回后做等价校验：还原文本逐字符相同 + 解析后
section/key 数量一致。
"""
import configparser
import os
import shutil
from datetime import datetime

ROOT = REPO_ROOT
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")

TARGETS = [
    r"WPSOfficePortable\dist\WPSOfficePortable\App\AppInfo\appinfo.ini",
    r"WPSOfficePortable\portableapps\App\AppInfo\appinfo.ini",
    r"MiaoshouPortable\dist\MiaoshouPortable\App\AppInfo\Launcher"
    r"\MiaoshouPortable.ini",
    r"MiaoshouPortable\portableapps\App\AppInfo\Launcher"
    r"\MiaoshouPortable.ini",
]


def sniff(path):
    with open(path, "rb") as f:
        b = f.read(4)
    if b[:2] == b"\xff\xfe":
        return "utf-16"
    if b[:2] == b"\xfe\xff":
        return "utf-16-be"
    if b[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def parse(path, enc):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    with open(path, encoding=enc, errors="replace") as f:
        cp.read_file(f)
    return cp


def main():
    done = 0
    for rel in TARGETS:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            print("  跳过（不存在）:", rel)
            continue
        enc = sniff(p)
        if enc not in ("utf-16", "utf-16-be"):
            print("  已是 %s，跳过: %s" % (enc, rel))
            continue
        # 字节级转码：不做任何换行处理，避免文本模式 universal newline
        # 与显式 \r\n 叠加导致空行翻倍（实测踩过）
        with open(p, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-16" if enc == "utf-16" else "utf-16-be")
        # ★ 安全护栏（2026-10-18 血泪教训）：含非 ASCII 的 launcher ini
        # 绝不能转 UTF-8 —— NSIS 按 ANSI 解 UTF-8 会导致中文路径乱码，
        # 程序直接起不来。正是这一步把 MiaoshouPortable（妙手\妙手.exe）
        # 转崩过一次，必须拦在工具层。
        if any(ord(ch) > 127 for ch in text):
            print('  [REFUSE] 含非 ASCII（中文路径），禁止转码，'
                  '保持 %s: %s' % (enc, rel))
            continue
        before = parse(p, enc)
        nsec, nkey = len(before.sections()), sum(
            len(before.items(s)) for s in before.sections())
        bak = p + ".bak-utf16-" + STAMP
        shutil.copy2(p, bak)
        with open(p, "wb") as f:
            f.write(text.encode("utf-8"))
        same_text = open(p, "rb").read().decode("utf-8") == text
        after = parse(p, "utf-8")
        a_sec, a_key = len(after.sections()), sum(
            len(after.items(s)) for s in after.sections())
        ok = same_text and (nsec, nkey) == (a_sec, a_key)
        print("  [%s] %s  %s -> UTF-8  文本等价=%s  "
              "sections=%d keys=%d -> %d/%d  备份=%s"
              % ("OK" if ok else "MISMATCH", os.path.basename(p), enc,
                 same_text, nsec, nkey, a_sec, a_key, os.path.basename(bak)))
        done += 1
    print("归一化完成:", done, "个文件")


if __name__ == "__main__":
    main()
