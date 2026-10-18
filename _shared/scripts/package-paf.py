# -*- coding: utf-8 -*-
"""package-paf.py —— 生成 dist 压缩包与 SHA256SUMS（--checksum-only 仅校验和）"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402

import hashlib
import shutil
import sys
from pathlib import Path



DIST = REPO / "dist"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    pkg_dir = DIST / PKG
    if not pkg_dir.is_dir():
        print(f"[FAIL] 先运行 build-portable.py 生成 {pkg_dir}")
        return 1
    archive = DIST / f"{PKG}"
    if "--checksum-only" not in sys.argv:
        out = shutil.make_archive(str(DIST / PKG), "zip", root_dir=DIST, base_dir=PKG)
        print(f"[OK] {out}")
    sums = []
    for f in sorted(DIST.glob("*.zip")):
        sums.append(f"{sha256_file(f)}  {f.name}")
    if sums:
        (DIST / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
        print("[OK] dist/SHA256SUMS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
