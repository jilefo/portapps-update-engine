# -*- coding: utf-8 -*-
r"""gen-sbom.py —— 生成 SPDX SBOM（通用版，包名自动推导）

只依赖标准库，输出 <打包暂存根>/<Pkg>-sbom.spdx.json（迁移前 <Pkg>/dist/、
迁移后共享产品根 D:\Portapps\——按包命名避免 39 个包互相覆盖）。
SBOM 记录本仓库便携化配置与原程序文件清单（不做依赖解析）。

注：sbom 是**构建产物**、不是产品文件，故不写进产品目录内部——
否则会撞 test_structure.py 的「产物根目录多出文件」白名单。
文件按 <Pkg>-sbom.spdx.json 命名，共享产品根下 39 个包互不覆盖。
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402
import _paths                          # noqa: E402

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path



DIST = _paths.artifact_root(PKG)
NAMESPACE = "https://greensoftmake.local/spdx/" + PKG


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    pkg_dir = _paths.product_dir(PKG)
    if not pkg_dir.is_dir():
        print("[FAIL] 先运行 build-portable.py 生成 " + str(pkg_dir))
        return 1

    files = []
    for path in sorted(pkg_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = "./" + str(path.relative_to(pkg_dir)).replace(os.sep, "/")
            files.append({
                "fileName": rel,
                "sha256": sha256(path),
                "size": path.stat().st_size,
            })
        except OSError:
            continue

    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": PKG + "-sbom",
        "documentNamespace": NAMESPACE,
        "creationInfo": {
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "creators": ["Tool: gen-sbom.py"],
        },
        "packages": [{
            "SPDXID": "SPDXRef-Package-portableconfig",
            "name": PKG,
            "versionInfo": "see-portableapps/App/AppInfo/appinfo.ini",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "MIT",
            "licenseDeclared": "MIT",
            "copyrightText": "NOASSERTION",
        }],
        "files": [
            {"SPDXID": "SPDXRef-File-" + str(i), "fileName": f["fileName"],
             "sha256": f["sha256"], "licenseConcluded": "NOASSERTION",
             "copyrightText": "NOASSERTION"}
            for i, f in enumerate(files)
        ],
        "relationships": [{
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relatedSpdxElement": "SPDXRef-Package-portableconfig",
            "relationshipType": "DESCRIBES",
        }],
    }

    # 按包命名：迁移后 DIST 是共享产品根（D:\Portapps），
    # 所有包共用 sbom.spdx.json 会互相覆盖。
    out = DIST / f"{PKG}-sbom.spdx.json"
    out.write_text(json.dumps(sbom, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("[OK] " + str(out) + " (" + str(len(files)) + " 个文件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
