# -*- coding: utf-8 -*-
r"""update_template.py —— 「一包一更新脚本」的自包含模板

**这是模板，不要直接运行。** 由 `_shared/tools/gen_update_strategies.py`
读取本文件、替换占位符后，输出 `<产品目录>/update.py`
（迁移前 dist/<Pkg>/，2026-10-18 起 <产品根>/<Pkg>/）。

为什么自包含（而不是 import 公共库）：
  用户拿到的是产品目录这一整个文件夹，常常整个拷走，此时仓库里的
  `_shared/` 并不在旁边。更新脚本必须能单目录独立运行，所以引擎代码
  直接内联。代价是有重复，收益是"拷走就能用"，这个取舍是值得的。
  代价的补偿：仓库根用「探测式」定位（环境变量 PORTABLEAPPS_REPO 或
  逐级上溯找 _shared/），拷走后找不到仓库就自动退临时目录，不崩。

模板里所有占位符都写成**合法的 Python 字面量**，这样 `compileall`
不会把模板本身报成语法错误。

占位符：
  %%PKG%%        包名，如 ZoomPortable
  %%UPSTREAM%%   上游信息（多行说明，进 docstring）
  %%NOTES%%      备注（进 docstring，说明为什么是/不是自动源）
  %%PACKAGE_TYPE%% / %%SCHEDULE%% / %%APP_SUBDIR%% / %%ENTRY_EXE%%
  %%CURRENT%%    生成时的版本号
  %%DROP%%       drop_paths 列表字面量
  %%DISABLE%%    disable_exe 列表字面量
  %%CONFIG%%     源配置字段（多行，缩进 4 空格）
  文件末尾那个继承自基类的策略类，其基类名与 pkg / 配置块会被整段替换。

注意：docstring 里不要出现与真实代码同形的占位片段，否则生成器的
「替换第一个匹配」会先命中注释里的那份（踩过这个坑）。

运行环境：Python 3.8+，仅使用标准库（无第三方依赖）；7-Zip 为可选外部
依赖，仅解包 NSIS/Inno/7z 类安装器时需要。
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
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


def _count_files(root, cap=200000):
    """目录下文件数（早停封顶，避免超大目录拖慢）。

    用于判断"这次解包到底有没有解出东西"——rc=0 不等于解出了内容。
    """
    n = 0
    try:
        for p in Path(root).rglob("*"):
            if p.is_file():
                n += 1
                if n >= cap:
                    break
    except OSError:
        pass
    return n


def _free_bytes(path):
    """目标盘可用字节数；取不到返回 None。

    解包前要知道空间够不够：7z 在空间不足时的表现是 rc=0 但截断，
    属于最难查的一类"假成功"（见 _run_7z）。
    """
    try:
        p = Path(path)
        probe = p if p.exists() else p.parent
        usage = shutil.disk_usage(str(probe))
        return usage.free
    except Exception:                                 # noqa: BLE001
        return None


def _parse_simple_yaml(text):
    r"""极简 YAML 解析，专供 electron-updater 的 `latest.yml`。

    只支持两种结构（feed 文件实际就这两种）：
        version: 2.6.6
        files:
          - url: WinClaw-2.6.6-win-x64.exe
            sha512: ...
            size: 259058448
        path: WinClaw-2.6.6-win-x64.exe
        releaseDate: '2026-10-14T12:19:44'

    不引第三方依赖（PyYAML 未必装），不处理锚点/多行块/嵌套映射。
    解析失败时尽量返回能拿到的那部分，而不是抛异常——
    版本号拿不到会让 check() 报 ERR，比拿半截更糟。
    """
    out = {}
    cur_list = None          # 当前正在往里塞的 list（files:）
    cur_item = None          # 当前 list 元素 dict
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if indent == 0 and ":" in body:
            key, _, val = body.partition(":")
            key, val = key.strip(), val.strip()
            cur_item = None
            cur_list = None
            if not val:
                # 可能是 list 起始（files:）——先占位，看下一行
                out[key] = []
                cur_list = out[key]
            else:
                out[key] = val.strip("'\"")
        elif indent >= 2 and cur_list is not None:
            if body.startswith("- "):
                cur_item = {}
                cur_list.append(cur_item)
                body = body[2:]
            if ":" in body and cur_item is not None:
                key, _, val = body.partition(":")
                cur_item[key.strip()] = val.strip().strip("'\"")
    return out


def http_get(url, params=None, headers=None, timeout=15):
    r"""标准库 GET，返回 (status, headers, body_bytes)。

    **不使用 requests**：`python update.py --check` 在只装了标准库的解释器
    （如编辑器/Agent 自带的精简 Python）下会直接 ModuleNotFoundError，
    而检测本该是零依赖的只读动作。4xx/5xx 不抛异常，交由调用方处理。
    """
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)
    h = {"User-Agent": UA}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


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
    _expected_hash = None    # 上游给 sha256 时由 fetch_latest 填，download 校验

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
            # `entry_exe` 与 appinfo.ini 的 ProgramExecutable 同基准：相对
            # AppDir（`App/`），且含子目录段（`QQ\Bin\QQ.exe` 这类）。
            # 别拼在 app_subdir 后面——那会多出一层，恒为False。
            rel = self.entry_exe.replace("\\", "/")
            for cand in (HERE / "App" / rel, root / rel):
                if cand.is_file():
                    exe = cand
                    break
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
            #
            # 例外：**探测型**策略（如 cdn_probe）走到这里通常不是网络抖动，
            # 而是"候选版本全部未命中"——本地已是最新版、或候选范围没覆盖
            # 到真实新版。此时若照搬缓存，会把上一次的陈旧结论（有更新 +
            # 旧 latest）当成现在的结论报出来：本地明明已是最新，脚本却仍
            # 催更新。所以这类结论不可信，只在明确是网络故障时才回退。
            transient = isinstance(e, (urllib.error.URLError,
                                        TimeoutError, ConnectionError,
                                        socket.timeout))
            prev = self._load_last_check() if transient else None
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
        name = url.split("?")[0].rsplit("/", 1)[-1] or "download.bin"
        CACHE.mkdir(parents=True, exist_ok=True)
        dest = Path(dest) if dest else CACHE / name
        if dest.is_file() and dest.stat().st_size > 0:
            log("  复用缓存: %s" % dest.name)
            self._verify_hash(dest)
            return dest
        # 先写 .part 再改名：中断不会留下"看起来下完了"的半截包
        part = dest.with_name(dest.name + ".part")
        if part.is_file():
            part.unlink()
        log("  下载 -> %s" % dest.name)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        total = 0
        exp = None
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                exp = r.headers.get("content-length")
                with open(part, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        total += len(chunk)
        except Exception:                              # noqa: BLE001
            if part.is_file():
                part.unlink()
            raise
        if exp and int(exp) != total:
            part.unlink()
            raise RuntimeError("下载不完整 %d/%s 字节，已丢弃" % (total, exp))
        part.replace(dest)
        log("  完成 %.1fMB" % (dest.stat().st_size / 1024 / 1024))
        self._verify_hash(dest)
        return dest

    def _verify_hash(self, p):
        r"""上游给了 SHA256 就校验 —— 接口是 HTTPS，但缓存复用/OBS 分片
        都可能拿到坏包，装进 App/ 之后再发现就晚了。"""
        exp = getattr(self, "_expected_hash", None)
        if not exp:
            return
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        got = h.hexdigest()
        if got.lower() != str(exp).lower():
            p.unlink()
            raise RuntimeError("SHA256 校验失败（期望 %s… 实际 %s…），已丢弃"
                               % (str(exp)[:12], got[:12]))
        log("  SHA256 校验通过")

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
        # 不写死盘符：优先 PATH，再按 Windows 标准环境变量拼装（缺变量就跳过）
        cands = [shutil.which("7z"), shutil.which("7za"),
                 shutil.which("7zz")]
        for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                cands.append(os.path.join(base, "7-Zip", "7z.exe"))
        return [c for c in cands if c]

    def _unpack_7z(self, archive, dst):
        r"""逐个试用 7-Zip 候选，**拿真实文件试**，第一个解出来的就用。

        踩过：`shutil.which("7z")` 命中的 `<本机工具目录>/tools\7z.EXE`
        旁边缺 `7z.dll`（只有 `7za.dll`），于是——
          * `7z` 无参数 → 正常打印帮助、rc=0（**看起来是好的**）
          * `7z x 真包`  → `Load Error: 7z.dll` + `Can't open as archive`、rc=2

        它排在安装目录里的 7z.exe 前面，结果所有
        NSIS / Inno / 7z 自解压包**静默解包失败**，表现为"更新没反应"。
        所以用"无参数跑一次"做健康检查是**骗人的**，必须拿真包试。
        """
        last = ""
        tried = 0
        for c in self._7z_candidates():
            if not c or not Path(c).is_file():
                continue
            tried += 1
            # 7-Zip 有时认不出 NSIS 自解压容器（华为 CodeArts 的安装器就是），
            # 把它当裸 PE 直接 rc=2；只有显式 -tNsis 才解得开。
            rc = None
            for extra in ((), ("-tNsis",)):
                try:
                    r = subprocess.run([c, "x", *extra, str(archive), "-y",
                                        "-o%s" % dst], capture_output=True,
                                       timeout=1800)
                except Exception as e:                 # noqa: BLE001
                    last, rc = str(e)[:200], -1
                    continue
                rc = r.returncode
                if rc == 0 and self._unpack_inner(dst):
                    return True
                last = (((r.stdout or b"") + (r.stderr or b""))
                        .decode("utf-8", "replace").strip()[-300:])
            log("  7-Zip %s 解包失败（rc=%s），换下一个候选"
                % (Path(c).name, rc))
        if not tried:
            log("  [需要 7-Zip] 无法解包 %s；请在 PATH 里放一个可用的 7z.exe，"
                "或把 7-Zip 安装目录加入 PATH" % self.package_type)
        else:
            log("  [解包失败] 所有 7-Zip 候选都失败：\n%s" % last)
        return False

    def _run_7z(self, archive, dst):
        """解一层，并**校验真的解出了内容**。

        只看 rc=0 是不够的，有两种"假成功"：

        1. 某些 7-Zip 变体（尤其精简的 7za）遇到多卷/大载荷时会 rc=0
           却只解出一部分——实测 OfficeAce 1.4.1 的 `payload-python.7z`
           解成功、`payload-rest.7z`（真正含 OfficeAce.exe 的那个）被
           跳过，结果顶层只剩一个 `tools/`。
        2. **磁盘空间不足**时 7z 可能 rc=0 但中途截断。实测 C 盘剩 3.3GB
           时，910MB 的 `payload-rest.7z` 解到一半就停，顶层同样只剩
           先解出来的 `tools/`。

        两种都靠"解完比对新出现的文件数"识别：一个文件都没新增就当失败，
        换下一个候选；若所有候选都失败，必须让上层看到失败（返回 False），
        否则 install 会拿一个只剩 tools/ 的空壳替换掉整个 App/。
        """
        before = _count_files(dst)
        for c in self._7z_candidates():
            if not c or not Path(c).is_file():
                continue
            for extra in ((), ("-tNsis",)):
                try:
                    r = subprocess.run([c, "x", *extra, str(archive), "-y",
                                        "-o%s" % dst], capture_output=True,
                                       timeout=1800)
                except Exception:                      # noqa: BLE001
                    continue
                if r.returncode == 0 and _count_files(dst) > before:
                    return True
        # 到这里说明"没解出东西"。区分两种原因给不同提示：
        free = _free_bytes(dst)
        if free is not None and free < 1 << 30:
            log("  [失败] %s 未解出内容；目标盘可用空间仅 %.1f GB，"
                "很可能空间不足导致 7z 静默截断"
                "（解包此类安装包需预留数倍于压缩包的体积）"
                % (Path(archive).name, free / (1 << 30)))
        else:
            log("  [失败] %s 未解出内容（所有 7-Zip 候选 rc=0 但零产出，"
                "疑似截断/不支持的压缩方式）" % Path(archive).name)
        return False

    def _unpack_inner(self, root):
        r"""把NSIS 外壳里的载荷再解一层，直到入口文件出现。

        支持两种载荷位置与两种组织方式：

        **旧结构**（华为 CodeArts 等）：`$PLUGINSDIR\app-64.7z` 单个内包。
        外层 PE 只装了个卸载器和 288MB 的 `app-64.7z`，真正的
        CodeArts.exe 在第二层里。

        **新结构**（OfficeAce 1.4.1 等）：载荷在**根目录**的
        `payload-*.7z`，且拆成多段：

            $PLUGINSDIR\\nsDialogs.dll, System.dll, nsExec.dll, nsis7z.dll, *.ps1
            payload-python.7z   -> tools\\python\\*, tools\\repack\\*  （安装器辅助工具）
            payload-rest.7z     -> OfficeAce.exe, resources\\app.asar, vendor\\*, version
            payload-skills.7z   -> office-claw-skills\\*, node_modules\\*
            uninstall.exe

        三个必须处理的坑：

        1. **载荷在根目录，不在 `$PLUGINSDIR`。** 只找 PLUGINSDIR 会漏掉
           新结构，结果只解出安装器插件。
        2. **多个 7z 必须全解，不能只解最大的那个。** `payload-skills.7z`
           165MB < `payload-rest.7z` 347MB，只解最大的会丢掉 skills 与
           node_modules；而只解 `payload-python.7z` 会得到一个只有
           `tools/python` 的目录，**看起来"解包成功"，实际把 App/ 换成了
           空壳**——最危险的一种失败。
        3. **`tools/` 是安装器的便携化辅助工具，不是程序本体。** 真正的
           更新器在应用内（Electron 自带通道），用不上这些脚本。
        """
        root = Path(root)
        # 候选内层包：根目录 payload-*.7z（优先）+ $PLUGINSDIR\*.7z
        inners = sorted(root.glob("payload-*.7z"))
        plug = root / "$PLUGINSDIR"
        if plug.is_dir():
            inners += sorted(plug.glob("*.7z"))
        if not inners:
            # 单层安装器：只要入口在就成立
            return self._entry_ok(root)

        log("  发现 %d 个内层载荷：%s"
            % (len(inners), ", ".join(p.name for p in inners)))
        n_ok = 0
        for p in inners:
            log("  二次解包 %s" % p.name)
            if self._run_7z(p, root):
                n_ok += 1
            else:
                # 记录但不立即中断：可能某个 payload 本就是可选组件。
                # 最终以"入口是否出现"为准（下面统一判定），这样单个
                # 可选载荷缺失不会误杀，而主载荷缺失必然进不到那一步。
                log("  [警告] %s 未解出内容" % p.name)
        # 清掉 NSIS 外壳残留
        for junk in ("$PLUGINSDIR", "$R0", "$R1", "$TEMP", "$PLUGINS"):
            p = root / junk
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
        for pat in ("Uninstall*.exe", "uninstall*.exe"):
            for p in root.glob(pat):
                try:
                    p.unlink()
                except OSError:
                    pass
        # 安装器自带的便携化辅助工具（tools\python、tools\repack）。
        # 只在"确实有程序本体"时才剔除——否则 tools/ 是唯一内容时
        # 剔掉了就什么都不剩，更没法诊断。
        tools = root / "tools"
        if tools.is_dir():
            has_entry = any(p.is_file() for p in root.glob("*.exe"))
            if has_entry:
                shutil.rmtree(tools, ignore_errors=True)
                log("  剔除安装器辅助目录 tools/（非程序本体）")
            else:
                log("  [警告] 顶层未见 exe，疑似只剩安装器辅助目录 "
                    "tools/ —— 多半是解包截断（磁盘空间不足？）")

        if not self._entry_ok(root):
            log("  [失败] 内层解包后仍未找到入口 %s，判定解包失败"
                % self.entry_exe)
            return False
        return True

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
    def _entry_ok(self, root):
        r"""**待替换的目录**里必须有程序入口，否则判定"解错了地方"。

        只看 root，不看当前安装目录。这点很关键：早期版本会额外查
        `HERE/App/<entry_exe>`（当前已装的那份），结果**安全闸永远放行**
        ——它验的是"旧版本在不在"，而要判断的是"新解出来的在不在"。
        解包失败只剩一个 tools/ 时照样通过，闸门形同虚设（实测踩过）。

        判定顺序：
          1. `root/<entry_exe>`——最准。
          2. 顶层任意 `*.exe`——各安装器解出的入口名/层级差异很大
             （有的多一层 `bin/`），安全闸的目的是拦住"只解出插件和
             辅助文件的空壳"，不是逐字节核对文件名。

        fallback 只看**顶层**，绝不用 `rglob`：安装器辅助工具
        （`tools\repack\7zzs.exe`）藏得很深，递归匹配会让"只剩 tools/"
        这种残缺结果蒙混过关。
        """
        root = Path(root)
        if not root.is_dir():
            return False
        # 候选基准：解包根目录 + 它的直接子目录（安装器可能解出
        # `产品-1.2.3/xxx.exe` 这样的单层外壳）
        bases = [root]
        try:
            bases += [p for p in list(root.iterdir())[:40] if p.is_dir()]
        except OSError:
            pass
        if self.entry_exe:
            rel = self.entry_exe.replace("\\", "/")
            name = Path(rel).name
            for base in bases:
                if (base / rel).is_file() or (base / name).is_file():
                    return True
        try:
            return any(p.is_file() for p in root.glob("*.exe"))
        except OSError:
            return False

    def install(self, src_dir, execute=False):
        """只替换 App/<程序子目录>；Data/ 与 AppInfo/ 在别的路径，天然不被碰。"""
        if not self.app_subdir:
            log("  [中止] 未配置 app_subdir，不敢盲替换")
            return False
        # 落地的最后一道闸：源目录里必须能找到入口文件。
        # 上游换安装器技术（NSIS → 别的容器、或内层载荷改名）时，脚本可能
        # "解包成功"却只解出辅助文件/插件；此时若照常替换，等于把整个
        # App/ 换成空壳，用户下次启动才发现应用没了。宁可失败也不落地。
        if not self._entry_ok(src_dir):
            log("  [中止] 源目录缺少入口文件（%s），判定解包结果不可用；"
                "已放弃替换，App/%s 保持原样"
                % (self.entry_exe or "*.exe", self.app_subdir))
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
            log("  无需更新" if r["status"] != "ERR" else "  检测失败")
            r["ok"] = r["status"] != "ERR"
            return r
        if not r.get("url"):
            log("  有新版但无直链，请人工下载后用 --ingest 接管")
            r["ok"] = False
            return r
        arch = self.download(r["url"])
        # 解包前的空间预检：这类 Electron 安装器解包后通常是压缩包的
        # 2~3 倍（实测 697MB 安装包解出约 1.7GB）。空间不够时 7z 会 rc=0
        # 却中途截断，解出半个目录——不预检的话，唯一的信号是"更新后
        # 应用打不开"，那时候已经晚了。所以在下载前就拦住。
        need = arch.stat().st_size * 3
        free = _free_bytes(CACHE)
        if free is not None and free < need:
            log("  [中止] 缓存盘可用空间 %.1f GB，不足以解包 %s"
                "（约需 %.1f GB = 压缩包 %.0f MB × 3）"
                % (free / (1 << 30), arch.name,
                   need / (1 << 30), arch.stat().st_size / 1024 / 1024))
            log("         请清理磁盘后重试；或用环境变量把缓存挪到大盘："
                "设 PORTABLEAPPS_REPO 指向目标盘上的仓库目录")
            r["ok"] = False
            return r
        tmp = CACHE / "_unpack"
        if tmp.exists():
            shutil.rmtree(tmp)
        if not self.unpack(arch, tmp):
            r["ok"] = False
            return r
        src = self.post_unpack(tmp)
        if not self.install(src, execute=execute):
            r["ok"] = False
            return r
        if not self.bump_version(r["latest"], execute=execute):
            r["ok"] = False
            return r
        if execute:
            # 落地后清掉解包临时目录；dry-run 时保留，方便人肉检查解出来对不对
            self.cleanup_tmp(tmp)
            ok = self.verify()
            log("  结构校验：%s" % ("PASS" if ok else "FAIL（可 --rollback）"))
            r["ok"] = ok
        else:
            r["ok"] = True
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
        u = "https://api.github.com/repos/%s/releases/latest" % self.repo
        h = {"Accept": "application/vnd.github+json"}
        # 未认证的 GitHub API 只有 60 次/小时（按 IP 计），4 个包连着跑几轮就
        # 打满了。带 token 可以到 5000 次/小时，CI 里务必配。
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if tok:
            h["Authorization"] = "Bearer %s" % tok
        code, _hdr, body = http_get(u, headers=h, timeout=timeout)
        if code == 403:
            raise RuntimeError(
                "GitHub HTTP 403：限流（未认证 60 次/小时"
                "，设置环境变量 GITHUB_TOKEN 可到 5000 次/小时）")
        if code != 200:
            raise RuntimeError("GitHub HTTP %d" % code)
        d = json.loads(body.decode("utf-8", "replace"))
        tag = d.get("tag_name") or ""
        url = None
        for a in d.get("assets", []):
            if re.search(self.asset_regex, a.get("name", "")):
                url = a.get("browser_download_url")
                break
        note = "" if url else "assets 未命中 %s" % self.asset_regex
        return tag, url, note


class ApiJson(Strategy):
    r"""JSON / YAML / 混合接口取版本号与直链。

    `version_field` / `url_field` 支持点号路径，段可以是：
      - 普通键：`versions.Windows_x64.version_number`
      - 数组下标：`info-list.0.version`（腾讯会议就用这个）

    三种数据形态都能吃：
      1. JSON（`Content-Type: application/json`）
      2. **YAML** —— electron-updater 的 generic feed 就是 `latest.yml`
         （今日头条 / WinClaw / Qoder CN 都用它）。无第三方依赖，
         只解析顶层 `key: value` 与一层 `files:` 列表，够用。
      3. JSON 里嵌着一段**URL 字符串**，版本号要从 URL 路径里抠
         （TIM 的 `download_link.windows`、QQ 的 `downloadUrl`）。
         这时把 `version_regex` 写成带捕获组的正则，
         并对 `version_field` 指向的字符串执行。

    坑（都踩过）：
      - 接口返回的 `version` 字段未必是这个包的版本。QQ 的
        windowsConfig.js 里 `"version":"9.9.36"` 其实是 **QQNT** 的，
        经典 QQ 早停在 9.7.25。必须从下载直链的路径里解析真实版本。
      - 版本号可能是 3 段而本地是 4 段（或反过来）。比较交给
        `cmp_version`，取不到完整段时不要瞎补。
    """
    source_type = "api"
    url = ""
    params = None
    # 需要随机 nonce 的接口（腾讯会议 query-download-info）。
    # 该参数不带会返回 code:1 + 空 info-list，看不出是缺参数。
    # 值为 "%random%" 时由 fetch_latest 现场生成 16 位十六进制。
    nonce_param = ""
    referer = ""            # 有些接口校验 Referer（如腾讯会议）
    version_field = "version"
    url_field = "downloadUrl"
    version_regex = ""
    # 有些接口只给版本号不给完整直链（Zoom 的 /rest/download 只回
    # version + packageName，下载 URL 要自己拼）。设了 url_template 就
    # 忽略 url_field，按模板拼 URL：
    #   - {version}      → 解析出的版本号
    #   - {a.b.c} 点号路径 → 从同一份 JSON 里挖值（如 packageName）
    #   - Zoom 实测：url = "https://zoom.us/rest/download?os=win"
    #     vf = "result.downloadVO.zoomX64.version"  →  "7.2.1.48556"
    #     tmpl = "https://cdn.zoom.us/prod/{version}/x64/ZoomInstallerFull.exe"
    #   ⚠️别用 downloadVO.zoom：那是已停更的 32 位分支（6.6.11），
    #   x64 版本看 zoomX64，arm 版看 zoomArm64。
    url_template = ""

    @staticmethod
    def _dig(d, path):
        cur = d
        for seg in str(path).split("."):
            if isinstance(cur, list):
                try:
                    cur = cur[int(seg)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(cur, dict):
                cur = cur.get(seg)
            else:
                return None
            if cur is None:
                return None
        return cur

    @staticmethod
    def _load(body):
        """按内容判断形态并解析：JSON → JS 内嵌对象 → YAML。

        第二种很重要：有些厂商的"接口"其实是**一段 JS**，形如
            ;(function(){var params= {"version":"9.9.36", ...}})()
        （QQ 的 windowsConfig.js 就是）。直接 json.loads 会失败，
        得先把最外层的那对花括号抠出来。
        """
        text = body.decode("utf-8", "replace")
        try:
            return json.loads(text)
        except ValueError:
            pass
        # JS 里嵌的 JSON 对象。⚠️不能从第一个 `{` 开始：形如
        #   ;(function(){var params= {"version":...}})()
        # 第一个 `{` 是**函数体**，配到最后的 `}` 得到的是
        # `{var params= {...}}`，json.loads 失败。要从**最后一个**
        # `{` 开始（那里才是对象字面量），配第一个 `}` 之前……
        # 更稳的做法：找 `{` 后跟引号键的模式，即对象字面量的特征。
        for m in re.finditer(r'\{\s*"[^"]+"\s*:', text):
            start = m.start()
            # 从 start 起做括号配对，找到与之匹配的 `}`
            depth = 0
            for k in range(start, len(text)):
                ch = text[k]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:k + 1])
                        except ValueError:
                            break
        return _parse_simple_yaml(text)

    def fetch_latest(self, timeout=15):
        params = self.params or None
        if self.nonce_param:
            params = dict(params or {})
            params[self.nonce_param] = format(
                random.getrandbits(64), "016x")
        hdrs = {"Referer": self.referer} if self.referer else None
        code, _hdr, body = http_get(self.url, params=params, headers=hdrs,
                                    timeout=timeout)
        if code != 200:
            raise RuntimeError("API HTTP %d" % code)
        d = self._load(body)
        ver = self._dig(d, self.version_field)
        if ver is not None:
            ver = str(ver)
            if self.version_regex:
                m = re.search(self.version_regex, ver)
                if m:
                    ver = m.group(1) if m.groups() else m.group(0)
        url = None
        note = ""
        if self.url_template:
            # 模板拼 URL：{version} 用解析出的版本号，其余 {路径}
            # 从同一份 JSON 挖。挖不到就报 None + note，绝不输出半拼的假链。
            def _sub(key):
                if key == "version":
                    return ver
                val = self._dig(d, key)
                return None if val is None else str(val)
            parts = []
            pos = 0
            for m in re.finditer(r"\{([^{}]+)\}", self.url_template):
                parts.append(self.url_template[pos:m.start()])
                key = m.group(1)
                sub = _sub(key)
                if sub is None:
                    note = "模板占位符 {%s} 在 JSON 中取不到" % key
                    parts = None
                    break
                parts.append(sub)
                pos = m.end()
            if parts is not None:
                parts.append(self.url_template[pos:])
                url = "".join(parts)
        else:
            url = self._dig(d, self.url_field)
            if url and not str(url).startswith(("http://", "https://")):
                # electron-updater 的 `path` 是相对 feed 基址的（如
                # `WinClaw-2.6.6-win-x64.exe`）。Qoder 的 files[0].url 才是
                # 绝对地址，两种都要兼容。
                base = self.url.rsplit("/", 1)[0]
                url = base + "/" + str(url).lstrip("/")
            if not url:
                note = "字段 %s 未取到直链" % self.url_field
        return ver, url, note


class HtmlPage(Strategy):
    """网页抓版本号。正则必须精确，否则极易抓到 JS/SDK/静态资源的版本号。"""
    source_type = "html"
    url = ""
    version_regex = ""
    download_url_template = ""

    def fetch_latest(self, timeout=15):
        code, _hdr, body = http_get(self.url, timeout=timeout)
        if code != 200:
            raise RuntimeError("HTTP %d" % code)
        text = body.decode("utf-8", "replace")
        m = re.search(self.version_regex, text)
        if not m:
            raise RuntimeError("页面未命中版本号正则")
        ver = m.group(1)
        url = (self.download_url_template.replace("{version}", ver)
               if self.download_url_template else None)
        return ver, url, ""


class HuaweiReleaseInfo(Strategy):
    r"""华为云 IDE 升级接口（CodeArts / CodeArts Agent 系列）。

    GET {url}?sub_product_name=&current_version=&arch=&is_server=&os_type=
    实测返回：
      {"status":"success","result":{"version":"0.2.6","available":true,
       "url":"https://cdn.example.com/<installer>-<ver>-x64.exe",
       "hash":"<sha256>"}}

    坑一：current_version 传 0.2.3 / 0.2.6 / 空，服务端都返回同一个最新版，
          所以 available 不能当"有没有新版"用，必须自己比版本号。
    坑二：接口地址只写在客户端 resources/product.json 的 updateUrl 里，
          官网下载页抓不到版本号，别去解析 HTML。
    坑三：arch 必须是 X86-64 / Arm64（不是 win32-x64），写错直接 400。
    """
    source_type = "api"
    url = ""
    sub_product_name = "work"
    arch = "X86-64"
    os_type = "windows"

    def fetch_latest(self, timeout=15):
        params = {
            "sub_product_name": self.sub_product_name,
            "current_version": self.current_version() or "",
            "arch": self.arch,
            "is_server": "false",
            "os_type": self.os_type,
        }
        code, _hdr, body = http_get(self.url, params=params, timeout=timeout)
        if code != 200:
            raise RuntimeError("华为升级接口 HTTP %d" % code)
        d = json.loads(body.decode("utf-8", "replace"))
        if d.get("status") != "success":
            raise RuntimeError("华为升级接口 status=%s" % d.get("status"))
        res = d.get("result") or {}
        ver = res.get("version")
        if not ver:
            raise RuntimeError("接口未返回 version 字段")
        # 交给 download 做完整性校验（缓存复用也会校验）
        self._expected_hash = res.get("hash") or None
        url = res.get("url") if res.get("available") else None
        note = "" if url else "接口未给出可下载安装包（available=false）"
        return ver, url, note


class CdnProbe(Strategy):
    r"""按版本号拼URL 做 HEAD 探测，找出最新版。

    适用于**上游不提供版本索引接口、但安装包按
    `.../<产品>-<版本>-<平台>-<架构>-setup.exe` 规律挂在静态 CDN 上**的产品。

    为什么不用接口：某些产品的版本只经**私有 Socket.IO 通道**下发
    （`update:subscribe` → `update:version-state`），服务端需要登录态鉴权，
    且实测该地址常返回 502——标准库 urllib 复现不了（还得装websocket
    依赖）。改为直接探测已知的公开 CDN 路径。

    两个要点：
    - **403 不等于 404**：这类 CDN 关闭了目录列举（列目录本身就返 403），
      不存在的文件名同样返 403。所以判定"存在"只看 200，
      不能用 404 做"确认不存在"的结论，否则会把网关错误当新版。
    - 探测是**分段发散**的：先在当前次版本内升补丁，再进到后续次版本
      从补丁 0 探起。这样既能覆盖 1.3.4 → 1.4.1 这种跳版发布
      （中间的 1.4.0 根本不存在），又不会漏掉正常递增。

    全部候选都未命中时返回当前版本（而非抛异常）：此时探测本身很可能是
    成功的（拿到了明确的 403），最常见就是本地已是最新。抛异常会让
    `check()` 把上次的陈旧"有更新"结论当现状报出。

    代价：每次检查发若干个 HEAD 请求，实测单次 ~0.1s，可接受。
    `patch_lookahead` / `minor_span` / `minor_patch_cap` 是兜底上限，
    防止版本号规则变化时无限探测。
    """
    source_type = "cdn_probe"
    cdn_base = ""
    name_pattern = "{version}"
    start_version = None         # None = 用本包当前版本作起点
    patch_lookahead = 4          # 当前次版本内，往后探几个补丁号
    minor_span = 2               # 再往后看几个次版本
    minor_patch_cap = 4          # 次版本下探到第几补丁号（0..N）
    # 本地线索文件（相对便携包根）：应用自己会把"它看到的最新版"写在这里，
    # 拿它当候选可把常见情况压到 1 次 HEAD
    hint_files = []
    # 已知版本号 -> sha256。上游 CDN 通常不提供摘要，这里靠人工登记；
    # 登记了才校验，没登记则只靠 HTTPS + 解包完整性。
    known_hashes = {}

    def _candidates(self, cur):
        r"""从当前版本出发，按**升序**生成候选版本号列表。

        要点：不能只在补丁位上+1。上游若 1.3.4 → 1.4.1（1.4.0 从未存在），
        只在补丁位递增会一路探 1.3.5…1.3.99 永远到不了 1.4.1。所以分两段：
          段一：当前次版本内继续升补丁（1.3.5 … 1.3.8）
          段二：随后每个次版本从补丁 0 探到上限（1.4.0 … 1.4.4）
        全程严格升序，命中第一个 200 即停，所以不会跳过真正的最新版。
        """
        base = self.start_version or cur or "1.0.0"
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(base))
        if not m:
            raise RuntimeError("无法解析当前版本号：%r" % base)
        a, b, c = (int(m.group(i)) for i in (1, 2, 3))
        out = []
        for i in range(self.patch_lookahead):
            out.append("%d.%d.%d" % (a, b, c + 1 + i))
        for mi in range(1, self.minor_span + 1):
            for p in range(0, self.minor_patch_cap + 1):
                out.append("%d.%d.%d" % (a, b + mi, p))
        return out

    def _url_for(self, ver):
        return "%s/%s" % (self.cdn_base.rstrip("/"),
                          self.name_pattern.format(version=ver))

    def _hint_version(self):
        r"""从本地线索文件读一个"很可能存在"的候选版本。

        应用自己会把下载任务写进 `updates/state.json`，形如
        `{"taskId":"version-1.4.1", ...}`。这是应用已经跟服务端对过一次的
        结果，比盲目发散准得多——先探它，一次命中就收工。
        只作线索：探不到就当没有，回落到发散探测。
        """
        for rel in self.hint_files:
            # 容错：允许写成单个路径字符串，也允许写成路径列表
            if isinstance(rel, (list, tuple)):
                rel = rel[0] if rel else ""
            if not rel:
                continue
            p = HERE / str(rel).replace("\\", "/")
            if not p.is_file():
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8",
                                           errors="replace"))
            except Exception:                          # noqa: BLE001
                continue
            for t in (d.get("tasks") or []):
                m = re.match(r"^version-(\d+(?:\.\d+)+)$",
                             str(t.get("taskId") or ""))
                if m:
                    log("  本地线索：%s → %s" % (p.name, m.group(1)))
                    return m.group(1)
        return None

    def fetch_latest(self, timeout=15):
        cur = self.current_version() or self.start_version

        def probe(ver):
            """返回 (存在?, 大小)。只有 200 算存在。"""
            req = urllib.request.Request(self._url_for(ver), method="HEAD",
                                         headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    if r.status != 200:
                        return False, 0
                    return True, int(r.headers.get("Content-Length") or 0)
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    return False, 0
                raise RuntimeError("CDN 探测 HTTP %d（%s）" % (e.code, ver))
            except Exception as e:                       # noqa: BLE001
                raise RuntimeError("CDN 探测失败：%s" % str(e)[:80])

        def hit(ver, size, extra=""):
            log("  命中 %s（%.1f MB）" % (ver, size / 1024 / 1024))
            self._expected_hash = self.known_hashes.get(ver)
            return ver, self._url_for(ver), (
                "CDN HEAD 探测命中；存在即发布，403 视为未发布" + extra)

        # 快路径：先探应用自己的线索
        hint = self._hint_version()
        if hint and (hint == cur or cmp_version(hint, cur) > 0):
            ok, size = probe(hint)
            if ok:
                return hit(hint, size)
            log("  线索 %s 未命中，回落发散探测" % hint)

        cands = self._candidates(cur)
        log("  探测 %d 个候选版本（起点 %s）…" % (len(cands), cur))
        miss = []
        for ver in cands:
            ok, size = probe(ver)
            if ok:
                extra = ""
                if miss:
                    extra = "；跳过 %d 个未发布版本号（上游跳版发布）" % len(miss)
                return hit(ver, size, extra)
            miss.append(ver)
        # 全部候选都是"不存在"，但探测本身很可能成功（拿到了明确的 403），
        # 所以这**不是故障**：最常见就是本地已是最新。约定latest 回填
        # 当前版本 → check() 判定 LATEST。
        return (cur, None,
                "已探测 %d 个候选版本（%s…%s）均未发布；当前版本 %s 即最新。"
                "若上游确有更新但未检出，请上调 patch_lookahead / "
                "minor_span / minor_patch_cap"
                % (len(cands), cands[0], cands[-1], cur))


class RedirectProbe(Strategy):
    r"""跟随 302，从 `Location` 头里抠版本号与直链。

    某些厂商把"最新版下载入口"做成一个**稳定的重定向端点**，真实文件
    地址（含版本号）放在 Location 里。企业微信就是典型：

        HEAD https://work.weixin.qq.com/wework_admin/commdownload?platform=win
        → 302, Location: .../WeCom_5.0.12.6018.exe

    这是最优雅的一类版本源：一次请求同时拿到版本 + 直链，CDN 换 URL
    时无需改代码。比解析 HTML 稳得多（HTML 里全是 JS 库版本号噪音）。

    实现要点：**不要让 urllib 自动跟随重定向**，否则拿到的是最终响应体，
    Location 头就丢了。手动读 `r.headers.get("Location")`。
    """
    source_type = "redirect"
    url = ""
    version_regex = ""
    # Location 里的文件名可能相对路径，用它拼绝对地址
    base_for_relative = ""

    def fetch_latest(self, timeout=15):
        req = urllib.request.Request(self.url, method="HEAD",
                                     headers={"User-Agent": UA})

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **kw):
                return None        # 拒绝跟随，让 302 直接冒到上层

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            r = opener.open(req, timeout=timeout)
            # 没重定向：说明端点失效或已改成直链
            loc = r.headers.get("Location")
            code = r.status
            r.close()
        except urllib.error.HTTPError as e:
            code = e.code
            loc = e.headers.get("Location") if e.headers else None
            if e.code not in (301, 302, 303, 307, 308):
                raise RuntimeError("重定向端点 HTTP %d" % e.code)
        if not loc:
            raise RuntimeError("端点未返回 Location（HTTP %d），"
                               "可能已改为直链或失效" % code)
        if not loc.startswith(("http://", "https://")):
            base = self.base_for_relative or self.url.rsplit("/", 1)[0]
            loc = base.rstrip("/") + "/" + loc.lstrip("/")
        m = re.search(self.version_regex, loc) if self.version_regex else None
        ver = (m.group(1) if m.groups() else m.group(0)) if m else None
        if not ver:
            raise RuntimeError("Location 未命中版本正则：%s" % loc[:120])
        return ver, loc, "跟随 302 Location 解析"


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
    if REPO_ROOT is None and not a.json:
        log("  [提示] 未定位到仓库根（可设 PORTABLEAPPS_REPO 固定）："
            "缓存与备份退到临时目录 %s" % CACHE.parent.parent)

    if a.rollback:
        return 0 if s.rollback() else 1
    if a.ingest:
        return 0 if s.ingest(a.ingest, execute=a.execute, ver=a.ver) else 1
    if a.update:
        try:
            r = s.update(execute=a.execute)
        except Exception as e:                      # noqa: BLE001
            log("  [失败] %s: %s" % (type(e).__name__, str(e)[:200]))
            return 1
        return 0 if r.get("ok", True) else 1
    r = s.check()
    if a.local:
        r["local"] = s.local_version()
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["status"] != "ERR" else 1
    flag = {True: "有更新", False: "最新", None: "—"}[r["has_update"]]
    log("%-24s 源=%-14s 当前=%-14s 最新=%-14s %s %s"
        % (r["pkg"], r["source"], r["current"], r["latest"], r["status"],
           flag))
    if r.get("local"):
        log("      本地实测版本：%s" % r["local"])
    if r["msg"]:
        log("      %s" % r["msg"])
    return 0 if r["status"] != "ERR" else 1


class S(Strategy):
    pkg = "%%PKG%%"
    # %%CONFIG%% 生成器会把 pkg 与本行整体替换成真实配置块；占位符写成注释，是为让模板本身合法可编译

STRATEGY = S

if __name__ == "__main__":
    sys.exit(main(S))
