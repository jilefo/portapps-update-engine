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
r"""test_ini_encoding_matrix.py —— launcher ini 编码 × 中文路径 启动矩阵

背景：MiaoshouPortable 的 launcher ini 含中文路径
      ProgramExecutable=妙手\妙手.exe
把它从 UTF-16LE 转成 UTF-8（无 BOM）后启动失败（3 轮排查 R2/R3 FAIL），
还原 UTF-16LE 后恢复 PASS。本脚本补测 UTF-8 **带 BOM** 是否安全，
给出确定性结论。

安全性：无论测试结果如何，结束前一定还原为 UTF-16LE（已知可用）。
"""
import glob
import os
import shutil
import sys

sys.path.insert(0, _TOOLS_DIR_F)
import smoke_clean as sc

LAUN = [
    (REPO_ROOT + r"\MiaoshouPortable\dist\MiaoshouPortable"
     r"\App\AppInfo\Launcher\MiaoshouPortable.ini"),
    (REPO_ROOT + r"\MiaoshouPortable\portableapps\App\AppInfo"
     r"\Launcher\MiaoshouPortable.ini"),
]
BAK = []


ORIG = {}


def save_backups():
    for p in LAUN:
        b = p + ".bak-encm"
        shutil.copy2(p, b)
        BAK.append((p, b))
        # 原文一次性读入内存，后续转码都以它为准，
        # 避免「还原后又被当 UTF-16 读一次」这类二次损坏
        ORIG[p] = open(b, encoding="utf-16").read()


def restore():
    for p, b in BAK:
        if os.path.isfile(b):
            shutil.copy2(b, p)
    print("已还原为原始 UTF-16LE（备份保留为 *.bak-encm）")


def set_encoding(enc):
    """enc: 'utf-16' | 'utf-8-sig' | 'utf-8'"""
    for p in LAUN:
        data = ORIG[p].encode(enc)
        with open(p, "wb") as f:
            if enc == "utf-16":
                f.write(b"\xff\xfe")
            f.write(data)


def main() -> int:
    # 前置检查：本脚本要在 dist 构建产物上做真实启动实测，dist 未构建（或只
    # 拉了源码没跑打包）时两个 ini 都/其一不存在。这属于「本机不具备测试前提」，
    # 不是代码缺陷 —— 早先直接 shutil.copy2 会抛 FileNotFoundError、被 CI 判 FAIL，
    # 现在统一输出 SKIP 并退 0，让未打包的机器也能跑通整套自检。
    missing = [p for p in LAUN if not os.path.isfile(p)]
    if missing:
        print("SKIP：launcher ini 不存在，跳过编码矩阵实测（环境不具备前提，不算失败）")
        for p in missing:
            print("       缺失: %s" % p)
        print("       说明：本脚本依赖包已构建的 dist；先跑打包再实测即可。")
        return 0

    proj = next((p for p in sc.load_projects()
                 if p["name"] == "MiaoshouPortable"), None)
    if proj is None:
        print("SKIP：项目清单里没有 MiaoshouPortable，跳过编码矩阵实测")
        return 0

    save_backups()
    try:
        for enc, label in (("utf-8-sig", "UTF-8 带 BOM"),
                           ("utf-8", "UTF-8 无 BOM（对照，预期 FAIL）")):
            set_encoding(enc)
            head = open(LAUN[0], "rb").read(3)
            print("\n=== %s  (头部字节=%s) ===" % (label, head))
            try:
                r = sc.test_project(proj)
                print("  判定=%s 子进程=%s Data新写=%s"
                      % (r.get("verdict"), r.get("children_count"),
                         r.get("fresh_files")))
            except Exception as e:  # noqa: BLE001
                print("  异常:", e)
    finally:
        restore()
    print("\n结论：UTF-16LE=可用（已实证 PASS）；其余见上面判定")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
