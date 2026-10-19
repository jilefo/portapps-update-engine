# -*- coding: utf-8 -*-
r"""migrate_dist.py —— dist → <产品根> 逐包原子迁移（同卷 rename + 全量哈希校验）

背景
----
任务书第④步：把 39 个 `portableapps/<Pkg>/dist/<Pkg>/` 迁到 `D:\Portapps\<Pkg>\`，
要求「保留结构、先备份、计数/大小/哈希校验、修配置路径」。

为什么是 rename 而不是「复制→校验→删源」
--------------------------------------
  * D: 盘剩余 ~30 GB < dist 总体积 ~59 GB，复制方案空间不够；
  * 源（<Repo>/<Pkg>/dist）与目标（<产品根>）**同卷**，`os.rename`
    是元数据操作：零拷贝、零额外空间、原子（要么整棵树过去、要么原样不动）；
  * 比复制方案更安全：不存在「数据只有一份且正在写入」的危险窗口，
    也不需要「复制完再删源」的二次破坏动作。

安全栅（四道）
------------
  1. **进程占用检查**：源树内有运行中进程的包一律跳过（可 --force 覆盖），
     典型是 WorkBuddyPortable——当前会话的宿主就跑在它的 dist 里；
  2. **预迁移 manifest**：逐文件记录 (相对路径, 大小, SHA-256)，
     junction 记 (相对路径, 目标) 且不穿透；
  3. **包内绝对目标 junction 重定点**：目标在源树内的 junction，rename 后
     目标路径失效 → 迁移后按新路径重建（rmdir + mklink /J，不删目标数据）；
     相对目标 junction 随树迁移天然有效，不动；
  4. **迁移后复算 manifest 全等比对**：文件集合/大小/哈希逐项一致才算 PASS，
     任一不符记 FAIL 并继续其余包，最后统一报告（不静默）。

用法
----
  python migrate_dist.py status              # 每包当前位置（new/legacy/missing）
  python migrate_dist.py manifest            # 全量预迁移 manifest（只读）
  python migrate_dist.py run --pkg X --yes   # 迁移指定包（跳过被占用的）
  python migrate_dist.py run --yes           # 全量迁移
  python migrate_dist.py verify --pkg X      # 对已迁移包重算并与预迁移 manifest 比对
  python migrate_dist.py repoint --pkg X     # 重定点包内 junction（预览）
  python migrate_dist.py repoint --pkg X --yes

经验（踩过才知道）
----------------
  * **重定点必须在 rename 之后、用新路径去定位 junction**。曾按迁移前的
    绝对路径去判 `Path(...).exists()`，rename 之后源树整棵消失 → 恒为 False
    → 整段 continue，junction 一个都没被修，还误报成 WARN「已不存在」。
  * **判链接存在要用链接本身的属性（`is_junction`），不能用 `.exists()`**。
    后者跟随目标，目标悬空即返回 False，恰好跳过最需要修的那些。
  * **校验只比 junction 数量等于没比**：目标是绝对路径，换根必变；
    必须折算成树内相对路径再逐个比对，否则悬空联接照样判 PASS。

产物：manifest 存 `_shared/migration/pre/<Pkg>.json`（已在 .gitignore），
汇总写 `_shared/migration/migration_log.jsonl` 与 stdout 报告。
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths  # noqa: E402

try:
    import psutil
except ImportError:  # pragma: no cover - 进程栅降级
    psutil = None

MIG_DIR = _paths.REPO_ROOT / "_shared" / "migration"
PRE_DIR = MIG_DIR / "pre"
LOG_FILE = MIG_DIR / "migration_log.jsonl"

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


# ---------------------------------------------------------------- junction 解析
def _get_attrs(p: Path):
    a = ctypes.windll.kernel32.GetFileAttributesW(str(p))
    if a in (-1, 0xFFFFFFFF):
        return None
    return a


def is_junction(p: Path) -> bool:
    a = _get_attrs(p)
    return a is not None and bool(a & FILE_ATTRIBUTE_REPARSE_POINT)


def _read_reparse(p: Path):
    """DeviceIoControl 取 reparse 数据；失败返回 None。"""
    handle = ctypes.windll.kernel32.CreateFileW(
        str(p), 0x80000000, 7, None, 3, 0x2200000, None)
    if handle == -1:
        return None
    try:
        buf = ctypes.create_string_buffer(16384)
        n = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.DeviceIoControl(
            handle, 0x900A8, None, 0, buf, 16384, ctypes.byref(n), None)
        if not ok or n.value < 16:
            return None
        return buf.raw[: n.value]
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def junction_target(p: Path, src_root: Path) -> str | None:
    """解析 junction 目标为绝对路径（尽量）；失败返回 None。"""
    raw = _read_reparse(p)
    if raw is None or len(raw) < 16:
        return None
    tag = struct.unpack_from("<I", raw, 0)[0]
    if tag != IO_REPARSE_TAG_MOUNT_POINT:
        return None
    sub_off, sub_len = struct.unpack_from("<HH", raw, 8)
    buf = raw[16 + sub_off: 16 + sub_off + sub_len]
    tgt = buf.decode("utf-16le", "replace")
    if tgt.startswith("\\??\\"):
        tgt = tgt[4:]
    elif tgt.startswith("\\??"):
        tgt = tgt[3:]
    # 盘符相对（\Projects\...）→ 补上源树所在盘符
    if re.match(r"^\\[A-Za-z]", tgt) and not re.match(r"^[A-Za-z]:", tgt):
        tgt = src_root.drive + tgt
    return tgt


# ---------------------------------------------------------------- manifest
def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(pkg: str, root: Path) -> dict:
    files = {}
    junctions = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames):
            p = Path(dirpath) / name
            if is_junction(p):
                tgt = junction_target(p, root)
                inside = bool(tgt) and tgt.lower().startswith(str(root).lower())
                # 目标在树内时一并记下「相对根的路径」：迁移只改前缀，
                # 相对路径应保持不变。没有它，迁移后就只能比数量、
                # 比不了目标对不对（悬空 junction 照样判 PASS）。
                trel = ""
                if inside:
                    trel = tgt[len(str(root)):].lstrip("\\/").replace("\\", "/")
                junctions.append({"rel": p.relative_to(root).as_posix(),
                                  "target": tgt, "inside": inside,
                                  "target_rel": trel})
                dirnames.remove(name)
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            try:
                st = p.stat()
                files[rel] = [st.st_size, sha256_file(p)]
            except OSError as e:
                files[rel] = [-1, "unreadable:%s" % e]
    total_bytes = sum(v[0] for v in files.values() if v[0] > 0)
    return {
        "pkg": pkg,
        "root": str(root),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "algorithm": "sha256",
        "file_count": len(files),
        "total_bytes": total_bytes,
        "junction_count": len(junctions),
        "files": files,
        "junctions": junctions,
    }


def save_manifest(m: dict) -> Path:
    PRE_DIR.mkdir(parents=True, exist_ok=True)
    out = PRE_DIR / ("%s.json" % m["pkg"])
    out.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return out


def load_manifest(pkg: str) -> dict | None:
    p = PRE_DIR / ("%s.json" % pkg)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _jkey(m: dict, j: dict):
    """junction 的「跨根可比」身份。

    目标是绝对路径，换根后必然不同，所以树内目标一律折算成相对路径再比。
    老 manifest 没有 target_rel 字段（本轮才加），这里按 root 现推，
    保证对 38 份已存盘的 pre-manifest 依然可用。
    """
    rel = j["rel"]
    if not j["inside"]:
        return (rel, False, (j.get("target") or "").lower())
    tr = j.get("target_rel")
    if not tr:
        r = str(m["root"])
        t = j.get("target") or ""
        tr = (t[len(r):].lstrip("\\/").replace("\\", "/")
              if t.lower().startswith(r.lower()) else t)
    return (rel, True, tr.lower().replace("\\", "/"))


def diff_junctions(pre: dict, post: dict):
    """比对 junction，返回 (判负项, 参考项)。

    **只有「迁移时目标在树内」的 junction 才是迁移的责任**——搬树之后它
    必须还在，且仍指向新根下的同一相对路径。这条规则正是抓到本次缺陷的
    那把尺子：目标没跟着换根的 junction，inside 会从 True 变 False。

    反过来，树外目标 junction（宿主重定向、历史遗留悬空联接）是 PAL 在
    运行时创建、退出时拆除的，数量随每次冒烟起落。拿它判负只会造出一片
    假红，把真正的迁移损伤淹掉——实测 12 条全是 2026-10-17 前的历史
    悬空联接，早已被清理，与迁移无关。
    """
    bad, notes = [], []
    pj = {j["rel"]: j for j in pre["junctions"] if j["inside"]}
    q_all = {j["rel"]: j for j in post["junctions"]}
    qj = {j["rel"]: j for j in post["junctions"] if j["inside"]}
    for rel in sorted(set(pj) | set(qj)):
        a, b = pj.get(rel), qj.get(rel)
        if a and b:
            if _jkey(pre, a) != _jkey(post, b):
                bad.append("junction 迁移后目标不符: rel=%s pre=%s post=%s"
                           % (rel, _jkey(pre, a), _jkey(post, b)))
        elif a:
            # 迁移时是树内目标，现在连链接都不在了 → 必须查
            bad.append("迁移时树内 junction 现已不在: %s" % rel)
        elif b:
            notes.append("迁移后新增树内 junction: %s -> %s"
                         % (rel, b.get("target")))
    gone_out = [j["rel"] for j in pre["junctions"]
                if not j["inside"] and j["rel"] not in q_all]
    if gone_out:
        notes.append("树外目标 junction 已不在 %d 条（PAL 运行时/清理所致，"
                     "非迁移责任）" % len(gone_out))
    return bad, notes


def diff_manifest(pre: dict, post: dict) -> list:
    """返回不一致项列表；空 = 完全一致。"""
    bad = []
    pf, qf = pre["files"], post["files"]
    only_pre = sorted(set(pf) - set(qf))
    only_post = sorted(set(qf) - set(pf))
    for k in only_pre:
        bad.append("迁移后缺失: %s" % k)
    for k in only_post:
        bad.append("迁移后多出: %s" % k)
    for k in sorted(set(pf) & set(qf)):
        if pf[k] != qf[k]:
            bad.append("内容/大小不符: %s pre=%s post=%s" % (k, pf[k], qf[k]))
    if pre["junction_count"] != post["junction_count"]:
        # 数量差本身不判负：树外 junction 会随冒烟起落（见 diff_junctions 说明）
        pass
    bad_j, _ = diff_junctions(pre, post)
    bad.extend(bad_j)
    return bad


# 应用运行时会自己改写的东西。**只认路径、且要求落在 Data/ 下**——
# 程序体（App/）在运行时不该变，变了就是真问题。
# 目录级判定：**整个目录都是运行期状态**，按目录认，不逐个认文件名
# （逐个认文件名必然演变成"为了让某个文件变绿而加词条"，那就是在造假绿）
VOLATILE_DIRS = ("data/profile/", "data/settings/")
# 名称/后缀级判定：给目录级兜不住的散落缓存
VOLATILE_TOKENS = (
    "/cache2/", "/cache/", "/caches/", "/startupcache/", "/shader-cache/",
    "/safebrowsing/", "/codecache/", "/gpuache/", "/usagelogs/",
    "-shm", "-wal", ".sqlite", "settings.ini",
)
# 明确的反例：这些即使在 Data/ 下也不是运行期状态
NOT_VOLATILE_DIRS = ("data/documents", "data/notes", "data/backup")


def is_volatile(rel: str) -> bool:
    """是否属于「应用跑一趟就会变」的运行期状态。

    三条约束，缺一就会变成新的假绿：
      1. 必须落在 `Data/` 下——`App/` 是程序体，运行时不该变；
      2. 命中目录级（整个 profile/settings 目录）或名称级（缓存/sqlite）特征；
      3. 不在反例目录里（用户文档不算运行期状态）。

    目录级优先于逐个文件名：ZenBrowser 的 `broadcast-listeners.json`
    就是逐个枚举认不出来的（认不出 → 判负 → 逼着人去加词条 → 造假绿）。
    按「整个 Data/profile/ 都是浏览器 profile」来认，一条规则覆盖全部。
    """
    low = rel.lower().replace("\\", "/")
    if not low.startswith("data/"):
        return False
    if any(d in low for d in NOT_VOLATILE_DIRS):
        return False
    if low.startswith(VOLATILE_DIRS) or any(d in low for d in VOLATILE_DIRS):
        return True
    return any(t in low for t in VOLATILE_TOKENS)


def classify_diff(bad: list):
    """把差异分成「真·判负」与「运行期状态」，返回 (hard, notes)。

    为什么要分：`verify` 的快照把 `Data/` 下的运行期状态也拍了进去，
    于是**只要跑过一次应用就会 FAIL**（实测冒烟期间 ZenBrowser 40 项、
    全是 `Data/profile/` 的浏览器缓存与 prefs）。不分的话这道门禁会变成
    常红，而常红的门禁跟假绿一样会被人忽略。

    怎么保证不滑向假绿：
      * **「迁移后缺失」一律判负**——文件少了永远是数据丢失，不接受
        "可能是应用自己删的"这种解释（缓存清理另说，但要先看清楚）；
      * 只有同时满足「在 Data/ 下」+「命中易变特征」才降级为备注；
      * 降级了也**要报数量**，让人看见分类确实发生了。
    """
    hard, notes = [], []
    for line in bad:
        if line.startswith("迁移后缺失:"):
            hard.append(line)              # 缺失永不降级
            continue
        body = line.split(": ", 1)[1]
        rel = body.split(" pre=")[0]
        if is_volatile(rel):
            notes.append(line)
        else:
            hard.append(line)
    return hard, notes


# ---------------------------------------------------------------- 进程栅
def procs_in(root: Path) -> list:
    """可执行路径/cwd/打开文件位于 root 内的进程。psutil 缺失时返回 []。"""
    hits = []
    if psutil is None:
        return hits
    r = str(root).lower()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            exe = (p.info.get("name") or "")
            paths = []
            try:
                paths.append(p.exe())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
            try:
                paths.append(p.cwd())
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
            if any(str(x).lower().startswith(r) for x in paths):
                hits.append((p.info["pid"], exe))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return hits


# ---------------------------------------------------------------- 迁移动作
def replace_root_prefix(target: str, old_root, new_root) -> str | None:
    """把 target 里的 old_root 前缀换成 new_root（Windows 路径大小写不敏感）。

    为什么不能直接用 `str.replace`：junction 目标可能被写成小写盘符
    （实测 ComatePortable 的 `d:\\Projects\\...`），而 old_root 是大写 `D:\\...`，
    直接 replace 会**静默不匹配**——此时 mklink 依然返回 0（junction 允许指向
    不存在的目标），工具会报告"重定点成功"而目标其实还指着已迁走的旧路径。
    这类静默失败正是本工具要防的东西，故单独抽函数并显式返回 None。
    """
    lo = str(old_root).lower()
    i = str(target).lower().find(lo)
    if i == -1:
        return None
    return str(target)[:i] + str(new_root) + str(target)[i + len(lo):]


def repoint_junction(junc: Path, old_target: str, old_root: Path,
                     new_root: Path) -> bool:
    """rmdir 旧 junction（不动目标数据），按新根重建。

    三道校验，任一不满足就报 FAIL（不静默）：
      1. 新目标**必须真实存在**——拒绝建立指向空路径的悬空 junction；
      2. mklink 返回 0 之后**回读** junction 目标并与预期比对
         （mklink 对不存在的目标也返回 0，只看返回码会漏）；
      3. 重建失败时**回滚**到旧目标，别把 junction 留在"已删除"状态。
    """
    import subprocess
    new_target = replace_root_prefix(old_target, old_root, new_root)
    if new_target is None:
        print("    [FAIL] 目标不含源树前缀，无法重定点: %s" % old_target)
        return False
    if not os.path.isdir(new_target):
        print("    [FAIL] 新目标不存在（拒绝建悬空 junction）: %s" % new_target)
        return False

    def _mklink(tgt: str) -> bool:
        # 中文 Windows 的 cmd 输出是 GBK（实测 0xb4 开头字节会让 utf-8 解码
        # 在后台线程抛 UnicodeDecodeError）。显式指定编码并容错，
        # 否则真实报错会被解码异常盖掉、只看到一堆看不懂的 traceback。
        cp = subprocess.run(["cmd", "/c", "mklink", "/J", str(junc), tgt],
                            capture_output=True, text=True,
                            encoding="gbk", errors="replace")
        if cp.returncode != 0:
            print("       mklink 输出: %s" % (cp.stderr or cp.stdout or "").strip())
        return cp.returncode == 0

    try:
        os.rmdir(str(junc))           # junction 删除不触及目标内容
    except OSError as e:
        print("    [FAIL] 删旧 junction 失败 %s: %s" % (junc, e))
        return False
    if not _mklink(new_target):
        print("    [FAIL] 重建 junction 失败: %s -> %s" % (junc, new_target))
        _mklink(old_target)           # 尽力回滚，别留下"已删除"状态
        return False
    # 回读校验：mklink 成功 ≠ 目标正确
    actual = junction_target(junc, Path(new_root))
    if not actual or actual.lower() != new_target.lower():
        print("    [FAIL] 目标回读不一致: 预期 %s 实际 %s"
              % (new_target, actual))
        os.rmdir(str(junc))
        _mklink(old_target)
        return False
    print("    [重定点] %s -> %s" % (junc.name, new_target))
    return True


def migrate_one(pkg: str, force: bool = False) -> dict:
    rec = {"pkg": pkg, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    src = _paths.product_dir(pkg)
    if not src.is_dir():
        rec.update(status="SKIP", reason="产品目录不存在: %s" % src)
        return rec
    # 已经在产品根（new 布局）？
    if _paths.product_tree_in_use(pkg) == "new":
        rec.update(status="SKIP", reason="已在产品根: %s" % src)
        return rec
    dst = _paths.product_root() / pkg
    if dst.exists():
        rec.update(status="FAIL", reason="目标已存在: %s" % dst)
        return rec

    # 1) 进程栅
    running = procs_in(src)
    if running and not force:
        rec.update(status="SKIP",
                   reason="源树有运行中进程（共 %d 个，如 %s）；加 --force 可强迁"
                          % (len(running), running[:3]))
        return rec

    # 2) dist 根额外产物（如 sbom.spdx.json）→ 搬到产品根并按包命名
    extras = []
    dist_root = _paths.repo_dist_parent(pkg)      # <Pkg>/dist
    if dist_root.is_dir():
        for item in sorted(dist_root.iterdir()):
            if item.name != pkg:
                extras.append(item)

    # 3) 预迁移 manifest
    pre = build_manifest(pkg, src)
    save_manifest(pre)
    rec["pre"] = {"files": pre["file_count"], "bytes": pre["total_bytes"],
                  "junctions": pre["junction_count"]}

    # 4) 包内绝对目标 junction 清单（迁移后重定点）
    #    存 rel 而非绝对路径：第 5 步 rename 之后 src 整棵就不在了，
    #    拿迁移前的绝对路径去判存在性必然是 False（曾让本段全程 continue，
    #    junction 一个都没被重定点，留下指向旧路径的悬空联接）。
    inside_juncs = [(j["rel"], j["target"])
                    for j in pre["junctions"] if j["inside"] and j["target"]]

    # 5) 原子 rename
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(str(src), str(dst))
    except OSError as e:
        rec.update(status="FAIL", reason="rename 失败: %s" % e)
        return rec
    rec["dst"] = str(dst)

    # 6) 重定点包内 junction
    if inside_juncs:
        ok_all = True
        for rel, tgt in inside_juncs:
            jp = dst / rel
            # 必须判「链接本身在不在」，不能用 .exists()——后者会跟随目标，
            # 目标悬空时返回 False，恰好跳过我们最需要修的那些 junction。
            if not is_junction(jp):
                print("    [WARN] junction 链接本身已不在: %s" % jp)
                continue
            if not repoint_junction(jp, tgt, src, dst):
                ok_all = False
        rec["junctions_repointed"] = len(inside_juncs)
        if not ok_all:
            rec["status"] = "WARN"

    # 7) 搬运 dist 根额外产物
    for item in extras:
        try:
            if item.is_dir():
                shutil.move(str(item), str(dst.parent / (pkg + "-" + item.name)))
            else:
                shutil.move(str(item), str(dst.parent /
                                           (pkg + "-" + item.name)))
            rec.setdefault("extras_moved", []).append(item.name)
        except OSError as e:
            print("    [WARN] 额外产物搬运失败 %s: %s" % (item, e))

    # 8) 迁移后复算 + 全等比对
    post = build_manifest(pkg, dst)
    bad = diff_manifest(pre, post)
    rec["post"] = {"files": post["file_count"], "bytes": post["total_bytes"],
                   "junctions": post["junction_count"]}
    if bad:
        rec["status"] = "FAIL"
        rec["diff"] = bad[:20]
        return rec
    if rec.get("status") != "WARN":
        rec["status"] = "PASS"

    # 9) 清理空的 dist 目录
    try:
        if dist_root.is_dir() and not any(dist_root.iterdir()):
            dist_root.rmdir()
            rec["dist_removed"] = True
    except OSError:
        pass
    return rec


def log(rec: dict) -> None:
    MIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def cmd_status(_args) -> int:
    root = _paths.product_root()
    print("产品根: %s（来源 %s）" % (root, _paths.product_root_source()))
    n_new = n_legacy = n_missing = 0
    for pkg in _paths.packages():
        t = _paths.product_tree_in_use(pkg)
        n_new += t == "new"
        n_legacy += t == "legacy"
        n_missing += t == "missing"
        if t != "new":
            print("  %-26s %s" % (pkg, t))
    print("合计 %d 包：新产品树 %d / 仓库内旧 dist %d / 缺失 %d"
          % (len(_paths.packages()), n_new, n_legacy, n_missing))
    return 0


def cmd_manifest(args) -> int:
    total_b = 0
    total_f = 0
    total_j = 0
    for pkg in _paths.packages():
        d = _paths.product_dir(pkg)
        if not d.is_dir():
            print("  %-26s SKIP（目录不存在）" % pkg)
            continue
        m = build_manifest(pkg, d)
        save_manifest(m)
        total_b += m["total_bytes"]
        total_f += m["file_count"]
        total_j += m["junction_count"]
        print("  %-26s %7d 文件  %10.2f MB  junction %d"
              % (pkg, m["file_count"], m["total_bytes"] / 1048576,
                 m["junction_count"]))
    print("manifest 完成：%d 文件 / %.2f GB / %d junction → %s"
          % (total_f, total_b / 1073741824, total_j, PRE_DIR))
    return 0


def cmd_run(args) -> int:
    pkgs = [args.pkg] if args.pkg else _paths.packages()
    summary = {"PASS": 0, "FAIL": 0, "SKIP": 0, "WARN": 0}
    for pkg in pkgs:
        print("[迁移] %s ..." % pkg)
        rec = migrate_one(pkg, force=args.force)
        log(rec)
        summary[rec["status"]] = summary.get(rec["status"], 0) + 1
        print("  => %s %s" % (rec["status"], rec.get("reason", "")))
        if rec["status"] == "FAIL" and rec.get("diff"):
            for d in rec["diff"][:5]:
                print("     " + d)
    print("\n汇总: " + " / ".join("%s %d" % kv for kv in summary.items()))
    return 0 if summary.get("FAIL", 0) == 0 else 1


def cmd_verify(args) -> int:
    pkgs = [args.pkg] if args.pkg else _paths.packages()
    bad_total = 0
    for pkg in pkgs:
        pre = load_manifest(pkg)
        d = _paths.product_dir(pkg)
        if pre is None or not d.is_dir():
            print("  %-26s SKIP（无 manifest 或目录不存在）" % pkg)
            continue
        post = build_manifest(pkg, d)
        raw = diff_manifest(pre, post)
        hard, vol = classify_diff(raw)
        _, notes = diff_junctions(pre, post)
        if hard:
            bad_total += len(hard)
            print("  %-26s FAIL (%d 项需查)" % (pkg, len(hard)))
            for x in hard[:5]:
                print("     " + x)
        else:
            print("  %-26s PASS（%d 文件 / %.2f MB 全等）"
                  % (pkg, post["file_count"], post["total_bytes"] / 1048576))
        # 分类结果必须报出来，否则「悄悄放过 40 项」和「真的没有问题」长一样
        if vol:
            print("       [运行期] %d 项易变状态变化（应用跑过的正常产物，"
                  "不计入判定）" % len(vol))
            for x in vol[:2]:
                print("         %s" % x.split(": ", 1)[1].split(" pre=")[0])
        for n in notes:
            print("       [备注] %s" % n)
    return 0 if bad_total == 0 else 1


def cmd_repoint(args) -> int:
    """按 pre-manifest 把包内 junction 重新指向当前产品根。

    幂等：目标已经正确就跳过，不需要「先破坏再修」。
    用途有二：① 修历史损伤（迁移时因缺陷没被重定点的悬空联接）；
    ② 独立于 run 再跑一遍做交叉确认。
    """
    pkgs = [args.pkg] if args.pkg else _paths.packages()
    n_fix = n_ok = n_skip = n_fail = 0
    for pkg in pkgs:
        pre = load_manifest(pkg)
        dst = _paths.product_dir(pkg)
        if pre is None or not dst.is_dir():
            n_skip += 1
            continue
        src = Path(pre["root"])
        for j in pre["junctions"]:
            if not (j["inside"] and j["target"]):
                continue
            jp = dst / j["rel"]
            if not is_junction(jp):
                print("  %-26s SKIP 链接不在: %s" % (pkg, j["rel"]))
                n_skip += 1
                continue
            want = replace_root_prefix(j["target"], src, dst)
            if want is None:
                print("  %-26s FAIL 目标不含源树前缀: %s"
                      % (pkg, j["target"]))
                n_fail += 1
                continue
            actual = junction_target(jp, dst)
            if actual and actual.lower() == want.lower():
                n_ok += 1                      # 已经正确，不动
                continue
            if not args.yes:
                print("  %-26s 待修 %s\n      %s -> %s"
                      % (pkg, j["rel"], actual, want))
                n_fix += 1
                continue
            if repoint_junction(jp, j["target"], src, dst):
                print("  %-26s 已修 %s" % (pkg, j["rel"]))
                n_fix += 1
            else:
                n_fail += 1
    tag = "（预览，加 --yes 执行）" if not args.yes else ""
    print("\n重定点汇总%s: 修复 %d / 已正确 %d / 跳过 %d / 失败 %d"
          % (tag, n_fix, n_ok, n_skip, n_fail))
    return 1 if n_fail else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("manifest")
    p_rep = sub.add_parser("repoint",
                           help="按 pre-manifest 重定点包内 junction（幂等）")
    p_rep.add_argument("--pkg", default=None)
    p_rep.add_argument("--yes", action="store_true", help="确认执行")
    p_run = sub.add_parser("run")
    p_run.add_argument("--pkg", default=None)
    p_run.add_argument("--force", action="store_true",
                       help="忽略进程占用栅（危险，仅应急）")
    p_run.add_argument("--yes", action="store_true", help="确认执行")
    p_ver = sub.add_parser("verify")
    p_ver.add_argument("--pkg", default=None)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd == "run" and not args.yes:
        print("[拒绝] run 需要 --yes 确认（迁移是不可逆原子操作）")
        return 2
    return {"status": cmd_status, "manifest": cmd_manifest,
            "run": cmd_run, "verify": cmd_verify,
            "repoint": cmd_repoint}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
