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
"""scan_broken_quotes.py —— 扫描 Custom.nsh 中 nsExec 单引号串未闭合的残缺行。"""
import glob
import os
import sys
from pathlib import Path

# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
REPO_ROOT_F = REPO_ROOT.replace("\\", "/")
_TOOLS_DIR_F = str(_Path(__file__).resolve().parent).replace("\\", "/")
# <<< 路径自适应

# 产品树 Custom.nsh 统一由 _paths 枚举（迁移后产品根、迁移前仓库 dist）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

pairs = _paths.custom_nsh_files()
bad = []
for pkg, f in pairs:
    for i, ln in enumerate(open(f, encoding="utf-8",
                                errors="replace").read().splitlines(), 1):
        s = ln.strip()
        if "nsExec::ExecToStack" in s and s.startswith("nsExec::ExecToStack '"):
            if not s.endswith("'"):
                bad.append((pkg, i, s[-60:]))
print("扫描范围: %d 个产品树 Custom.nsh（包数 %d）"
      % (len(pairs), len(pairs)))
print("unterminated nsExec lines:", len(bad))
for pkg, i, tail in bad:
    print(f"  [{pkg}] L{i} ...{tail}")
