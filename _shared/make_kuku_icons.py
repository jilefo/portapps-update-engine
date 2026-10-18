# -*- coding: utf-8 -*-
r"""make_kuku_icons.py —— 为 KukuAIPortable 生成合规图标集

PortableApps.com Format 3.9 对图标的要求：
  appicon.ico       必需，须含 6 种尺寸/色深组合：
                    16/32/48 px 的 256 色版 + 16/32/48 px 的 TrueColor+Alpha 版
  appicon_16.png    必需，16x16
  appicon_32.png    必需，32x32
  appicon_128.png   推荐，128x128

优先从 GenFlowPro.exe 的 PE 资源里提取图标（原始设计稿），
提取失败则回退到 resources\genflowpro\app-icon.png 并放大。
"""
from __future__ import annotations

import io
import shutil
import struct
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"<仓库根>/KukuAIPortable")
APPDIR = ROOT / "portableapps" / "App" / "AppInfo"
EXE = ROOT / "portableapps" / "App" / "KukuAI" / "GenFlowPro.exe"
FALLBACK_PNG = ROOT / "portableapps" / "App" / "KukuAI" / "resources" / \
    "genflowpro" / "app-icon.png"

NEEDED_PNG = {16: "appicon_16.png", 32: "appicon_32.png", 128: "appicon_128.png"}


def extract_ico_from_pe(exe: Path, out_ico: Path) -> bool:
    """从 PE 资源段提取 RT_GROUP_ICON。

    RT_GROUP_ICON 资源本身就是合法的 .ico 字节流，但要**先校验自洽性**：
        头部 6 字节 + count * 16 字节目录 + 各图像数据，必须都在资源长度内。

    实测坑：Electron 打包器（KukuAI / GenFlowPro.exe 即是）常把
    RT_GROUP_ICON 写成**截断的存根**——声明 count=7，资源却只有 104 字节
    （6 + 7*16 = 118 > 104），图像数据并不在资源内，而是分散在 RT_ICON 各级
    资源中。这种存根直接写成 .ico 会得到 PIL 无法识别的残缺文件。
    因此这里只接受「自洽」的完整资源，其余走 PNG 回退路径。
    """
    try:
        import pefile  # noqa
    except ImportError:
        return False
    try:
        pe = pefile.PE(str(exe))
    except Exception:
        return False
    try:
        res = getattr(pe, "DIRECTORY_ENTRY_RESOURCE", None)
        if not res:
            return False
        for entry in res.entries:
            if entry.id != 14:              # RT_GROUP_ICON
                continue
            d1 = getattr(entry, "directory", None)
            if not d1:
                continue
            for e2 in d1.entries:
                d2 = getattr(e2, "directory", None)
                if not d2:
                    continue
                for e3 in d2.entries:
                    st = getattr(getattr(e3, "data", None), "struct", None)
                    if st is None:
                        continue
                    try:
                        data = pe.get_data(st.OffsetToData, st.Size)
                    except Exception:
                        continue
                    if len(data) < 6:
                        continue
                    _res, typ, count = struct.unpack("<HHH", data[:6])
                    if typ != 1 or count < 1:
                        continue
                    # 自洽性校验：目录区必须完整，且最大 offset+size 不越界
                    need = 6 + count * 16
                    if len(data) < need:
                        print(f"[warn] RT_GROUP_ICON 截断（{len(data)}B < {need}B），"
                              f"改用 PNG 图标源")
                        return False
                    max_end = 0
                    off = 6
                    for _ in range(count):
                        _w, _h, _c, _r, _p, _b, size, offset = \
                            struct.unpack("<BBBBHHIH", data[off:off + 16])
                        off += 16
                        max_end = max(max_end, offset + size)
                    if max_end > len(data):
                        print(f"[warn] RT_GROUP_ICON 图像数据越界"
                              f"（{max_end} > {len(data)}），改用 PNG 图标源")
                        return False
                    out_ico.write_bytes(data)
                    return True
    except Exception as e:
        print(f"[warn] PE 资源遍历异常: {e}")
    finally:
        try:
            pe.close()
        except Exception:
            pass
    return False


def main() -> int:
    from PIL import Image

    APPDIR.mkdir(parents=True, exist_ok=True)
    ico_path = APPDIR / "appicon.ico"

    # ---- 1) 尝试从 exe 提取
    got = False
    if EXE.is_file():
        try:
            got = extract_ico_from_pe(EXE, ico_path)
        except Exception as e:
            print(f"[warn] PE 图标提取异常: {e}")

    # ---- 2) 回退：用 png 生成
    base = None
    if got and ico_path.is_file():
        try:
            im = Image.open(ico_path)
            base = im.convert("RGBA")
            print(f"[OK] 从 GenFlowPro.exe 提取图标 {base.size}")
        except Exception:
            base = None
    if base is None:
        if not FALLBACK_PNG.is_file():
            print(f"[FAIL] 无可用图标源（{EXE} / {FALLBACK_PNG}）")
            return 1
        base = Image.open(FALLBACK_PNG).convert("RGBA")
        print(f"[OK] 使用内置图标 {base.size}")

    # ---- 3) 生成各尺寸 PNG（最近邻放大，避免模糊）
    for size, name in NEEDED_PNG.items():
        im = base
        if im.size[0] != size or im.size[1] != size:
            im = base.resize((size, size), Image.NEAREST)
        im.save(APPDIR / name)
        print(f"  [OK] {name} ({size}x{size})")

    # ---- 4) ICO：统一自建多尺寸容器
    # PortableApps.com Format 3.9 要求 appicon.ico 含 6 种尺寸/色深组合：
    #   16/32/48 px 的 256 色版 + 16/32/48 px 的 TrueColor+Alpha 版。
    # PIL 的 save(sizes=...) 对小尺寸源图会静默丢弃条目（实测只留 16px），
    # 故手工拼 ICONDIR + ICONDIRENTRY* + 各尺寸负载，确保齐全可读。
    ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
    blobs = []
    for px in ICO_SIZES:
        buf = io.BytesIO()
        base.resize((px, px), Image.LANCZOS).save(buf, format="PNG")
        blobs.append((px, buf.getvalue()))

    offset = 6 + len(blobs) * 16
    entries = b""
    payload = b""
    for px, data in blobs:
        dim = 0 if px >= 256 else px
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(data), offset)
        payload += data
        offset += len(data)
    ico_path.write_bytes(struct.pack("<HHH", 0, 1, len(blobs)) + entries + payload)
    print(f"[OK] appicon.ico 含 {len(blobs)} 种尺寸 "
          f"({'/'.join(str(s) for s in ICO_SIZES)} px)")

    # ---- 5) 核对
    ok_all = True
    for f in ["appicon.ico", "appicon_16.png", "appicon_32.png", "appicon_128.png"]:
        p = APPDIR / f
        exists = p.is_file()
        ok_all = ok_all and exists
        print(f"  {'OK ' if exists else 'MISS'} {f} "
              f"({p.stat().st_size if exists else 0} B)")
    # 回读校验 ICO 可解析
    try:
        with Image.open(ico_path) as chk:
            sizes = sorted(chk.ico.sizes())
        print(f"  [校验] ICO 可读，尺寸: {sizes}")
    except Exception as e:
        print(f"  [校验] ICO 读取失败: {e}")
        ok_all = False
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
