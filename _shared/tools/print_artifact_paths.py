# -*- coding: utf-8 -*-
r"""print_artifact_paths.py —— 解析单包发布产物的真实路径，供 CI 消费

为什么需要它
------------
包级 release.yml 原来把附件路径**写死**成工作区相对路径 `<Pkg>/dist/*.zip`。
但产物路径由 `_paths.artifact_root()` 决定，而它是动态的：

    本机      -> D:\Portapps                （_shared/portapps_root.txt 指向）
    CI 新克隆 -> <内置默认产品根>            （该文件被 .gitignore 排除，CI 上没有）

实测：CI 上 `product_dir()` 解析到的是产品根下的 `<Pkg>`，而 `<Pkg>/dist/<Pkg>`
在 CI 上根本不存在，于是附件路径永远对不上——**64 份写死的路径全是猜的**。

修法是把路径交回唯一的定义处，而不是再抄一份字符串：本工具直接复用
`package_formula.artifact_paths()`，按当前环境解析出真实绝对路径。

用法（工作流里）
----------------
```yaml
# bash runner（ubuntu-latest）
- run: python _shared/tools/print_artifact_paths.py <Pkg> >> $GITHUB_OUTPUT
# pwsh runner（windows-latest）
- run: python _shared/tools/print_artifact_paths.py <Pkg> >> $env:GITHUB_OUTPUT
```

输出（GITHUB_OUTPUT 键值）
--------------------------
  --kind formula（默认，配 package_formula.py 用）：
    formula=<配方 zip 绝对路径>
    sums=<SHA256 文件绝对路径>
  --kind product（配 package-paf.py + gen-sbom.py 用）：
    zip=<产品 zip 绝对路径>
    sums=<SHA256 文件绝对路径>
    sbom=<SBOM 绝对路径>

★ 缺产物时 **exit 1** 并列明缺了什么：绝不能 WARN 之后 return 0。
  原来 `package-paf.py --checksum-only` 就是这么干的——跳过打包、打印
  [WARN]、return 0，工作流看着全绿，实际发出去的是 0 个附件。
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # _shared/tools
REPO = HERE.parent.parent
SCRIPTS = REPO / "_shared" / "scripts"


def _load_package_formula():
    """按文件路径加载 package_formula.py。

    它在 _shared/scripts/ 下（与 build-* / test_structure 同目录），
    不在 tools/ 里，故用 importlib 按路径加载；路径定义只保留一处。
    """
    sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(HERE.parent))
    spec = importlib.util.spec_from_file_location(
        "package_formula", SCRIPTS / "package_formula.py")
    if spec is None or spec.loader is None:
        print("[FAIL] 找不到 %s" % (SCRIPTS / "package_formula.py"),
              file=sys.stderr)
        raise SystemExit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _product_paths(pkg):
    """产品态产物路径：zip / SHA256SUMS / sbom，均落在 _paths.artifact_root()。"""
    sys.path.insert(0, str(HERE.parent))
    import _paths
    root = _paths.artifact_root(pkg)
    return (root / ("%s.zip" % pkg),
            root / ("%s-SHA256SUMS.txt" % pkg),
            root / ("%s-sbom.spdx.json" % pkg))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("[FAIL] 用法：print_artifact_paths.py <Pkg> "
              "[--kind formula|product] [--out <目录>]", file=sys.stderr)
        return 2
    pkg = args[0]

    kind = "formula"
    if "--kind" in sys.argv:
        i = sys.argv.index("--kind")
        if i + 1 >= len(sys.argv):
            print("[FAIL] --kind 缺参数", file=sys.stderr)
            return 2
        kind = sys.argv[i + 1]
    if kind not in ("formula", "product"):
        print("[FAIL] --kind 只支持 formula|product，收到 %r" % kind,
              file=sys.stderr)
        return 2

    if kind == "product":
        zip_path, sums_path, sbom_path = _product_paths(pkg)
        pairs = [("zip", zip_path), ("sums", sums_path), ("sbom", sbom_path)]
        hint = "先跑 package-paf.py %s 与 gen-sbom.py %s" % (pkg, pkg)
    else:
        pf = _load_package_formula()
        outdir = pf.default_outdir()
        if "--out" in sys.argv:
            i = sys.argv.index("--out")
            if i + 1 >= len(sys.argv):
                print("[FAIL] --out 缺参数", file=sys.stderr)
                return 2
            outdir = Path(sys.argv[i + 1])
        z, s = pf.artifact_paths(outdir, pf.read_version())
        pairs = [("formula", z), ("sums", s)]
        hint = "先跑 package_formula.py %s" % pkg

    missing = [p for _, p in pairs if not p.is_file()]
    if missing:
        for p in missing:
            print("[FAIL] 产物不存在：%s（%s）" % (p, hint), file=sys.stderr)
        return 1

    # 只有这些行走 stdout —— 其余一律走 stderr，别污染 GITHUB_OUTPUT
    for key, p in pairs:
        print("%s=%s" % (key, p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
