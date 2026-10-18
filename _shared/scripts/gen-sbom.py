# -*- coding: utf-8 -*-
"""gen-sbom.py —— 生成 SPDX SBOM（通用版，包名自动推导）

只依赖标准库，输出 dist/sbom.spdx.json。
SBOM 记录本仓库便携化配置与原程序文件清单（不做依赖解析）。
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _pkg import PKG, REPO, REPO_ROOT   # noqa: E402

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path



DIST = REPO / "dist"
NAMESPACE = "https://greensoftmake.local/spdx/" + PKG


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    pkg_dir = DIST / PKG
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

    out = DIST / "sbom.spdx.json"
    out.write_text(json.dumps(sbom, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("[OK] " + str(out) + " (" + str(len(files)) + " 个文件)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
