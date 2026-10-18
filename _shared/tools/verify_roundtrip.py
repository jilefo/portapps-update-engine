# -*- coding: utf-8 -*-
"""verify_roundtrip.py —— 校验克隆前后每个文件的编码/BOM 未被改写。

用法：python verify_roundtrip.py <源仓库> <克隆仓库>
"""
import os
import subprocess
import sys

SRC = sys.argv[1].rstrip("\\/")
DST = sys.argv[2].rstrip("\\/")


def enc(p: str) -> str:
    with open(p, "rb") as f:
        b = f.read(3)
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "UTF16"
    if b == b"\xef\xbb\xbf":
        return "UTF8BOM"
    return "UTF8noBOM"


def main() -> int:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=DST,
                         capture_output=True)
    files = [f.decode("utf-8") for f in out.stdout.split(b"\0") if f]
    bad, u16, bom = [], [], []
    for f in files:
        p1 = os.path.join(SRC, f.replace("/", os.sep))
        p2 = os.path.join(DST, f.replace("/", os.sep))
        if not (os.path.isfile(p1) and os.path.isfile(p2)):
            bad.append((f, "缺失", "缺失"))
            continue
        a, b = enc(p1), enc(p2)
        if a != b:
            bad.append((f, a, b))
        if b == "UTF16":
            u16.append(f)
        elif b == "UTF8BOM":
            bom.append(f)

    print(f"比对文件数     : {len(files)}")
    print(f"编码/BOM 变化  : {len(bad)} 处")
    for f, a, b in bad[:20]:
        print(f"    {f}  源={a} 克隆={b}")
    print(f"UTF-16LE 文件  : {len(u16)} 个")
    for f in u16:
        print(f"    {f}")
    print(f"UTF-8 BOM 文件 : {len(bom)} 个")
    ok = not bad
    print()
    print("结论：" + ("编码零漂移，UTF-16LE 保护生效。" if ok
                     else "存在编码漂移，需处理！"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
