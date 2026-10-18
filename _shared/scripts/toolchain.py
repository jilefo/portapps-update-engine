# -*- coding: utf-8 -*-
"""toolchain.py —— 本项目的工具链转发器

真正的定位逻辑在 `../../_shared/toolchain.py`，此处仅做转发，
保证项目脚本 `from toolchain import ...` 在任何层级下都能工作。
"""
import importlib.util
import sys
from pathlib import Path

_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "_shared" / "toolchain.py",
    Path(__file__).resolve().parents[1] / "_shared" / "toolchain.py",
    Path(__file__).resolve().parent / "toolchain.py",
]


def _load():
    last = None
    for c in _CANDIDATES:
        if c.is_file():
            spec = importlib.util.spec_from_file_location("_paf_toolchain", c)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
                return mod
            except Exception as e:      # noqa: BLE001
                last = e
    sys.stderr.write(f"[FAIL] 无法加载 _shared/toolchain.py: {last}\n")
    raise SystemExit(2)


_mod = _load()
find_toolchain = _mod.find_toolchain
pal_dir = _mod.pal_dir
build_launcher_script = _mod.build_launcher_script
update_engine_script = _mod.update_engine_script
config_for = _mod.config_for

if __name__ == "__main__":
    try:
        tc = find_toolchain(Path(__file__).resolve().parent)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
    print(f"[OK] 工具链: {tc}")
    print(f"     PAL    : {pal_dir(tc)}")
