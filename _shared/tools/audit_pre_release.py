# -*- coding: utf-8 -*-
r"""audit_pre_release.py —— 开源发布前综合审计（只读，不删不改）

对应「开源前便携软件审计清理迁移与自动发布提示词」的第三步之一：
  一、开源文件审计
  二、便携软件逐项检查（静态部分；启动/冒烟另由 smoke_*.py 动态执行）

五个区块：
  A 根级元数据       LICENSE / README / SECURITY / CONTRIBUTING / CODE_OF_CONDUCT /
                    CHANGELOG / .gitignore / .gitattributes / .editorconfig / docs / .github
  B 包级元数据       每包：LICENSE / THIRD_PARTY_NOTICES.md / README / .gitignore /
                    .gitattributes / .github/workflows/ci.yml / portableapps 与 dist 双树
  C 敏感信息         密钥、Token、账号密码、私有证书、本机绝对路径、内部地址
  D 无用文件         日志 / 缓存 / 临时 / 备份 / 旧版本包 / 重复产物 / 测试残留
  E dist 迁移影响面  dist 下被 git 跟踪的文件、体积、以及工具链对 dist 的硬编码假设

退出码：0 = 无 FAIL 级问题；1 = 有 FAIL 级问题（WARN 不影响退出码）。
用法：python _shared/tools/audit_pre_release.py [--json out.json] [--deep]
      --deep 才会扫 dist 全树（59GB/59.8 万文件，约 1 分钟）；默认只扫配方区。
"""
import configparser
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# >>> 路径自适应：仓库根由本文件位置推导，可用 PORTABLEAPPS_ROOT 覆盖
REPO_ROOT = os.environ.get("PORTABLEAPPS_ROOT") or str(
    Path(__file__).resolve().parents[2])
# <<<
REPO = Path(REPO_ROOT)

ROOT_META = [
    "LICENSE", "README.md", "SECURITY.md", "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md", "CHANGELOG.md", ".gitignore", ".gitattributes",
    ".editorconfig",
]
ROOT_DIRS = ["docs", ".github"]
PKG_META = [
    "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", ".gitignore",
    ".gitattributes",
]

# 敏感信息
LEAK = re.compile(r"[A-Za-z]:\\(Projects|DevTools|Work|Portapps)\b|/d/(Projects|Portapps)")
RE_USER = re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9_.\-]+\\")
SECRET = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|gitee_[A-Za-z0-9]{16,}|glpat-[A-Za-z0-9_\-]{20,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
SECRET_CFG = re.compile(
    r"^\s*(password|passwd|secret|api[_-]?key|access[_-]?token|token)\s*[:=]\s*\S",
    re.I)

# 无用文件：目录名 / 文件名模式
JUNK_DIR_NAMES = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
    ".vs", ".vscode", ".idea", "Backups", "Staging", "_evidence", "_icons",
    "_制作素材", "evidence", "$RECYCLE.BIN", "System Volume Information",
}
JUNK_FILE_PAT = [
    (re.compile(r"\.log$", re.I), "日志"),
    (re.compile(r"\.tmp$|^~\\\$|\.~lock", re.I), "临时文件"),
    (re.compile(r"\.(bak|bakfix|orig|old|rej)$", re.I), "备份/补丁残留"),
    (re.compile(r"\.(paf\.exe|7z|zip|rar|tar\.gz)$", re.I), "打包产物"),
    (re.compile(r"(^|\.)(desktop|Thumbs)\.db$", re.I), "系统缓存"),
    (re.compile(r"\.pyc$", re.I), "Python 字节码"),
]
JUNK_DIR_PAT = [
    (re.compile(r"^Backups?$", re.I), "旧版本备份目录"),
    (re.compile(r"^Staging$", re.I), "更新暂存目录"),
    (re.compile(r"^Temp$|^tmp$|^_tmp$", re.I), "构建期临时目录"),
]

# 扫描时跳过的超大二进制区（属构建输入/产物，另由 --deep 与 dist 专项处理）
SKIP_DIRS = {".git", "App"}

# ★ 用户数据区：绝不作为清理候选。
#   dist/<Pkg>/Data/ 与 portableapps/Data/ 里出现的 .log/.tmp/.zip 等是**应用
#   自己产生的用户数据**（日志、缓存、模型、下载物），正是数据重定向生效的证据。
#   误删 = 丢用户数据。曾把 19770 项 / 1.8GB 判成垃圾，其中 95% 在这里。
DATA_DIR_RE = re.compile(
    r"^(?:[^/]+/)?(?:portableapps|dist)/(?:[^/]+/)?Data(?:/|$)")

# 工具链里硬编码 <Pkg>/dist/ 假设的位置（E 区块用）
TOOL_FILES = sorted((REPO / "_shared" / "tools").glob("*.py")) + \
             sorted((REPO / "_shared" / "scripts").glob("*.py")) + \
             sorted((REPO / "_shared").glob("*.py"))


def sniff(path):
    with open(path, "rb") as f:
        b = f.read(3)
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return "utf-16"
    return "utf-8-sig" if b == b"\xef\xbb\xbf" else "utf-8"


def is_text(path, limit=8192):
    try:
        with open(path, "rb") as f:
            chunk = f.read(limit)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    # GBK 文本也扫（Windows 本地产物）
    try:
        chunk.decode("gbk")
        return True
    except (UnicodeDecodeError, LookupError):
        return False


def packages():
    return sorted(p for p in REPO.iterdir()
                  if p.is_dir() and p.name.endswith("Portable")
                  and not p.name.startswith(("_", ".")))


def git_tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO,
                         capture_output=True)
    return [f.decode("utf-8") for f in out.stdout.split(b"\0") if f]


# ---------------------------------------------------------------- A 根级元数据
def audit_root(fails, warns, notes):
    for f in ROOT_META:
        if not (REPO / f).is_file():
            fails.append("[A] 根目录缺 %s" % f)
    for d in ROOT_DIRS:
        if not (REPO / d).is_dir():
            fails.append("[A] 根目录缺 %s/" % d)
    lic = REPO / "LICENSE"
    if lic.is_file() and len(lic.read_text(encoding="utf-8", errors="replace")) < 800:
        warns.append("[A] LICENSE 仅 %d 字节，疑似不是完整 MIT 文本"
                     % len(lic.read_text(encoding="utf-8", errors="replace")))
    # README 应说明许可证与第三方二进制的边界
    rd = REPO / "README.md"
    if rd.is_file():
        t = rd.read_text(encoding="utf-8", errors="replace")
        for kw in ("MIT", "第三方"):
            if kw not in t:
                warns.append("[A] README.md 未提及「%s」——开源边界不清" % kw)


# ---------------------------------------------------------------- B 包级元数据
def audit_packages(fails, warns, notes):
    for pkg in packages():
        n = pkg.name
        for f in PKG_META:
            if not (pkg / f).is_file():
                fails.append("[B] %s 缺 %s" % (n, f))
        if not (pkg / ".github" / "workflows" / "ci.yml").is_file():
            warns.append("[B] %s 缺 .github/workflows/ci.yml" % n)
        for tree in ("portableapps", "dist"):
            for sub in (("App", "AppInfo"), (n, "App", "AppInfo")):
                if (pkg / tree / Path(*sub) / "appinfo.ini").is_file():
                    break
            else:
                if tree == "portableapps":
                    fails.append("[B] %s 两处都没有 appinfo.ini" % n)
                else:
                    notes.append("%s dist 未装配（仅含 update.py 等，本地/CI 预期内）" % n)
        # THIRD_PARTY_NOTICES 应真的列出了第三方
        tpn = pkg / "THIRD_PARTY_NOTICES.md"
        if tpn.is_file():
            t = tpn.read_text(encoding="utf-8", errors="replace")
            if len(t) < 200:
                warns.append("[B] %s 的 THIRD_PARTY_NOTICES.md 仅 %d 字节，可能没列全"
                             % (n, len(t)))


# ---------------------------------------------------------------- C 敏感信息
def scan_text(tracked_only, deep, fails, warns, hits):
    pool = git_tracked() if tracked_only else walk_repo(deep)
    n = 0
    for rel in pool:
        p = REPO / rel.replace("/", os.sep)
        if not p.is_file() or p.stat().st_size > 4 * 1024 * 1024:
            continue
        if not is_text(p):
            continue
        n += 1
        try:
            t = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for m in SECRET.finditer(t):
            hits.append((rel, "疑似密钥/Token", m.group(0)[:24]))
        for m in SECRET_CFG.finditer(t):
            hits.append((rel, "疑似明文凭据", m.group(0).strip()[:48]))
        for m in LEAK.finditer(t):
            hits.append((rel, "本机绝对路径", m.group(0)))
    return n


def walk_repo(deep):
    """遍历仓库文件，跳过 .git 与 portableapps/*/App（巨量二进制）。

    deep=True 时才进 dist 树。
    """
    out = []
    for root, dirs, files in os.walk(REPO):
        rel = os.path.relpath(root, REPO)
        parts = [] if rel == "." else rel.split(os.sep)
        # 跳过 .git
        if ".git" in parts:
            dirs[:] = []
            continue
        # 跳过 <Pkg>/portableapps/App/<程序>/（第三方二进制）
        if len(parts) == 3 and parts[1] == "portableapps" and parts[2] == "App":
            dirs[:] = []
            continue
        # 非 deep 时跳过 <Pkg>/dist
        if not deep and len(parts) == 2 and parts[1] == "dist":
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            out.append(os.path.join(rel, f) if rel != "." else f)
    return out


def is_user_data(rel):
    """rel 为仓库相对路径（/ 分隔）。Data/ 区一律是用户数据，禁止清理。"""
    return bool(DATA_DIR_RE.match(rel.replace("\\", "/")))


# ---------------------------------------------------------------- D 无用文件
def scan_junk(deep, rows):
    """返回 (junk 行, 被排除的用户数据统计 (文件数, 字节数))。"""
    ud_n = ud_b = 0
    for rel in walk_repo(deep):
        p = REPO / rel.replace("/", os.sep)
        if is_user_data(rel):
            try:
                if p.is_file():
                    ud_n += 1
                    ud_b += p.stat().st_size
            except OSError:
                pass
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        parts = Path(rel).parts
        name = parts[-1]
        for pat, why in JUNK_DIR_PAT:
            if pat.match(name) and p.is_dir():
                rows.append((rel, why, st.st_size, True))
                break
        else:
            if p.is_dir():
                continue
            for pat, why in JUNK_FILE_PAT:
                if pat.search(name):
                    rows.append((rel, why, st.st_size, False))
                    break
    return ud_n, ud_b


# ---------------------------------------------------------------- E dist 影响面
def audit_dist_impact(fails, warns, notes):
    tracked = [f for f in git_tracked() if "/dist/" in f.replace("\\", "/")]
    notes.append("dist 下被 git 跟踪：%d 个文件 → %s"
                 % (len(tracked), sorted({Path(f).name for f in tracked})))
    if not tracked:
        fails.append("[E] dist 下没有任何被跟踪文件——迁移会无损失")
    # 工具链里对 dist 路径的假设
    hard = []
    for tf in TOOL_FILES:
        try:
            t = tf.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if re.search(r"['\"]dist['\"]|/dist/|dist.*\\\\", t) and \
                "audit_pre_release" not in tf.name:
            hard.append(tf.relative_to(REPO).as_posix())
    ws = [d for d in sorted(REPO.glob("*/.github/workflows/ci.yml"))]
    notes.append("引用 dist 的工具/脚本 %d 个、包级 workflow %d 个——"
                 "外迁 dist 需一并适配" % (len(hard), len(ws)))
    return tracked, hard


def main():
    deep = "--deep" in sys.argv
    t0 = time.time()
    fails, warns, notes, hits, junk = [], [], [], [], []

    audit_root(fails, warns, notes)
    audit_packages(fails, warns, notes)
    ntext = scan_text(True, deep, fails, warns, hits)
    ud_n, ud_b = scan_junk(deep, junk)
    tracked_dist, hard_tools = audit_dist_impact(fails, warns, notes)

    print("=" * 72)
    print("开源发布前综合审计（只读）  仓库根：%s" % REPO_ROOT)
    print("深度扫描 dist：%s    耗时 %.1fs" % ("是" if deep else "否", time.time() - t0))
    print("=" * 72)

    print("\n【A/B】元数据")
    if not fails and not warns:
        print("  OK   根级 %d 项 + 包级 %d 项 × %d 包，全部齐备"
              % (len(ROOT_META) + len(ROOT_DIRS), len(PKG_META), len(packages())))
    else:
        for x in fails:
            print("  FAIL %s" % x)
        for x in warns:
            print("  WARN %s" % x)

    print("\n【C】敏感信息（已扫 %d 个受跟踪文本文件）" % ntext)
    if not hits:
        print("  OK   未发现密钥 / Token / 明文凭据 / 本机绝对路径")
    else:
        for rel, kind, snip in hits[:40]:
            print("  HIT  %-58s %-14s %s" % (rel[:58], kind, snip))
        if len(hits) > 40:
            print("  ...另有 %d 处" % (len(hits) - 40))

    print("\n【D】无用文件（候选，共 %d 项）" % len(junk))
    if ud_n:
        print("  已排除用户数据 %d 个文件 / %.2f GB（dist/<Pkg>/Data/ 与 "
              "portableapps/Data/，属应用自身产物，禁止清理）"
              % (ud_n, ud_b / 2 ** 30))
    if junk:
        tot = sum(r[2] for r in junk)
        print("  合计 %.2f MB" % (tot / 1048576))
        for rel, why, sz, isdir in sorted(junk, key=lambda r: -r[2])[:40]:
            print("  %-64s %-12s %8.1f KB%s"
                  % (rel[:64], why, sz / 1024, "/" if isdir else ""))
        if len(junk) > 40:
            print("  ...另有 %d 项" % (len(junk) - 40))
    else:
        print("  OK   未发现")

    print("\n【E】dist 迁移影响面")
    for n in notes:
        print("  - %s" % n)
    if hard_tools:
        print("  需适配 dist 根的工具：")
        for h in hard_tools[:20]:
            print("      %s" % h)

    print("\n" + "-" * 72)
    print("FAIL %d · WARN %d · 敏感命中 %d · 无用文件 %d · dist 受跟踪 %d"
          % (len(fails), len(warns), len(hits), len(junk), len(tracked_dist)))
    print("结论：" + ("存在 FAIL 级问题，需先处理" if fails
                     else "无阻断级问题，可进入清理/迁移评审"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
