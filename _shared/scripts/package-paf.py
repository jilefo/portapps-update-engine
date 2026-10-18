# -*- coding: utf-8 -*-
"""package-paf.py —— 生成便携包压缩 zip 与 SHA256SUMS（--checksum-only 仅校验和）"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402
import _paths                          # noqa: E402

import hashlib
import shutil
import sys
from pathlib import Path



# 打包产物暂存根：迁移前 <Repo>/<Pkg>/dist，迁移后 <产品根>（与产品同级）。
# zip / SHA256SUMS 都不进 git，放这里两边都不污染仓库。
DIST = _paths.artifact_root(PKG)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    pkg_dir = _paths.product_dir(PKG)
    if not pkg_dir.is_dir():
        print(f"[FAIL] 先运行 build-portable.py 生成 {pkg_dir}")
        return 1
    archive = DIST / f"{PKG}"
    if "--checksum-only" not in sys.argv:
        out = shutil.make_archive(str(archive), "zip", root_dir=DIST, base_dir=PKG)
        print(f"[OK] {out}")
    # 只校验本包的 zip：迁移后 DIST 是共享产品根（D:\Portapps），
    # glob("*.zip") 会把 39 个包的 zip 全算进本包 SHA256SUMS。
    # 校验和文件同样按包命名，避免跨包互相覆盖。
    mine = DIST / f"{PKG}.zip"
    sums = []
    if mine.is_file():
        sums.append(f"{sha256_file(mine)}  {mine.name}")
        out_sums = DIST / f"{PKG}-SHA256SUMS.txt"
        out_sums.write_text("\n".join(sums) + "\n", encoding="utf-8")
        print("[OK] " + str(out_sums))
    else:
        print(f"[WARN] 未找到本包 zip：{mine}（先构建或用 --checksum-only 前确认）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
