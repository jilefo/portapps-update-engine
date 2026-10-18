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
"""smoke_sample.py —— 对批量重编后的代表性包做真启动抽样冒烟。
复用 smoke_real.run()，扩展 TARGETS。"""
import sys

_argv = sys.argv[:]
sys.argv = [sys.argv[0]]  # 防 smoke_real import 时解析 argv[2]
sys.path.insert(0, _TOOLS_DIR_F)
import smoke_real as sr

sys.argv = _argv

sr.TARGETS.update({
    "ZoomPortable": ("zoom.exe",),
    "ZenBrowserPortable": ("zen.exe",),
    "FeishuPortable": ("feishu.exe",),
})

for pkg in sys.argv[1:]:
    print(f"\n===== {pkg} =====", flush=True)
    sr.run(pkg)
