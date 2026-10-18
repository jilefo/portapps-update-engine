# -*- coding: utf-8 -*-
r"""FSCapturePortable 便携版 —— 更新脚本

本文件由 `_shared/tools/gen_update_strategies.py` 自动生成，
改策略请改生成器里的 SPEC 再重新生成，不要直接手改本文件。

源类型   : manual
下载页   : https://www.faststone.org/FSCaptureDetail.htm
包类型   : zip
检查周期 : monthly
程序目录 : App\FSCapture
入口     : FSCapture\FSCapture.exe
生成时版本: 11.3.0.0

说明：原配置走蓝奏云文件夹；实测页面无版本号且需二次签名跳转

用法（在本目录下执行）：
  python update.py --check                 只检测，只读，最安全
  python update.py --update                演练全流程（不落地）
  python update.py --update --execute      真正下载并替换
  python update.py --ingest <安装包> --execute   人工下载后接管
  python update.py --rollback              回滚到上一备份
  python update.py --check --json          机器可读输出

安全设计：默认 dry-run；自动备份到
`_shared/update/_backups/FSCapturePortable/`；Data/ 目录永不触碰；失败自动回滚。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------- 路径推导
# 布局（2026-10-18 迁移后）：
#   HERE        = <产品根>/<Pkg>      便携包目录（= EXEDIR）
#   HERE.parent = <产品根>
# 迁移前是 <Repo>/<Pkg>/dist/<Pkg>，上溯三级能到仓库根；迁移后本脚本在
# 仓库外，固定级数上溯会推出 D:\ 这种错误根。故改为**探测式**：
#   1) 环境变量 PORTABLEAPPS_REPO（迁移后显式告知仓库位置）
#   2) 从 HERE 逐级上溯，找同时含 _shared/update 与 _shared/scripts 的目录
#   3) 都找不到 → None：缓存/备份退到临时目录，结构校验明确跳过
HERE = Path(__file__).resolve().parent
PKG = HERE.name
PKG_ROOT = HERE.parent


def _find_repo_root():
    env = os.environ.get("PORTABLEAPPS_REPO")
    if env and (Path(env) / "_shared" / "scripts").is_dir():
        return Path(env)
    for p in [HERE] + list(HERE.parents):
        if (p / "_shared" / "scripts").is_dir() and (p / "_shared" / "update").is_dir():
            return p
    return None


REPO_ROOT = _find_repo_root()

# 目录**按需创建**，不在导入时 mkdir —— 否则每跑一次 --check 就给每个包
# 各建一个空目录，纯噪音。真正要写的时候再建（见 download / install）。
# 仓库找不到时（单拷走 / 迁移后未设 PORTABLEAPPS_REPO）退到临时目录，
# 保证脚本永远能跑，只是缓存不跨机器共享。
try:
    if REPO_ROOT is None:
        raise OSError("仓库根未定位（脱离仓库运行）")
    _probe = REPO_ROOT / "_shared" / "update"
    _probe.mkdir(parents=True, exist_ok=True)
    CACHE = _probe / "_cache" / PKG
    BACKUP_ROOT = _probe / "_backups" / PKG
except OSError:                                     # 单拷走、无写权限、脱离仓库
    import tempfile
    _t = Path(tempfile.gettempdir()) / "portable-update" / PKG
    CACHE = _t / "_cache"
    BACKUP_ROOT = _t / "_backups"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def log(msg=""):
    print(msg, flush=True)


# ---------------------------------------------------------------- 版本规范化
def norm_version(v):
    r"""规范成 4 段整数元组。

    真实陷阱：appinfo.ini 里是 `2.1.0.0`（PAL 要求 4 段），上游 tag 是
    `v2.1.0`，Zen 这种还带 `1.23.3b`。直接字符串比会得出"永远有更新"
    或"永远没更新"的错结论。
    """
    if not v:
        return (0, 0, 0, 0)
    s = str(v).strip()
    s = re.sub(r"^[vV]", "", s)
    s = re.sub(r"[bB]$", "", s)          # 1.23.3b -> 1.23.3
    s = s.split("-")[0].split("+")[0]
    parts = []
    for seg in s.split(".")[:4]:
        m = re.match(r"\d+", seg)
        parts.append(int(m.group()) if m else 0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def cmp_version(a, b):
    na, nb = norm_version(a), norm_version(b)
    return (na > nb) - (na < nb)


# ---------------------------------------------------------------- 基类
class Strategy:
    pkg = PKG
    source_type = "manual"
    app_subdir = ""          # 由文件末尾的 S 类按本包实际结构覆盖
    entry_exe = ""
    package_type = "unknown"
    schedule = "monthly"
    note = ""
    drop_paths = []      # 上游包里要剔除的顶层名（如自带的 Data/）
    disable_exe = []     # 要改名的自带更新器文件名
    strip_root = ""      # 真正的程序在这层子目录里（如 Zen 安装器的 core/）

    _last_backup = None
    _new_local_version = None

    def fetch_latest(self, timeout=15):
        return None, None, "无在线版本源"

    # ---- 读当前版本 ----
    def appinfo_path(self):
        p = HERE / "App" / "AppInfo" / "appinfo.ini"
        return p if p.is_file() else None

    def current_version(self):
        p = self.appinfo_path()
        if not p:
            return None
        raw = p.read_bytes()
        enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
        try:
            t = raw.decode(enc)
        except UnicodeDecodeError:
            t = raw.decode("gb18030", errors="replace")
        m = re.search(r"(?m)^PackageVersion\s*=\s*(.+)$", t)
        return m.group(1).strip() if m else None

    def local_version(self):
        r"""从已安装文件读真实版本（manual 源也能知道"现在装的是什么"）。"""
        if not self.app_subdir:
            return None
        root = HERE / "App" / self.app_subdir
        for rel in ("resources/app/package.json",
                    "resources/app.asar.unpacked/package.json",
                    "package.json"):
            p = root / rel
            if p.is_file():
                try:
                    d = json.loads(p.read_text(encoding="utf-8",
                                               errors="replace"))
                    if d.get("version"):
                        return str(d["version"])
                except Exception:                      # noqa: BLE001
                    pass
        exe = None
        if self.entry_exe:
            cand = HERE / self.entry_exe.replace("\\", "/")
            if cand.is_file():
                exe = cand
        if exe is None and root.is_dir():
            for p in sorted(root.glob("*.exe"))[:200]:
                if p.is_file():
                    exe = p
                    break
        if exe:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-Item -LiteralPath '%s').VersionInfo.ProductVersion"
                     % str(exe)], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=30)
                v = (r.stdout or "").strip()
                if re.match(r"^\d+(\.\d+){1,3}$", v):
                    return v
            except Exception:                          # noqa: BLE001
                pass
        return None

    # ---- 上次成功结果的兜底缓存 ----
    def _last_check_path(self):
        return CACHE / "_last_check.json"

    def _load_last_check(self):
        p = self._last_check_path()
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:                          # noqa: BLE001
                return None
        return None

    def _save_last_check(self, r):
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            self._last_check_path().write_text(
                json.dumps(r, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ---- 检测 ----
    def check(self):
        cur = self.current_version()
        try:
            latest, url, note = self.fetch_latest()
        except Exception as e:                         # noqa: BLE001
            # 网络抖动 / GitHub 限流是**临时故障**，不是"这个包坏了"。
            # 直接报 ERR 会让人以为策略写错了，所以退回上次成功的结果。
            prev = self._load_last_check()
            if prev:
                prev["current"] = cur
                prev["status"] = "CACHED"
                prev["msg"] = "本次取新失败（%s），显示上次成功结果" % str(e)[:60]
                return prev
            return dict(pkg=self.pkg, source=self.source_type, current=cur,
                        latest=None, has_update=None, status="ERR",
                        msg=str(e)[:120], url=None)
        if latest is None:
            return dict(pkg=self.pkg, source=self.source_type, current=cur,
                        latest=None, has_update=None, status="MANUAL",
                        msg=note or "需人工下载", url=None)
        c = cmp_version(latest, cur) if cur else 1
        r = dict(pkg=self.pkg, source=self.source_type, current=cur,
                 latest=latest, has_update=(c > 0),
                 status="UPDATE" if c > 0 else "LATEST",
                 msg=note or "", url=url)
        self._save_last_check(r)
        return r

    # ---- 下载 ----
    def download(self, url, dest=None):
        import requests
        name = url.split("?")[0].rsplit("/", 1)[-1] or "download.bin"
        CACHE.mkdir(parents=True, exist_ok=True)
        dest = Path(dest) if dest else CACHE / name
        if dest.is_file() and dest.stat().st_size > 0:
            log("  复用缓存: %s" % dest.name)
            return dest
        # 先写 .part 再改名：中断不会留下"看起来下完了"的半截包
        part = dest.with_name(dest.name + ".part")
        if part.is_file():
            part.unlink()
        log("  下载 -> %s" % dest.name)
        r = requests.get(url, headers={"User-Agent": UA}, stream=True,
                         timeout=60)
        r.raise_for_status()
        total = 0
        with open(part, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                total += len(chunk)
        exp = r.headers.get("content-length")
        if exp and int(exp) != total:
            part.unlink()
            raise RuntimeError("下载不完整 %d/%s 字节，已丢弃" % (total, exp))
        part.replace(dest)
        log("  完成 %.1fMB" % (dest.stat().st_size / 1024 / 1024))
        return dest

    # ---- 解包 ----
    def unpack(self, archive, dst):
        dst.mkdir(parents=True, exist_ok=True)
        pt = (self.package_type or "unknown").lower()
        if pt == "zip":
            with zipfile.ZipFile(archive) as z:
                z.extractall(dst)
            return True
        if pt in ("7z", "inno", "7z_sfx", "electron_installer", "nsis",
                  "msi"):
            return self._unpack_7z(archive, dst)
        log("  [跳过解包] package_type=%s 需人工处理" % pt)
        return False

    def _7z_candidates(self):
        return [shutil.which("7z"), shutil.which("7za"),
                shutil.which("7zz"),
                r"C:\Program Files\7-Zip\7z.exe",
                r"C:\Program Files (x86)\7-Zip\7z.exe"]

    def _unpack_7z(self, archive, dst):
        r"""逐个试用 7-Zip 候选，**拿真实文件试**，第一个解出来的就用。

        踩过：`shutil.which("7z")` 命中的 `<本机工具目录>/tools\7z.EXE`
        旁边缺 `7z.dll`（只有 `7za.dll`），于是——
          * `7z` 无参数 → 正常打印帮助、rc=0（**看起来是好的**）
          * `7z x 真包`  → `Load Error: 7z.dll` + `Can't open as archive`、rc=2

        它排在 `C:\Program Files\7-Zip\7z.exe` 前面，结果所有
        NSIS / Inno / 7z 自解压包**静默解包失败**，表现为"更新没反应"。
        所以用"无参数跑一次"做健康检查是**骗人的**，必须拿真包试。
        """
        last = ""
        tried = 0
        for c in self._7z_candidates():
            if not c or not Path(c).is_file():
                continue
            tried += 1
            try:
                r = subprocess.run([c, "x", str(archive), "-y",
                                    "-o%s" % dst], capture_output=True,
                                   timeout=1800)
            except Exception as e:                     # noqa: BLE001
                last = str(e)[:200]
                continue
            if r.returncode == 0:
                return True
            last = (((r.stdout or b"") + (r.stderr or b""))
                    .decode("utf-8", "replace").strip()[-300:])
            log("  7-Zip %s 解包失败（rc=%d），换下一个候选"
                % (Path(c).name, r.returncode))
        if not tried:
            log("  [需要 7-Zip] 无法解包 %s；请在 PATH 里放一个可用的 7z.exe，"
                "或安装到 C:\\Program Files\\7-Zip\\" % self.package_type)
        else:
            log("  [解包失败] 所有 7-Zip 候选都失败：\n%s" % last)
        return False

    def post_unpack(self, root):
        r"""解包后、替换前的「再便携化」——这一步是便携版能不能活下来的关键。

        0. 进入真正的程序目录（Zen 这类 Mozilla 安装器解出来是
           `core/` + `setup.exe`，正主在 `core/` 里）。
        1. 剥掉单层外壳目录（zip 常解出 `SoloMD_5.0.3/...`，多一层就找不到入口）。
        2. 剔除上游自带的 `Data/`——PAL 用 `[Environment]` 把数据重定向到
           `<产品目录>/Data/`，用上游的会把用户数据写进 App 里。
        3. 禁用上游自带更新器——`update_installer.exe` / `updater.exe` /
           `zUpdater.exe` 一旦跑起来，会把便携版改写成安装版。
        """
        if self.strip_root:
            p = root / self.strip_root
            if p.is_dir():
                log("  进入程序子目录 %s/" % self.strip_root)
                root = p
            else:
                log("  [警告] strip_root=%s 不存在，按原样继续"
                    % self.strip_root)
        try:
            entries = list(root.iterdir())
        except FileNotFoundError:
            return root
        if len(entries) == 1 and entries[0].is_dir():
            log("  剥掉外壳目录 %s" % entries[0].name)
            return entries[0]
        for name in (self.drop_paths or []):
            p = root / name
            if p.exists():
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                log("  剔除上游 %s（PAL 自己管理，不能用上游的）" % name)
        for base in (self.disable_exe or []):
            for p in list(root.glob(base)) + list(root.glob("*/" + base)):
                if p.is_file():
                    p.rename(p.with_name(p.name + ".disabled-by-engine"))
                    log("  禁用自带更新器 %s" % base)
                    break
        return root

    # ---- 替换安装 ----
    def install(self, src_dir, execute=False):
        """只替换 App/<程序子目录>；Data/ 与 AppInfo/ 在别的路径，天然不被碰。"""
        if not self.app_subdir:
            log("  [中止] 未配置 app_subdir，不敢盲替换")
            return False
        target = HERE / "App" / self.app_subdir
        if not target.is_dir():
            log("  [中止] 目标程序目录不存在: %s" % target)
            return False
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bak = BACKUP_ROOT / ("%s-%s" % (self.app_subdir, stamp))
        log("  备份 %s -> %s" % (target, bak))
        self.prune_backups(keep=3)
        if not execute:
            log("  [DRY-RUN] 未执行（加 --execute 落地）")
            return True
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, bak)
        # 把 appinfo.ini 一并存进备份：回滚时版本号也要跟着退回去，
        # 否则出现"文件是旧的、版本号是新的"这种对不上的状态。
        ai = self.appinfo_path()
        if ai:
            (bak / "_appinfo").mkdir(exist_ok=True)
            shutil.copy2(ai, bak / "_appinfo" / "appinfo.ini")
        self._last_backup = bak
        try:
            shutil.rmtree(target)
            shutil.copytree(src_dir, target)
            log("  已替换 %s" % target)
            self._new_local_version = self.local_version()
            return True
        except Exception as e:                         # noqa: BLE001
            log("  [失败回滚] %s" % e)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(bak, target)
            return False

    def prune_backups(self, keep=3):
        r"""只保留最近 keep 份备份。

        不清理的话备份会无限增长：一次 SublimeText 备份就是 172MB，
        重装几次就吃掉几个 G。这里在**新建备份之前**调用，保证任何
        时刻磁盘上都还留着 keep 份可回滚点。
        """
        if not BACKUP_ROOT.is_dir():
            return
        cands = sorted((d for d in BACKUP_ROOT.iterdir()
                        if d.is_dir() and d.name.startswith(self.app_subdir)),
                       key=lambda d: d.name)
        for old in cands[:max(0, len(cands) - keep + 1)]:
            shutil.rmtree(old, ignore_errors=True)
            log("  清理旧备份 %s" % old.name)

    def rollback(self, backup=None):
        r"""回滚。

        `--rollback` 是新起一次进程跑的，此时 `self._last_backup` 一定是
        None（那是上一次进程的内存状态）。所以这里改成去备份目录里找
        最新的一个 —— 这个坑不修的话回滚功能等于不存在。
        """
        bak = Path(backup) if backup else None
        if bak is None and BACKUP_ROOT.is_dir():
            cands = [d for d in BACKUP_ROOT.iterdir()
                     if d.is_dir() and d.name.startswith(self.app_subdir)]
            bak = max(cands, key=lambda d: d.name) if cands else None
        if not bak or not bak.is_dir():
            log("  没有可回滚的备份（%s）" % BACKUP_ROOT)
            return False
        target = HERE / "App" / self.app_subdir
        if target.exists():
            shutil.rmtree(target)
        # 备份里混放了 _appinfo/，拷回程序目录时要排除掉
        shutil.copytree(bak, target,
                        ignore=shutil.ignore_patterns("_appinfo"))
        ai = bak / "_appinfo" / "appinfo.ini"
        if ai.is_file():
            dst = self.appinfo_path()
            if dst:
                shutil.copy2(ai, dst)
        log("  已回滚到 %s" % bak.name)
        return True

    # ---- 回写版本号 ----
    def bump_version(self, new_ver, execute=False):
        p = self.appinfo_path()
        if not p:
            return False
        raw = p.read_bytes()
        enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
        t = raw.decode(enc)
        v4 = ".".join(str(x) for x in norm_version(new_ver))
        t2 = re.sub(r"(?m)^PackageVersion\s*=.*$", "PackageVersion=%s" % v4, t)
        if re.search(r"(?m)^DisplayVersion\s*=", t2):
            t2 = re.sub(r"(?m)^DisplayVersion\s*=.*$",
                        "DisplayVersion=%s" % v4, t2)
        if t2 == t:
            log("  版本号已是 %s，无需回写" % v4)
            return True
        if not execute:
            log("  [DRY-RUN] 将回写版本号 %s" % v4)
            return True
        # 备份放到备份区，不要落在 AppInfo/ 里 —— 那是要随包发出去的目录，
        # 每更新一次就多一个 .bak，属于污染产物。
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bd = BACKUP_ROOT / ("_appinfo-%s" % stamp)
        bd.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, bd / "appinfo.ini")
        p.write_bytes(t2.encode(enc))
        log("  版本已回写 %s（备份 %s）" % (v4, bd.name))
        return True

    # ---- 冒烟验证 ----
    def verify(self):
        if REPO_ROOT is None:
            log("  [跳过结构校验] 未定位仓库根（迁移后在仓库外运行）；"
                "设环境变量 PORTABLEAPPS_REPO=<仓库路径> 可恢复")
            return None
        t = REPO_ROOT / "_shared" / "scripts" / "test_structure.py"
        if not t.is_file():
            log("  [跳过] 未找到结构校验脚本（可能已脱离仓库）")
            return None
        r = subprocess.run([sys.executable, str(t), self.pkg],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
        if r.returncode != 0:
            log("  %s" % (r.stdout or "").strip()[-300:])
        return r.returncode == 0

    # ---- 主流程 ----
    def update(self, execute=False):
        log("=" * 66)
        log("%s  源=%s  周期=%s" % (self.pkg, self.source_type, self.schedule))
        log("=" * 66)
        r = self.check()
        log("  当前=%s  最新=%s  -> %s" % (r["current"], r["latest"],
                                           r["status"]))
        if r["status"] != "UPDATE":
            log("  无需更新")
            return r
        if not r.get("url"):
            log("  有新版但无直链，请人工下载后用 --ingest 接管")
            return r
        arch = self.download(r["url"])
        tmp = CACHE / "_unpack"
        if tmp.exists():
            shutil.rmtree(tmp)
        if not self.unpack(arch, tmp):
            return r
        src = self.post_unpack(tmp)
        if not self.install(src, execute=execute):
            return r
        self.bump_version(r["latest"], execute=execute)
        if execute:
            # 落地后清掉解包临时目录；dry-run 时保留，方便人肉检查解出来对不对
            self.cleanup_tmp(tmp)
            ok = self.verify()
            log("  结构校验：%s" % ("PASS" if ok else "FAIL（可 --rollback）"))
        return r

    @staticmethod
    def cleanup_tmp(tmp):
        shutil.rmtree(tmp, ignore_errors=True)

    def ingest(self, file_path, execute=False, ver=None):
        """人工下载新版后接管：解包 -> 再便携化 -> 替换 -> 回写 -> 验证"""
        p = Path(file_path)
        if not p.is_file():
            log("  文件不存在: %s" % p)
            return False
        log("接管人工下载: %s" % p.name)
        tmp = CACHE / "_ingest"
        if tmp.exists():
            shutil.rmtree(tmp)
        if not self.unpack(p, tmp):
            return False
        src = self.post_unpack(tmp)
        if not self.install(src, execute=execute):
            return False
        if not ver:
            ver = self._new_local_version
        if not ver and execute:
            try:
                ver = input("  请输入新版本号（回车跳过）: ").strip()
            except EOFError:
                ver = ""
        if ver:
            self.bump_version(ver, execute=execute)
        if execute:
            self.cleanup_tmp(tmp)
            log("  结构校验：%s" % ("PASS" if self.verify() else "FAIL"))
        return True


# ---------------------------------------------------------------- 源类型
class GithubReleases(Strategy):
    source_type = "github_releases"
    repo = ""
    asset_regex = r".*"

    def fetch_latest(self, timeout=15):
        import requests
        u = "https://api.github.com/repos/%s/releases/latest" % self.repo
        h = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
        # 未认证的 GitHub API 只有 60 次/小时（按 IP 计），4 个包连着跑几轮就
        # 打满了。带 token 可以到 5000 次/小时，CI 里务必配。
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if tok:
            h["Authorization"] = "Bearer %s" % tok
        r = requests.get(u, headers=h, timeout=timeout)
        if r.status_code == 403:
            raise RuntimeError(
                "GitHub HTTP 403：限流（未认证 60 次/小时"
                "，设置环境变量 GITHUB_TOKEN 可到 5000 次/小时）")
        if r.status_code != 200:
            raise RuntimeError("GitHub HTTP %d" % r.status_code)
        d = r.json()
        tag = d.get("tag_name") or ""
        url = None
        for a in d.get("assets", []):
            if re.search(self.asset_regex, a.get("name", "")):
                url = a.get("browser_download_url")
                break
        note = "" if url else "assets 未命中 %s" % self.asset_regex
        return tag, url, note


class ApiJson(Strategy):
    """version_field / url_field 支持点号路径，如 versions.Windows_x64.version_number"""
    source_type = "api"
    url = ""
    params = None
    version_field = "version"
    url_field = "downloadUrl"
    version_regex = ""

    @staticmethod
    def _dig(d, path):
        cur = d
        for seg in str(path).split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(seg)
            if cur is None:
                return None
        return cur

    def fetch_latest(self, timeout=15):
        import requests
        r = requests.get(self.url, params=self.params or None,
                         headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError("API HTTP %d" % r.status_code)
        d = r.json()
        ver = self._dig(d, self.version_field)
        if ver is not None and self.version_regex:
            m = re.search(self.version_regex, str(ver))
            ver = m.group(1) if m else ver
        url = self._dig(d, self.url_field)
        note = "" if url else "字段 %s 未取到直链" % self.url_field
        return ver, url, note


class HtmlPage(Strategy):
    """网页抓版本号。正则必须精确，否则极易抓到 JS/SDK/静态资源的版本号。"""
    source_type = "html"
    url = ""
    version_regex = ""
    download_url_template = ""

    def fetch_latest(self, timeout=15):
        import requests
        r = requests.get(self.url, headers={"User-Agent": UA}, timeout=timeout)
        if r.status_code != 200:
            raise RuntimeError("HTTP %d" % r.status_code)
        m = re.search(self.version_regex, r.text)
        if not m:
            raise RuntimeError("页面未命中版本号正则")
        ver = m.group(1)
        url = (self.download_url_template.replace("{version}", ver)
               if self.download_url_template else None)
        return ver, url, ""


class Manual(Strategy):
    source_type = "manual"
    download_page = ""

    def fetch_latest(self, timeout=15):
        return None, None, ("无已验证的在线版本源；人工下载页：%s"
                            % (self.download_page or "见包 README"))


# ---------------------------------------------------------------- 入口
def main(cls):
    import argparse
    ap = argparse.ArgumentParser(
        description="%s 便携版更新脚本" % PKG)
    ap.add_argument("--check", action="store_true", help="只检测新版本（只读）")
    ap.add_argument("--update", action="store_true", help="执行更新流程")
    ap.add_argument("--ingest", metavar="FILE", help="人工下载好的安装包")
    ap.add_argument("--execute", action="store_true",
                    help="真正落地（默认 dry-run）")
    ap.add_argument("--rollback", action="store_true", help="回滚到上一备份")
    ap.add_argument("--type", dest="ptype", help="临时覆盖包类型")
    ap.add_argument("--strip", dest="strip", default=None,
                    help="临时指定程序所在的子目录（如 core）")
    ap.add_argument("--ver", dest="ver", help="指定新版本号（ingest 用）")
    ap.add_argument("--local", action="store_true", help="探测本地已装版本")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    a = ap.parse_args()

    s = cls()
    if a.ptype:
        s.package_type = a.ptype
    if a.strip:
        s.strip_root = a.strip

    if a.rollback:
        return 0 if s.rollback() else 1
    if a.ingest:
        return 0 if s.ingest(a.ingest, execute=a.execute, ver=a.ver) else 1
    if a.update:
        s.update(execute=a.execute)
        return 0
    r = s.check()
    if a.local:
        r["local"] = s.local_version()
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0
    flag = {True: "有更新", False: "最新", None: "—"}[r["has_update"]]
    log("%-24s 源=%-14s 当前=%-14s 最新=%-14s %s %s"
        % (r["pkg"], r["source"], r["current"], r["latest"], r["status"],
           flag))
    if r.get("local"):
        log("      本地实测版本：%s" % r["local"])
    if r["msg"]:
        log("      %s" % r["msg"])
    return 0


class S(Manual):
    pkg = "FSCapturePortable"
    download_page = "https://www.faststone.org/FSCaptureDetail.htm"
    app_subdir = "FSCapture"
    entry_exe = r"FSCapture\FSCapture.exe"
    package_type = "zip"
    schedule = "monthly"
    note = "原配置走蓝奏云文件夹；实测页面无版本号且需二次签名跳转"

STRATEGY = S

if __name__ == "__main__":
    sys.exit(main(S))
