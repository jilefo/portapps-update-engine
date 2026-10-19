# -*- coding: utf-8 -*-
r"""gen_release_workflows.py —— 39 个包的包级 workflow 唯一生成源

为什么要有它
------------
包级 `.github/workflows/` 最早是 scaffold 整包复制出来的，之后只被人用
文本替换修过路径（`fix_package_workflows.py`）。文本替换能改字符串，
改不了**语义**，于是这些文件里留下了四处彼此独立的错：

  1. 附件写 `<Pkg>/dist/*.7z`，而打包器只产 `.zip` —— 格式对不上；
  2. 打包步带 `--checksum-only`，该开关会**跳过打包**，产物一个都没有；
  3. 而 `package-paf.py` 遇到没产物时是 `[WARN] + return 0`
     —— 三重叠加的结果：39 条流水线全绿，附件 0 个，没人报警；
  4. 附件路径写死成工作区相对路径，但产物路径由 `_paths` 动态决定，
     CI 上新解析出来的位置跟写死的那个**必然不是同一个**。

问题 1~3 的根源是"生成器与打包器各写各的，互不知情"；
问题 4 的根源是"路径抄了一份字符串"。
所以现在反过来：workflow 由本脚本生成，附件路径不写字面量，
而是从 `print_artifact_paths.py` 动态解析。

用法
----
    python _shared/tools/gen_release_workflows.py                # 生成 39 包
    python _shared/tools/gen_release_workflows.py --check        # 只校验，不写
    python _shared/tools/gen_release_workflows.py CursorPortable # 只生成指定包

★ `--check` 必须报告检查了多少个包、多少条不符。只说"没问题"、不说检查量
  的门禁，等于没有——真出事时它照样一片绿。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# PyYAML 不是标准库：CI 上可能没有。缺失时如实跳过并说明，
# 绝不能"解析不了就当通过"——那正是假绿的常见做法。
try:
    import yaml as _YAML
except ImportError:
    _YAML = None

HEADER = """\
# 本文件由 _shared/tools/gen_release_workflows.py 生成，请勿手工编辑；
# 改模板请改生成器，否则 --check 会报漂移。
#
# ★ 发的是「配方」不是程序本体：
#   第三方程序在 portableapps/App/<程序>/ 下，被 .gitignore 排除，
#   CI 在新克隆上构建出的产品树是"有启动器、无程序"的空壳，发布它没有意义。
#   因此这里打包发布的是本包的便携化配方（portableapps/ + LICENSE +
#   THIRD_PARTY_NOTICES.md + README.md）。
#   整仓级别的四平台发布走仓库根 .github/workflows/release.yml。
#
# ★ tag 带包名前缀（<Pkg>@v*）：
#   39 个包若都用 v*，推一个 v1.7.0 会同时触发 39 条流水线抢建同一个
#   Release。加前缀后各发各的，互不干扰。
"""

RELEASE = HEADER + """\
name: release
on:
  push:
    tags: ['{pkg}@v*']

permissions:
  contents: write          # 创建 Release 需要；缺了会 403

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 结构校验（本包）
        run: python _shared/scripts/test_structure.py {pkg} --ini-only

      - name: 打包配方
        run: python _shared/scripts/package_formula.py {pkg}

      # 产物路径由 _paths 动态决定（本机 D:\\Portapps / CI 上各不相同），
      # 不能写死 —— 写死的那 34 份没有一份能对上。
      - name: 解析产物路径
        id: artifacts
        run: python _shared/tools/print_artifact_paths.py {pkg} >> $GITHUB_OUTPUT

      - name: 创建 Release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            ${{{{ steps.artifacts.outputs.formula }}}}
            ${{{{ steps.artifacts.outputs.sums }}}}
"""

BUILD = """\
# 本文件由 _shared/tools/gen_release_workflows.py 生成，请勿手工编辑。
#
# 手动触发的构建验证：在**有第三方程序**的 runner（自建 runner，或已备好
# 产品根的机器）上才有意义。GitHub 托管 runner 是全新克隆，没有第三方程序，
# 构建出来的是空壳——这是设计使然，不是故障。
name: portableapps
on:
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    # ★ env 必须在 job 级：写在某个 step 的 env: 里只对该 step 生效，
    #   而真正要用它的是后面的 build-portable / package-paf / gen-sbom
    #   三个 step。放错位置不会报错，只会让它们悄悄解析到默认产品根。
    env:
      # 产品根固定到 runner 临时目录：不依赖 D: 盘存在，也不把产物
      # 写进工作区（否则会被后续 git 操作扫到）。
      PORTAPPS_ROOT: ${{{{ runner.temp }}}}\\portapps
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 准备产品根
        run: New-Item -ItemType Directory -Force -Path "$env:PORTAPPS_ROOT" | Out-Null

      - name: 构建便携包
        run: python _shared/scripts/build-portable.py {pkg}

      - name: 结构校验
        run: python _shared/scripts/test_structure.py {pkg}

      - name: 打包并生成校验和
        run: python _shared/scripts/package-paf.py {pkg}

      - name: 生成 SBOM
        run: python _shared/scripts/gen-sbom.py {pkg}

      # 原来这里写 path: {pkg}/dist/ —— 迁移后该目录已不存在，上传必空。
      - name: 解析产物路径
        id: artifacts
        run: python _shared/tools/print_artifact_paths.py {pkg} --kind product >> $env:GITHUB_OUTPUT

      - name: 上传 artifact
        uses: actions/upload-artifact@v4
        with:
          name: {pkg}
          path: |
            ${{{{ steps.artifacts.outputs.zip }}}}
            ${{{{ steps.artifacts.outputs.sums }}}}
            ${{{{ steps.artifacts.outputs.sbom }}}}
          if-no-files-found: error
"""


def render(pkg: str) -> tuple[str, str]:
    return RELEASE.format(pkg=pkg), BUILD.format(pkg=pkg)


def packages() -> list:
    return sorted(p.name for p in ROOT.iterdir()
                  if p.is_dir() and (p / "portableapps").is_dir())


def _yaml_ok(p: Path, sink: list) -> bool:
    """解析一份 YAML；失败则记入 sink。PyYAML 缺失时返回 True（不假装解析过）。"""
    if _YAML is None:
        return True
    try:
        d = _YAML.safe_load(_read(p))
    except Exception as e:
        sink.append("%s: %s" % (p.as_posix(), str(e).replace("\n", " ")[:120]))
        return False
    return isinstance(d, dict)


def _read(p: Path) -> str:
    """读已存在的工作流文件，用于与模板比对。

    ★ 两处必须归一化，否则门禁会在某个平台上恒红：
      1) 行尾——`write_text()` 在 Windows 上把 \\n 翻译成 \\r\\n（实测 49 处），
         而 .gitattributes 的 `* text=auto eol=crlf` 本来就要求工作区是 CRLF。
         所以不是去改写入，而是比对时把 CRLF 折算成 LF，让 Windows/Linux 同判。
      2) BOM——现有 72 份文件带 UTF-8 BOM，新写的不带；比对时剥掉。
    """
    raw = p.read_bytes()
    t = raw.decode("utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8")
    return t.replace("\r\n", "\n")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check = "--check" in sys.argv
    dry = "--dry-run" in sys.argv

    pkgs = args or packages()
    if not pkgs:
        print("[FAIL] 未枚举到任何包（仓库根下没有含 portableapps/ 的目录）")
        return 1

    drift, missing, written, total_files, unparsable = [], [], 0, 0, []
    for pkg in pkgs:
        wf = ROOT / pkg / ".github" / "workflows"
        want = {}
        rel, bld = render(pkg)
        want["release.yml"] = rel
        want["portableapps.yml"] = bld
        for name, text in want.items():
            total_files += 1
            f = wf / name
            # 逐字节一致 ≠ 合法：模板若被改坏，78 份会一起坏而 --check 仍绿。
            # 故同时做一次 YAML 解析（PyYAML 缺失时如实跳过，不假装通过）。
            if f.is_file():
                _yaml_ok(f, unparsable)
            if not f.is_file():
                missing.append("%s/.github/workflows/%s" % (pkg, name))
                if not check and not dry:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text(text, encoding="utf-8")   # 无 BOM
                    written += 1
                continue
            if _read(f) != text:
                drift.append("%s/.github/workflows/%s" % (pkg, name))
                if not check and not dry:
                    # 不在此留 .bak：这些文件本身受 git 版本控制，旧内容从
                    # git 历史即可取回。往受控目录里塞 .bak 正是本次要清的
                    # 那类垃圾（仓库里已躺着 6 个 .bak6/.bak7 / .bakfix）。
                    f.write_text(text, encoding="utf-8")
                    written += 1

    print("检查了 %d 个包 × 2 份 workflow = %d 份" % (len(pkgs), total_files))
    if missing:
        print("  缺失 %d 份：%s" % (len(missing), ", ".join(missing)))
    if drift:
        print("  与模板不符 %d 份：%s" % (len(drift), ", ".join(drift)))
    if _YAML is None:
        print("  [i] YAML 解析已跳过：PyYAML 不可用（未安装时不要假装通过）")
    else:
        print("  YAML 解析 %d 份，失败 %d 份"
              % (total_files - len(missing), len(unparsable)))
        for u in unparsable[:5]:
            print("      [X] " + u)

    if check:
        bad = len(missing) + len(drift) + len(unparsable)
        print("[%s] 一致 %d 份 / 不符 %d 份 / 缺失 %d 份 / 解析失败 %d 份"
              % ("PASS" if bad == 0 else "FAIL",
                 total_files - len(missing) - len(drift),
                 len(drift), len(missing), len(unparsable)))
        return 1 if bad else 0

    print("[%s] 新写入 %d 份（--dry-run 时未落盘）" % ("OK", written))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
