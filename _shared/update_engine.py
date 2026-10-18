# -*- coding: utf-8 -*-
"""update_engine.py —— 便携软件自动化更新引擎（方案整合定稿版落地）

一个引擎 + Configs\\<项目>.yaml 配置，覆盖七阶段流水线：
  detect → download/ingest → extract → diff → test → stage → release（门禁）→ rollback

强制约束（.trae/rules/00-protocol.md）：
  - 所有破坏性操作 dry_run 默认 True，需显式 --execute 才落地
  - Data 目录只读（仅生成清单快照），任何阶段不写入/删除
  - 结构化 dict 返回（exit_code / 时间戳 / 证据路径），日志走 logging
  - 状态文件原子写（临时文件 + os.replace）
  - 依赖白名单：标准库 + requests + psutil + packaging + PyYAML

版本源诚实原则：仅配置了可靠来源的项目执行在线检测；其余标记 needs_manual，
由人工下载后通过 ingest 子命令接管后续全流程（腾讯会议半自动先例）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import psutil
import requests
import yaml
from packaging.version import InvalidVersion, Version

# ---------------------------------------------------------------- 路径与常量

ROOT = Path(__file__).resolve().parent          # ...\PortableApps\_shared
WORK = ROOT.parent                              # ...\PortableApps（各项目父目录）
CONFIGS = ROOT / "configs"
STATE_FILE = ROOT / "state" / "update_versions.json"
EVIDENCE = ROOT / "evidence"
STAGING = ROOT / "staging"
REPORTS = ROOT / "reports"
CHANGELOG = ROOT / "docs" / "update_changelog.md"

# 冒烟测试残留扫描的宿主噪声白名单（便携包外、确认属宿主环境）
NOISE_PATTERNS = [
    r"tencent", r"zoom", r"trae[ _-]?cn", r"workbuddy", r"microsoft",
    r"pnpm-cache", r"awesun", r"wechat", r"xwechat", r"qimei",
    r"gameviewer",            # 向日葵远控 webview 缓存（宿主远控软件）
    r"tablacus",              # 宿主文件管理器
    r"python-languageserver",
    r"appdata[\\/]local[\\/]temp",  # 系统临时目录（项目既定过滤规则）
]

# diff 阶段高危文件名特征（更新器/服务组件）。
# 仅匹配可执行/配置级文件的基本名；node_modules 等库内源文件不参与判定
# （Azure MSAL 的 telemetry/*.mjs 之类是库内部实现，非独立遥测服务）。
RISK_FILE_PATTERNS = {
    "updater": re.compile(
        r"(?i)(^|[/\\])(update\.exe|updater\.exe|inno_updater\.exe|"
        r"app-update\.yml|app-updater\.yml|squirrel[^/\\]*)$"),
    "service": re.compile(
        r"(?i)(^|[/\\])[^/\\]*(service|svc|crashpad|crashhandler|beacon)"
        r"[^/\\]*\.(exe|dll)$"),
}
RISK_EXCLUDE_DIRS = re.compile(r"(?i)(^|[/\\])node_modules[/\\]")

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 60
# 页面类/网盘类版本源统一 UA（避免被站点判定为爬虫）
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DOWNLOAD_CHUNK = 1024 * 1024

log = logging.getLogger("update_engine")


# ---------------------------------------------------------------- 基础工具

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(DOWNLOAD_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_json(path: Path, data: dict) -> None:
    """临时文件 + os.replace 原子写 JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, path)


def load_state() -> dict:
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    return {"schema": 1, "updated_at": None, "projects": {}}


def save_state(state: dict) -> None:
    state["updated_at"] = now_iso()
    atomic_write_json(STATE_FILE, state)


def load_config(project: str) -> dict:
    path = CONFIGS / f"{project}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"配置不存在: {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    cfg["_config_path"] = str(path)
    return cfg


def list_projects() -> list[str]:
    if not CONFIGS.is_dir():
        return []
    return sorted(p.stem for p in CONFIGS.glob("*.yaml"))


def evidence_dir(project: str, run_id: str, stage: str) -> Path:
    d = EVIDENCE / project / run_id / f"update-{stage}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def result(exit_code: int, msg: str, **kw) -> dict:
    """统一结构化返回"""
    out = {"exit_code": exit_code, "msg": msg, "timestamp": now_iso()}
    out.update(kw)
    level = logging.INFO if exit_code == 0 else logging.WARNING
    log.log(level, "%s", msg)
    return out


def pkg_dir(cfg: dict) -> Path:
    return WORK / cfg["dir"]


def app_root(cfg: dict) -> Path:
    """便携包 App 层根目录（其下为 entry_exe 等程序文件）"""
    return pkg_dir(cfg) / "App"


def find_7z() -> str | None:
    """定位 7-Zip：优先独立版 7za（无 7z.dll 依赖；PATH 上的 7z.EXE
    若缺 7z.dll 则无法解 LZMA，实证于 2026-10-16 Zen SFX），
    其次 PATH 7z，最后常见安装位置"""
    w = shutil.which("7za")
    if w:
        return w
    for c in (r"<本机工具目录>/tools\7za.exe",):
        if Path(c).is_file():
            return c
    w = shutil.which("7z")
    if w:
        return w
    for c in (r"C:\Program Files\7-Zip\7z.exe",
              r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if Path(c).is_file():
            return c
    return None


def find_innounp() -> str | None:
    """定位 innounp（Inno Setup 解包器）。

    优先级（不写死任何绝对路径，换机器可用）：
      1) 环境变量 PAF_INNOUNP 指向 innounp.exe 或其所在目录
      2) PATH
      3) 仓库内常见位置：<_shared|项目>/tools/innounp/、tools/innounp/
    找不到返回 None，由调用方给出提示（含 PAF_INNOUNP 说明）。
    """
    here = Path(__file__).resolve()
    env = os.environ.get("PAF_INNOUNP")
    if env:
        p = Path(env)
        if p.is_dir():
            p = p / "innounp.exe"
        if p.is_file():
            return str(p)

    w = shutil.which("innounp")
    if w:
        return w

    roots = [here.parent, here.parent.parent, Path.cwd()]
    cands: list[Path] = []
    for r in roots:
        cands += [r / "tools" / "innounp" / "innounp.exe",
                  r / "tools" / "innounp.exe"]
    for c in cands:
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    return None


def pe_machine(path: Path) -> int | None:
    """struct 直读 PE Machine（0x8664=x64 / 0x014c=x86），不依赖 pefile"""
    try:
        with open(path, "rb") as f:
            head = f.read(0x40)
            if len(head) < 0x40 or head[:2] != b"MZ":
                return None
            (pe_off,) = struct.unpack_from("<I", head, 0x3C)
            f.seek(pe_off)
            sig = f.read(6)
            if sig[:4] != b"PE\0\0":
                return None
            (machine,) = struct.unpack_from("<H", sig, 4)
            return machine
    except OSError:
        return None


def dir_manifest(base: Path, with_hash: bool = False) -> dict:
    """目录清单：{相对路径: {size, mtime[, sha256]}}。只读，不写目标目录"""
    items: dict = {}
    if not base.is_dir():
        return items
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        rel = p.relative_to(base).as_posix()
        entry = {"size": st.st_size, "mtime": int(st.st_mtime)}
        if with_hash:
            entry["sha256"] = sha256_file(p)
        items[rel] = entry
    return items


def kill_by_path_prefix(prefix: Path, timeout: int = 15) -> list[int]:
    """按可执行路径前缀终止进程（绝不按映像名全局杀）"""
    prefix_s = str(prefix).lower()
    killed: list[int] = []
    for proc in psutil.process_iter(["pid", "exe"]):
        try:
            exe = proc.info.get("exe") or ""
            if exe.lower().startswith(prefix_s):
                proc.terminate()
                killed.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        procs = []
        for pid in killed:
            try:
                procs.append(psutil.Process(pid))
            except psutil.NoSuchProcess:
                pass  # 进程已自行退出（TOCTOU 竞态）
        _, alive = psutil.wait_procs(procs, timeout=timeout)
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    return killed


def processes_under(prefix: Path) -> list[dict]:
    prefix_s = str(prefix).lower()
    out = []
    for proc in psutil.process_iter(["pid", "exe", "name"]):
        try:
            exe = proc.info.get("exe") or ""
            if exe.lower().startswith(prefix_s):
                out.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


# ---------------------------------------------------------------- detect

def _to_candidates(values: list[str]) -> list:
    """原始版本串列表 → [(Version, 原串)]，去重后排序"""
    out: dict[str, Version] = {}
    for v in values:
        try:
            out[v] = Version(v)
        except InvalidVersion:
            continue
    return sorted((ver, s) for s, ver in out.items())


def _versions_from_names(names: list[str], pattern: str) -> list:
    """文件名列表按正则抽版本串 → 候选列表
    pattern 为空时用通用版本正则（必须含小数点，天然滤掉 20260817 这类日期）"""
    rex = re.compile(pattern or r"\d+\.\d+(?:\.\d+){0,3}")
    vals: list[str] = []
    for n in names:
        for m in rex.findall(n or ""):
            vals.append(m if isinstance(m, str) else (m[0] if m else ""))
    return _to_candidates(vals)


def _finish_version_detect(cfg: dict, entry: dict, project: str, versions: list,
                           source: str, label: str = "最新") -> dict:
    """版本候选 → 取最大 → 写状态并返回 result
    （page_regex / lanzou_folder / ctfile_dir 三类来源共用尾段）"""
    if not versions:
        entry["status"] = "regex_miss"
        return result(3, f"{project}: {source} 未取得版本号"
                         f"（页面/分享结构可能已变）", project=project)
    latest = max(versions)[1]
    entry.update({"latest_version": latest, "status": "ok",
                  "source": source})
    entry.pop("download_url", None)  # 页面/分享页源无稳定直链
    cur = cfg.get("current_version")
    try:
        entry["update_available"] = (
            bool(cur and latest) and Version(latest) > Version(cur))
    except InvalidVersion:
        entry["update_available"] = bool(latest and latest != cur)
    return result(0, f"{project}: 当前 {cur} / {label} {latest}",
                  project=project, latest=latest,
                  update_available=entry["update_available"])


# 蓝奏云反爬 acw_sc__v2（Aliyun WAF 系列，2026-10-16 实证 osssr 分享页）
# 页面下发 var arg1='<40位十六进制>'，按「固定置换 + 逐字节异或」算出 cookie 值。
_ACW_M = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f,
          0x28, 0x1b, 0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8,
          0xe, 0x15, 0x20, 0x1a, 0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c,
          0x22, 0x25, 0xc, 0x24]
_ACW_KEY = "3000176000856006061501533003690027800375"


def _acw_sc_v2(arg1: str) -> str:
    """由页面 arg1 求 acw_sc__v2 cookie 值（算法取自页面内联 JS 实测）。"""
    buf = [""] * len(_ACW_M)
    for x, ch in enumerate(arg1[:len(_ACW_M)]):
        for z in range(len(_ACW_M)):
            if _ACW_M[z] == x + 1:
                buf[z] = ch
    u = "".join(buf)
    out = ""
    for i in range(0, min(len(u), len(_ACW_KEY)), 2):
        out += format(int(u[i:i + 2], 16) ^ int(_ACW_KEY[i:i + 2], 16), "02x")
    return out


def _lanzou_fetch(url: str, hdr: dict):
    """抓蓝奏云分享页；若命中 acw_sc__v2 反爬挑战则解盾后重取。

    返回 (session, page_text)：session 保留了反爬 cookie，
    后续 filemoreajax 列表请求必须复用同一 session，否则解盾失效。
    """
    s = requests.Session()
    page = s.get(url, headers=hdr, timeout=REQUEST_TIMEOUT)
    m = re.search(r"var arg1='([0-9A-F]+)'", page.text)
    if m:
        s.cookies.set("acw_sc__v2", _acw_sc_v2(m.group(1)),
                      domain=urlparse(url).netloc)
        page = s.get(url, headers=hdr, timeout=REQUEST_TIMEOUT)
    return s, page.text


def _lanzou_resolve(page: str, val: str):
    """把 ajax 块里的取值解析为字面量（支持字面量/变量名两种写法）。"""
    val = val.strip()
    if re.fullmatch(r"\d+", val):
        return val
    if val[:1] in "'\"":
        return val.strip("'\"")
    m = re.search(r"var\s+" + re.escape(val) + r"\s*=\s*'?([0-9a-fA-F]+)'?",
                  page)
    return m.group(1) if m else None


def lanzou_tokens(page: str) -> dict:
    """从分享页内联 ajax 块解析一次性 token（t/k 变量名每次随机，勿写死）。"""
    out = {}
    m = re.search(r"filemoreajax\.php\?file=(\d+)", page)
    out["fid"] = m.group(1) if m else None
    m = re.search(r"'uid'\s*:\s*'?(\d+)'?", page)
    out["uid"] = m.group(1) if m else None
    m = re.search(r"'puid'\s*:\s*'([^']+)'", page)
    out["puid"] = m.group(1) if m else None
    for key in ("t", "k"):
        m = re.search(r"'%s'\s*:\s*([^,}]+)" % key, page)
        out[key] = _lanzou_resolve(page, m.group(1)) if m else None
    return out


def detect_one(cfg: dict, state: dict) -> dict:
    """版本检测：仅对已配置可靠来源的项目在线检测，其余标 needs_manual"""
    project = cfg["project"]
    vs = cfg.get("version_source") or {}
    vtype = vs.get("type", "manual")
    entry = state["projects"].setdefault(project, {})
    entry["current_version"] = cfg.get("current_version")
    entry["last_checked_at"] = now_iso()
    entry["release_policy"] = cfg.get("release_policy", "manual_confirm")

    if cfg.get("release_policy") == "blocked":
        entry["status"] = "blocked"
        return result(0, f"{project}: release_policy=blocked，跳过检测",
                      project=project, status="blocked")

    if vtype == "github_releases":
        repo = vs.get("repo")
        if not repo:
            entry["status"] = "config_error"
            return result(2, f"{project}: github_releases 缺少 repo 字段",
                          project=project)
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")  # 仅从环境变量读取，不落盘
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = requests.get(f"{GITHUB_API}/repos/{repo}/releases/latest",
                             headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            entry["status"] = "network_error"
            return result(3, f"{project}: GitHub API 网络错误 {e}",
                          project=project)
        if r.status_code != 200:
            entry["status"] = f"http_{r.status_code}"
            return result(3, f"{project}: GitHub API HTTP {r.status_code}",
                          project=project)
        rel = r.json()
        latest = (rel.get("tag_name") or "").lstrip("vV")
        asset_re = vs.get("asset_regex", "")
        asset_url = None
        if asset_re:
            for a in rel.get("assets", []):
                if re.search(asset_re, a.get("name", "")):
                    asset_url = a.get("browser_download_url")
                    break
        entry.update({"latest_version": latest, "download_url": asset_url,
                      "status": "ok", "source": f"github:{repo}"})
        cur, new = cfg.get("current_version"), latest
        try:
            entry["update_available"] = (
                bool(cur and new) and Version(new) > Version(cur))
        except InvalidVersion:
            entry["update_available"] = bool(new and new != cur)
        msg = (f"{project}: 当前 {cur} / 最新 {latest}"
               f"（{'有更新' if entry['update_available'] else '已最新'}）")
        return result(0, msg, project=project, latest=latest,
                      update_available=entry["update_available"])

    if vtype == "api":
        # 通用 JSON API 版本源（已验证官方端点，如 Cursor api/download）
        url = vs.get("url")
        if not url:
            entry["status"] = "config_error"
            return result(2, f"{project}: api 源缺少 url 字段",
                          project=project)
        try:
            r = requests.get(url, params=vs.get("params") or {},
                             timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            entry["status"] = "network_error"
            return result(3, f"{project}: API 网络错误 {e}",
                          project=project)
        if r.status_code != 200:
            entry["status"] = f"http_{r.status_code}"
            return result(3, f"{project}: API HTTP {r.status_code}",
                          project=project)
        try:
            data = r.json()
        except ValueError:
            entry["status"] = "bad_json"
            return result(3, f"{project}: API 返回非 JSON", project=project)
        def _dig(obj, dotted: str):
            """api 字段点路径下钻（如 data.version_number）；无点等价 data.get"""
            cur_obj = obj
            for part in (dotted or "").split("."):
                if not isinstance(cur_obj, dict):
                    return None
                cur_obj = cur_obj.get(part)
            return cur_obj

        latest = str(_dig(data, vs.get("version_field", "version")) or "")
        asset_url = _dig(data, vs.get("url_field", "downloadUrl"))
        # 可选 version_regex：从含前缀的原始版本串抽取纯版本号
        # （实证：飞书 api 返回 "Windows@V8.2.14"）
        vre = vs.get("version_regex")
        if vre and latest:
            m = re.search(vre, latest)
            if m:
                latest = m.group(1)
        entry.update({"latest_version": latest, "download_url": asset_url,
                      "status": "ok", "source": f"api:{url}"})
        cur = cfg.get("current_version")
        try:
            entry["update_available"] = (
                bool(cur and latest) and Version(latest) > Version(cur))
        except InvalidVersion:
            entry["update_available"] = bool(latest and latest != cur)
        msg = (f"{project}: 当前 {cur} / 最新 {latest}"
               f"（{'有更新' if entry['update_available'] else '已最新'}）")
        return result(0, msg, project=project, latest=latest,
                      update_available=entry["update_available"])

    if vtype == "page_regex":
        # 官方页面正则版本源（须已实证：URL 可访问且正则能命中真实产品版本）
        url = vs.get("url")
        pattern = vs.get("regex")
        if not url or not pattern:
            entry["status"] = "config_error"
            return result(2, f"{project}: page_regex 缺少 url/regex",
                          project=project)
        try:
            r = requests.get(url, headers={"User-Agent": UA_BROWSER,
                                           "Accept-Language": "zh-CN,zh;q=0.9"},
                             timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            entry["status"] = "network_error"
            return result(3, f"{project}: 页面网络错误 {e}", project=project)
        if r.status_code != 200:
            entry["status"] = f"http_{r.status_code}"
            return result(3, f"{project}: 页面 HTTP {r.status_code}",
                          project=project)
        matches = re.findall(pattern, r.text)
        versions = _to_candidates(
            [m if isinstance(m, str) else (m[0] if m else "") for m in matches])
        return _finish_version_detect(cfg, entry, project, versions,
                                      f"page:{url}", label="页面最新")

    if vtype == "lanzou_folder":
        # 蓝奏云文件夹分享（第三方分发页）：页面 JS 下发一次性 token，
        # 复现其 filemoreajax 接口取文件列表，再按文件名抽版本号
        # （2026-10-16 实证 gndown 分享页；每页 50 条，最多翻 5 页）
        url = vs.get("url")
        if not url:
            entry["status"] = "config_error"
            return result(2, f"{project}: lanzou_folder 缺少 url 字段",
                          project=project)
        hdr = {"User-Agent": UA_BROWSER, "Accept-Language": "zh-CN,zh;q=0.9"}
        try:
            sess, page_text = _lanzou_fetch(url, hdr)
        except requests.RequestException as e:
            entry["status"] = "network_error"
            return result(3, f"{project}: 蓝奏云页面网络错误 {e}",
                          project=project)
        tok = lanzou_tokens(page_text)
        if not all(tok.get(k) for k in ("fid", "uid", "puid", "t", "k")):
            entry["status"] = "regex_miss"
            return result(3, f"{project}: 蓝奏云页面未取到接口 token"
                             f"（分享页结构可能已变）", project=project)
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        names: list[str] = []
        for pg in range(1, 6):
            data = {"lx": 2, "fid": tok["fid"], "uid": tok["uid"],
                    "puid": tok["puid"], "pg": pg, "rep": "0",
                    "t": tok["t"], "k": tok["k"], "up": 1, "vip": "0",
                    "webfoldersign": ""}
            try:
                r = sess.post(f"{host}/filemoreajax.php",
                              params={"file": tok["fid"]}, data=data,
                              headers=dict(hdr, Referer=url,
                                           **{"X-Requested-With":
                                              "XMLHttpRequest"}),
                              timeout=REQUEST_TIMEOUT)
                j = r.json()
            except (requests.RequestException, ValueError) as e:
                entry["status"] = "network_error"
                return result(3, f"{project}: 蓝奏云列表接口失败 {e}",
                              project=project)
            if str(j.get("zt")) != "1":
                entry["status"] = "api_error"
                return result(3, f"{project}: 蓝奏云接口 zt={j.get('zt')}"
                                 f" info={j.get('info')}", project=project)
            rows = j.get("text") or []
            names.extend(row.get("name_all", "") for row in rows)
            if len(rows) < 50:
                break
        versions = _versions_from_names(names, vs.get("version_regex", ""))
        return _finish_version_detect(cfg, entry, project, versions,
                                      f"lanzou:{url}")

    if vtype == "ctfile_dir":
        # 城通网盘分享目录（第三方重打包分发）：官方 SPA 的数据接口，
        # 纯 query 参数即可复现（2026-10-16 实证，无需 authority 令牌）
        url = vs.get("url") or "https://urlapi.ctfile.com/api/v2/listing"
        params = dict(vs.get("params") or {})
        if not params:
            entry["status"] = "config_error"
            return result(2, f"{project}: ctfile_dir 缺少 params 字段",
                          project=project)
        hdr = {"User-Agent": UA_BROWSER,
               "Accept": "application/json, text/plain, */*"}
        if vs.get("referer"):
            hdr["Referer"] = vs["referer"]
        length = int(params.get("length") or 20)
        names: list[str] = []
        start = 0
        for _ in range(5):
            try:
                r = requests.get(url, params=dict(params, start=str(start),
                                                  length=str(length)),
                                 headers=hdr, timeout=REQUEST_TIMEOUT)
                j = r.json()
            except (requests.RequestException, ValueError) as e:
                entry["status"] = "network_error"
                return result(3, f"{project}: 城通接口失败 {e}", project=project)
            if str(j.get("code")) != "200":
                entry["status"] = "api_error"
                return result(3, f"{project}: 城通接口 code={j.get('code')}"
                                 f" msg={j.get('msg')}", project=project)
            data = j.get("data") or {}
            rows = data.get("rows") or []
            names.extend(row.get("name", "") for row in rows)
            if len(rows) < length or not data.get("hasMore"):
                break
            start += length
        versions = _versions_from_names(names, vs.get("version_regex", ""))
        return _finish_version_detect(cfg, entry, project, versions,
                                      f"ctfile:{params.get('id', '')}")

    # manual 未验证：诚实标记，不猜测版本
    entry["status"] = "needs_manual"
    entry.pop("download_url", None)
    return result(0, f"{project}: 无可靠在线版本源，标记 needs_manual"
                     f"（人工下载后 ingest 接管）", project=project,
                  status="needs_manual")


def cmd_detect(args) -> dict:
    state = load_state()
    state.setdefault("projects", {})
    projects = [args.project] if args.project else list_projects()
    if not projects:
        return result(2, "Configs 目录无项目配置")
    summary = []
    rc = 0
    for name in projects:
        try:
            cfg = load_config(name)
        except FileNotFoundError as e:
            log.warning("%s", e)
            rc = 2
            continue
        r = detect_one(cfg, state)
        summary.append({"project": name, "exit_code": r["exit_code"],
                        "status": state["projects"][name].get("status"),
                        "update_available":
                            state["projects"][name].get("update_available")})
        rc = max(rc, min(r["exit_code"], 1))  # 单项目失败不掩盖整体
    save_state(state)
    ok = sum(1 for s in summary if s["exit_code"] == 0)
    return result(rc, f"detect 完成 {ok}/{len(summary)}", projects=summary,
                  state_file=str(STATE_FILE))


# ---------------------------------------------------------------- download / ingest

def cmd_download(args) -> dict:
    cfg = load_config(args.project)
    state = load_state()
    entry = state.get("projects", {}).get(args.project, {})
    url = args.url or entry.get("download_url")
    if not url:
        return result(2, f"{args.project}: 无 download_url"
                         f"（先 detect 或 --url 显式指定）")
    dl_dir = STAGING / args.project / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    fname = url.split("?")[0].rstrip("/").split("/")[-1] or "download.bin"
    dst = dl_dir / fname
    ev = evidence_dir(args.project, new_run_id(), "download")
    log.info("下载 %s → %s", url, dst)
    h = hashlib.sha256()
    size = 0
    try:
        with requests.get(url, stream=True, timeout=REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            with open(dst, "wb") as f:
                for chunk in r.iter_content(DOWNLOAD_CHUNK):
                    f.write(chunk)
                    h.update(chunk)
                    size += len(chunk)
    except requests.RequestException as e:
        return result(3, f"下载失败: {e}", url=url)
    digest = h.hexdigest()
    meta = {"project": args.project, "url": url, "file": str(dst),
            "size": size, "sha256": digest, "downloaded_at": now_iso(),
            "hash_note": "仅本地计算哈希，未验证官方真实性"
                         "（官方未提供可信哈希基准时）"}
    atomic_write_json(ev / "download.json", meta)
    entry.update({"package_file": str(dst), "package_sha256": digest,
                  "package_size": size})
    if args.version:
        entry["latest_version"] = args.version
    state.setdefault("projects", {})[args.project] = entry
    save_state(state)
    return result(0, f"下载完成 {fname}（{size} 字节，sha256={digest[:16]}…）",
                  file=str(dst), sha256=digest, evidence=str(ev))


def cmd_ingest(args) -> dict:
    """人工下载的安装包接管（半自动通道，腾讯会议先例）"""
    cfg = load_config(args.project)
    src = Path(args.file)
    if not src.is_file():
        return result(2, f"文件不存在: {src}")
    dl_dir = STAGING / args.project / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    dst = dl_dir / src.name
    if args.execute:
        shutil.copy2(src, dst)
    digest = sha256_file(src)
    ev = evidence_dir(args.project, new_run_id(), "ingest")
    meta = {"project": args.project, "source_file": str(src),
            "staged_file": str(dst), "version": args.version,
            "size": src.stat().st_size, "sha256": digest,
            "ingested_at": now_iso(), "dry_run": not args.execute,
            "hash_note": "人工下载来源，仅本地计算哈希"}
    atomic_write_json(ev / "ingest.json", meta)
    state = load_state()
    entry = state.setdefault("projects", {}).setdefault(args.project, {})
    entry.update({"package_file": str(dst), "package_sha256": digest,
                  "package_size": src.stat().st_size})
    if args.version:
        entry["latest_version"] = args.version
        entry["update_available"] = True
    save_state(state)
    return result(0, f"ingest {'完成' if args.execute else '（dry-run 预检）'}"
                     f": {src.name} sha256={digest[:16]}…",
                  file=str(dst), sha256=digest, evidence=str(ev),
                  dry_run=not args.execute)


# ---------------------------------------------------------------- extract

def _extract_zip(pkg: Path, out: Path) -> None:
    with zipfile.ZipFile(pkg) as zf:
        zf.extractall(out)


def _extract_nsis(pkg: Path, out: Path) -> dict:
    """NSIS 静态解包；electron-builder 双层包按名精确提取 app-64.7z
    （禁止 sorted()[0]——app-32.7z 字典序在前会取错 32 位包）"""
    seven = find_7z()
    if not seven:
        return {"exit_code": 2, "msg": "未找到 7-Zip（PATH 或常见安装路径）"}
    layer1 = out / "_layer1"
    layer1.mkdir(parents=True, exist_ok=True)

    def run7z(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run([seven, *argv], shell=False, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=1800)
    r = run7z(["x", str(pkg), f"-o{layer1}", "-y"])
    if r.returncode != 0:
        return {"exit_code": 3, "msg": f"7z 第一层解包失败: {r.stderr[:300]}"}
    plugins = layer1 / "$PLUGINSDIR"
    app64 = None
    if plugins.is_dir():
        for f in plugins.iterdir():
            if f.name.lower() == "app-64.7z":  # 按名精确匹配
                app64 = f
                break
    if app64:
        # 双层 electron-builder：解第二层
        layer2 = out / "_layer2"
        r2 = run7z(["x", str(app64), f"-o{layer2}", "-y"])
        if r2.returncode != 0:
            return {"exit_code": 3,
                    "msg": f"7z 第二层解包失败: {r2.stderr[:300]}"}
        final = out / "app"
        layer2.rename(final)
        shutil.rmtree(layer1, ignore_errors=True)
        return {"exit_code": 0, "msg": "NSIS 双层解包完成", "dir": str(final),
                "layers": 2}
    # 单层 NSIS
    final = out / "app"
    layer1.rename(final)
    return {"exit_code": 0, "msg": "NSIS 单层解包完成", "dir": str(final),
            "layers": 1}


def _extract_inno(pkg: Path, out: Path) -> dict:
    """Inno Setup 静态解包（innounp）。占位目录 {app}/{code_*} 合并为
    程序树；{tmp}/{win}/{sys} 等系统目标不取（便携包不需要）。"""
    inno = find_innounp()
    if not inno:
        return {"exit_code": 2, "msg": "未找到 innounp；请设置环境变量 "
                                       "PAF_INNOUNP 指向 innounp.exe，"
                                       "或将其加入 PATH"}
    raw = out / "_inno_raw"
    raw.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([inno, "-x", f"-d{raw}", str(pkg)], shell=False,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    if r.returncode != 0:
        return {"exit_code": 3,
                "msg": f"innounp 解包失败: {(r.stderr or r.stdout)[:300]}"}
    final = out / "app"
    final.mkdir(exist_ok=True)
    merged: list[str] = []
    skipped: list[str] = []
    for sub in sorted(raw.iterdir()):
        if not sub.is_dir():
            continue
        name_l = sub.name.lower()
        if name_l == "{app}" or name_l.startswith("{code_"):
            # 程序载荷：合并进 final
            for item in sub.iterdir():
                dst = final / item.name
                if dst.exists():
                    shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
                shutil.move(str(item), str(dst))
            merged.append(sub.name)
        else:
            skipped.append(sub.name)
    if not merged:
        return {"exit_code": 3, "msg": "innounp 解出内容无 {app}/{code_*} "
                                       f"程序载荷目录（仅有 {skipped}）"}
    shutil.rmtree(raw, ignore_errors=True)
    return {"exit_code": 0, "msg": f"Inno 解包完成（合并 {merged}）",
            "dir": str(final), "layers": 1, "skipped_targets": skipped}


def cmd_extract(args) -> dict:
    cfg = load_config(args.project)
    state = load_state()
    entry = state.get("projects", {}).get(args.project, {})
    pkg = Path(args.file or entry.get("package_file") or "")
    if not pkg.is_file():
        return result(2, f"安装包不存在: {pkg}（先 download 或 ingest）")
    ptype = args.package_type or cfg.get("package_type", "unknown")
    workdir = STAGING / args.project / "extract" / new_run_id()
    workdir.mkdir(parents=True, exist_ok=True)

    if ptype in ("zip",):
        final = workdir / "app"
        final.mkdir(exist_ok=True)
        _extract_zip(pkg, final)
        info = {"exit_code": 0, "msg": "ZIP 解包完成", "dir": str(final),
                "layers": 1}
    elif ptype in ("7z", "7z_sfx"):
        # 7z_sfx：PE 内嵌 7z 压缩流（Feishu/Zen 安装器）
        # 7z    ：纯 7z 归档（蓝奏云分享的 renamer_pro_*-Portable.7z）——同一通道
        seven = find_7z()
        if not seven:
            return result(2, "未找到 7-Zip（PATH 或常见安装路径）")
        final = workdir / "app"
        final.mkdir(exist_ok=True)
        r7 = subprocess.run([seven, "x", str(pkg), f"-o{final}", "-y"],
                            shell=False, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=1800)
        if r7.returncode != 0:
            return result(3, f"{ptype} 解包失败: {(r7.stderr or '')[:300]}")
        info = {"exit_code": 0, "msg": f"{ptype} 解包完成", "dir": str(final),
                "layers": 1}
    elif ptype in ("nsis", "electron_installer"):
        info = _extract_nsis(pkg, workdir)
    elif ptype == "inno":
        info = _extract_inno(pkg, workdir)
    else:
        return result(2, f"package_type={ptype} 需人工解包"
                         f"（extract_strategy=manual_fallback），"
                         f"解出后用 --dir 指定候选目录", )
    if info["exit_code"] != 0:
        return result(info["exit_code"], info["msg"])
    app_dir = Path(info["dir"])

    # entry_exe 定位与 PE 位数复核（x64 包必须 0x8664）
    entry_rel = cfg.get("entry_exe", "")
    exe_found = list(app_dir.rglob(Path(entry_rel).name)) if entry_rel else []
    pe = pe_machine(exe_found[0]) if exe_found else None
    pe_note = {0x8664: "x64", 0x14C: "x86"}.get(pe, f"未知({pe})")
    if pe == 0x14C:
        log.warning("取到 32 位主程序 %s——核对是否解错层/解错包",
                    exe_found[0])
    ev = evidence_dir(args.project, new_run_id(), "extract")
    files = dir_manifest(app_dir)
    meta = {"project": args.project, "package": str(pkg),
            "package_type": ptype, "layers": info["layers"],
            "candidate_dir": str(app_dir), "file_count": len(files),
            "entry_exe_found": str(exe_found[0]) if exe_found else None,
            "pe_machine": pe_note, "extracted_at": now_iso()}
    atomic_write_json(ev / "extract.json", meta)
    entry["candidate_dir"] = str(app_dir)
    state.setdefault("projects", {})[args.project] = entry
    save_state(state)
    return result(0, f"extract 完成：{len(files)} 文件，主程序 {pe_note}",
                  candidate_dir=str(app_dir), evidence=str(ev),
                  pe_machine=pe_note, file_count=len(files))


# ---------------------------------------------------------------- diff

def cmd_diff(args) -> dict:
    cfg = load_config(args.project)
    state = load_state()
    entry = state.get("projects", {}).get(args.project, {})
    cand = Path(args.candidate or entry.get("candidate_dir") or "")
    if not cand.is_dir():
        return result(2, f"候选目录不存在: {cand}（先 extract）")
    # 旧版程序层：以 entry_exe 的顶层程序目录为比较基准
    cur_root = app_root(cfg) / cfg.get("app_subdir", "")
    old = dir_manifest(cur_root)
    new = dir_manifest(cand)
    old_set, new_set = set(old), set(new)
    added = sorted(new_set - old_set)
    removed = sorted(old_set - new_set)
    changed = sorted(p for p in old_set & new_set
                     if old[p]["size"] != new[p]["size"])
    risks: list[dict] = []
    for f in added:
        if RISK_EXCLUDE_DIRS.search(f):
            continue  # 库内源文件不参与高危判定
        for kind, pat in RISK_FILE_PATTERNS.items():
            if pat.search(f):
                risks.append({"type": kind, "file": f,
                              "note": "新增更新器/服务组件"})
    for f in removed:
        if not RISK_EXCLUDE_DIRS.search(f) and \
                RISK_FILE_PATTERNS["updater"].search(f):
            risks.append({"type": "updater_removed", "file": f,
                          "note": "更新器组件被移除（需重新执行禁用处置）"})
    ev = evidence_dir(args.project, new_run_id(), "diff")
    rep = {"project": args.project, "old_dir": str(cur_root),
           "candidate_dir": str(cand),
           "old_files": len(old), "new_files": len(new),
           "added": len(added), "removed": len(removed),
           "changed": len(changed), "risks": risks,
           "risk_level": "high" if risks else "normal",
           "added_list": added[:500], "removed_list": removed[:500],
           "diffed_at": now_iso()}
    atomic_write_json(ev / "diff.json", rep)
    entry["last_diff"] = {"risks": len(risks), "evidence": str(ev)}
    # 命中高危 → release_policy 强制 manual_confirm
    if risks and cfg.get("release_policy") == "auto":
        entry["release_policy"] = "manual_confirm"
        log.warning("%s: 命中 %d 项高危差异，release_policy 升级为 "
                    "manual_confirm", args.project, len(risks))
    state.setdefault("projects", {})[args.project] = entry
    save_state(state)
    return result(0, f"diff 完成：+{len(added)} -{len(removed)} "
                     f"~{len(changed)}，高危 {len(risks)} 项",
                  risk_count=len(risks), risks_preview=risks[:20],
                  evidence=str(ev))


# ---------------------------------------------------------------- test（冒烟）

def _scan_residue(roots: list[Path], since: float) -> list[str]:
    """扫描 since 之后的新增文件，过滤噪声白名单"""
    hits: list[str] = []
    pats = [re.compile(p, re.I) for p in NOISE_PATTERNS]
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not any(p.search(d) for p in pats)]
            for fn in filenames:
                fp = Path(dirpath) / fn
                try:
                    if fp.stat().st_mtime >= since:
                        rel = str(fp)
                        if not any(p.search(rel) for p in pats):
                            hits.append(rel)
                except OSError:
                    continue
    return hits


def cmd_test(args) -> dict:
    """候选版本冒烟：重定向 APPDATA/LOCALAPPDATA/TEMP（严禁 USERPROFILE），
    两次启动 + 浸泡 + 残留扫描 + 按路径前缀终止"""
    cfg = load_config(args.project)
    state = load_state()
    entry = state.get("projects", {}).get(args.project, {})
    cand = Path(args.candidate or entry.get("candidate_dir") or "")
    entry_rel = cfg.get("entry_exe", "")
    exes = list(cand.rglob(Path(entry_rel).name)) if entry_rel else []
    if not exes:
        return result(2, f"候选目录找不到 {entry_rel}（先 extract）")
    exe = exes[0]
    soak = args.soak
    smoke_env = STAGING / args.project / "smoke-env"
    smoke_env.mkdir(parents=True, exist_ok=True)
    ev = evidence_dir(args.project, new_run_id(), "test")
    started = datetime.now().timestamp()
    checks: list[dict] = []
    residues: list[str] = []

    env = dict(os.environ)
    for var, sub in (("APPDATA", "AppData/Roaming"),
                     ("LOCALAPPDATA", "AppData/Local"), ("TEMP", "Temp"),
                     ("TMP", "Temp")):
        d = smoke_env / sub
        d.mkdir(parents=True, exist_ok=True)
        env[var] = str(d)
    # 严禁重定向 USERPROFILE（Electron app.getPath('appData') 崩溃机理）

    launch_args = [str(exe), *cfg.get("launcher_args", [])]
    for round_no in (1, 2):
        try:
            proc = subprocess.Popen(launch_args, shell=False, env=env,
                                    cwd=str(exe.parent),
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        except OSError as e:
            checks.append({"round": round_no, "launch": False, "err": str(e)})
            break
        alive = False
        for _ in range(args.launch_timeout):
            procs = processes_under(exe.parent)
            if procs:
                alive = True
                break
            if proc.poll() is not None and not procs:
                break
            psutil.wait_procs([proc], timeout=1)
        checks.append({"round": round_no, "launch": alive,
                       "pid": proc.pid, "processes":
                           len(processes_under(exe.parent))})
        if alive:
            import time
            time.sleep(soak)
        kill_by_path_prefix(exe.parent)
    # 残留扫描（宿主两大路径，排除 smoke-env 与噪声）。
    # 注：原始候选 exe 未经 PAL 启动器，Electron 应用经 SHGetKnownFolderPath
    # 写真实 %APPDATA% 属预期行为，不作为冒烟门禁；便携级泄漏由成品包
    # 动态落盘验证（data_persist_test）负责。
    user = Path(os.environ["USERPROFILE"])
    residues = _scan_residue(
        [Path(os.environ.get("APPDATA", user / "AppData/Roaming")),
         Path(os.environ.get("LOCALAPPDATA", user / "AppData/Local"))],
        started)
    passed = (len(checks) == 2 and all(c.get("launch") for c in checks))
    rep = {"project": args.project, "exe": str(exe), "checks": checks,
           "soak_seconds": soak, "residue_count": len(residues),
           "residues": residues[:200], "passed": passed,
           "residue_note": "原始 exe 直跑（无 PAL 重定向），残留仅作参考",
           "tested_at": now_iso()}
    atomic_write_json(ev / "test.json", rep)
    entry["last_test"] = {"passed": passed, "evidence": str(ev)}
    state.setdefault("projects", {})[args.project] = entry
    save_state(state)
    return result(0 if passed else 4,
                  f"冒烟{'通过' if passed else '未通过'}："
                  f"启动 {sum(1 for c in checks if c.get('launch'))}/2 轮，"
                  f"残留 {len(residues)} 项",
                  passed=passed, evidence=str(ev), residues=residues[:50])


# ---------------------------------------------------------------- stage

def cmd_stage(args) -> dict:
    """候选归档：test 通过后将候选目录归档为 Staging\\<项目>\\v<版本>-candidate"""
    cfg = load_config(args.project)
    state = load_state()
    entry = state.get("projects", {}).get(args.project, {})
    if not entry.get("last_test", {}).get("passed"):
        return result(5, f"{args.project}: 无通过的冒烟记录，禁止 stage")
    cand = Path(entry.get("candidate_dir") or "")
    if not cand.is_dir():
        return result(2, f"候选目录不存在: {cand}")
    version = args.version or entry.get("latest_version") or "unknown"
    dst = STAGING / args.project / f"v{version}-candidate"
    if dst.exists():
        shutil.rmtree(dst)
    if args.execute:
        shutil.move(str(cand), str(dst))
    ev = evidence_dir(args.project, new_run_id(), "stage")
    atomic_write_json(ev / "stage.json", {
        "project": args.project, "version": version,
        "staged_dir": str(dst), "dry_run": not args.execute,
        "staged_at": now_iso()})
    entry["staged_dir"] = str(dst)
    entry["staged_version"] = version
    state.setdefault("projects", {})[args.project] = entry
    save_state(state)
    return result(0, f"stage {'完成' if args.execute else '（dry-run 预检）'}"
                     f"：v{version} → {dst}", staged_dir=str(dst),
                  dry_run=not args.execute)


# ---------------------------------------------------------------- release

def cmd_release(args) -> dict:
    """门禁发布：冒烟 PASS + Data 快照 + 无运行进程 + 备份旧 App + 切换候选。
    dry_run 默认 True，须 --execute 显式落地。"""
    cfg = load_config(args.project)
    state = load_state()
    entry = state.get("projects", {}).get(args.project, {})
    run_id = new_run_id()
    ev = evidence_dir(args.project, run_id, "release")

    # 门禁一：冒烟通过
    if not entry.get("last_test", {}).get("passed"):
        return result(5, "门禁拒绝：无通过的冒烟记录", evidence=str(ev))
    # 门禁二：高危差异需人工确认
    risks = entry.get("last_diff", {}).get("risks", 0)
    if risks and not args.allow_risk:
        return result(5, f"门禁拒绝：{risks} 项高危差异未确认"
                         f"（--allow-risk 显式放行）", evidence=str(ev))
    # 门禁三：发布策略
    policy = entry.get("release_policy",
                       cfg.get("release_policy", "manual_confirm"))
    if policy == "blocked":
        return result(5, "门禁拒绝：release_policy=blocked", evidence=str(ev))
    if policy == "manual_confirm" and not args.confirm:
        return result(5, "门禁拒绝：manual_confirm 策略须 --confirm",
                      evidence=str(ev))

    staged = Path(entry.get("staged_dir") or "")
    if not staged.is_dir():
        return result(2, f"候选未 stage: {staged}")
    pkg = pkg_dir(cfg)
    # 门禁四：无运行中的包进程
    running = processes_under(pkg)
    if running:
        return result(5, f"门禁拒绝：{len(running)} 个包进程仍在运行"
                         f"（先关闭再发布）",
                      running=[p.get("pid") for p in running])

    data_dir = pkg / cfg.get("data_dir", "Data")
    app_sub = cfg.get("app_subdir", "")
    live_app = app_root(cfg) / app_sub
    old_version = cfg.get("current_version", "unknown")
    new_version = entry.get("staged_version", "unknown")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = pkg / "Backups" / f"{old_version}-{ts}"

    # Data 快照（轻量清单，不复制数据本身——Data 神圣不可侵犯，只读）
    data_snap = dir_manifest(data_dir, with_hash=False)
    atomic_write_json(ev / "data_snapshot_pre.json",
                      {"project": args.project, "files": len(data_snap),
                       "manifest": data_snap})

    steps: list[str] = []
    if args.execute:
        # 备份当前 App → Backups
        backup_dir.mkdir(parents=True, exist_ok=True)
        if live_app.exists():
            os.rename(live_app, backup_dir / live_app.name)
            steps.append(f"备份 {live_app.name} → {backup_dir}")
        # 候选移入
        shutil.move(str(staged), str(live_app))
        steps.append(f"切换 {staged} → {live_app}")
        # 更新 appinfo.ini 版本字段（启动器 ini 运行时读取，无需重编译）
        appinfo = pkg / "App" / "AppInfo" / "appinfo.ini"
        if appinfo.is_file() and new_version != "unknown":
            txt = appinfo.read_text(encoding="utf-8-sig")
            for field in ("Version", "VersionFormat"):
                txt = re.sub(rf"(?m)^{field}=.*$", f"{field}={new_version}",
                             txt)
            pv = new_version if new_version.count(".") >= 3 \
                else new_version + ".0"
            txt = re.sub(r"(?m)^PackageVersion=.*$",
                         f"PackageVersion={pv}", txt)
            appinfo.write_text(txt, encoding="utf-8")
            steps.append("appinfo.ini 版本字段已更新")
        # version.json 原子写
        atomic_write_json(pkg / "version.json", {
            "current_version": new_version, "previous_version": old_version,
            "released_at": now_iso(), "run_id": run_id,
            "channel": cfg.get("update_channel", "stable")})
        # Backups 保留最近 3 版
        _prune_backups(pkg / "Backups", keep=3, steps=steps)
        # changelog 追加
        CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHANGELOG, "a", encoding="utf-8") as f:
            f.write(f"\n## {args.project} v{old_version} → v{new_version}"
                    f"（{now_iso()}，run {run_id}）\n"
                    f"- 备份：{backup_dir}\n- 证据：{ev}\n"
                    f"- 回滚：python scripts\\update_engine.py rollback "
                    f"{args.project} --to {old_version} --execute\n")
        steps.append("changelog 已追加")
    else:
        steps.append("dry-run：不执行文件切换")

    atomic_write_json(ev / "release.json", {
        "project": args.project, "old_version": old_version,
        "new_version": new_version, "dry_run": not args.execute,
        "steps": steps, "released_at": now_iso()})
    if args.execute:
        entry.update({"current_version": new_version,
                      "update_available": False})
        entry.pop("staged_dir", None)
        state.setdefault("projects", {})[args.project] = entry
        save_state(state)
    return result(0, f"release {'完成' if args.execute else '（dry-run 预检）'}"
                     f"：v{old_version} → v{new_version}",
                  steps=steps, evidence=str(ev), dry_run=not args.execute)


def _prune_backups(backups: Path, keep: int, steps: list[str]) -> None:
    if not backups.is_dir():
        return
    snaps = sorted((d for d in backups.iterdir() if d.is_dir()),
                   key=lambda d: d.name)
    while len(snaps) > keep:
        victim = snaps.pop(0)
        shutil.rmtree(victim, ignore_errors=True)
        steps.append(f"清理旧备份 {victim.name}")


# ---------------------------------------------------------------- rollback

def cmd_rollback(args) -> dict:
    """回滚：Backups 中指定版本换回 App 层（dry_run 默认 True）"""
    cfg = load_config(args.project)
    pkg = pkg_dir(cfg)
    backups = pkg / "Backups"
    if not backups.is_dir():
        return result(2, f"无 Backups 目录: {backups}")
    cands = sorted(d for d in backups.iterdir()
                   if d.is_dir() and d.name.startswith(f"{args.to}-"))
    if not cands:
        avail = [d.name for d in backups.iterdir() if d.is_dir()]
        return result(2, f"Backups 中无 {args.to} 版本快照，现有: {avail}")
    chosen = cands[-1]
    running = processes_under(pkg)
    if running:
        return result(5, f"拒绝回滚：{len(running)} 个包进程仍在运行")
    app_sub = cfg.get("app_subdir", "")
    live_app = app_root(cfg) / app_sub
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    quarantine = backups / f"rolledback-{ts}"
    ev = evidence_dir(args.project, new_run_id(), "rollback")
    steps: list[str] = []
    if args.execute:
        quarantine.mkdir(parents=True, exist_ok=True)
        if live_app.exists():
            os.rename(live_app, quarantine / live_app.name)
            steps.append(f"现行版本隔离 → {quarantine.name}")
        inner = chosen / live_app.name
        os.rename(inner, live_app)
        steps.append(f"恢复 {chosen.name} → {live_app}")
        if not any(chosen.iterdir()):
            chosen.rmdir()
        atomic_write_json(pkg / "version.json", {
            "current_version": args.to,
            "rolled_back_at": now_iso(),
            "rollback_evidence": str(ev)})
        with open(CHANGELOG, "a", encoding="utf-8") as f:
            f.write(f"\n## {args.project} 回滚至 v{args.to}"
                    f"（{now_iso()}）\n- 证据：{ev}\n")
    else:
        steps.append("dry-run：不执行文件切换")
    atomic_write_json(ev / "rollback.json", {
        "project": args.project, "to": args.to, "from_backup": str(chosen),
        "dry_run": not args.execute, "steps": steps,
        "rolled_back_at": now_iso()})
    return result(0, f"rollback {'完成' if args.execute else '（dry-run 预检）'}"
                     f"：→ v{args.to}（{chosen.name}）",
                  steps=steps, evidence=str(ev), dry_run=not args.execute)


# ---------------------------------------------------------------- report

def cmd_report(args) -> dict:
    state = load_state()
    projects = state.get("projects", {})
    rows = []
    for name in sorted(set(list_projects()) | set(projects)):
        e = projects.get(name, {})
        rows.append({
            "project": name,
            "current": e.get("current_version", "-"),
            "latest": e.get("latest_version", "-"),
            "status": e.get("status", "未检测"),
            "update_available": e.get("update_available", False),
            "policy": e.get("release_policy", "-"),
            "last_checked": e.get("last_checked_at", "-"),
        })
    lines = ["# 便携软件更新状态报告", "",
             f"- 生成时间：{now_iso()}",
             f"- 状态数据源：{STATE_FILE}", "",
             "| 项目 | 当前版本 | 最新版本 | 状态 | 有更新 | 发布策略 | 最后检测 |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['project']} | {r['current']} | {r['latest']} "
            f"| {r['status']} | {'是' if r['update_available'] else '否'} "
            f"| {r['policy']} | {r['last_checked']} |")
    n_manual = sum(1 for r in rows if r["status"] == "needs_manual")
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    lines += ["", f"- 在线检测源覆盖：{n_ok}/{len(rows)}",
              f"- 待人工接入（needs_manual）：{n_manual}/{len(rows)}",
              "", "> needs_manual 项目：人工从官方渠道下载安装包后执行",
              "> `python scripts\\update_engine.py ingest <项目> "
              "--file <安装包> --version <版本号> --execute` 接管后续流程。"]
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"update_report-{datetime.now():%Y%m%d-%H%M%S}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return result(0, f"报告已生成：{out}", report=str(out),
                  online=n_ok, manual=n_manual, total=len(rows))


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="update_engine",
        description="便携软件自动化更新引擎（detect→download/ingest→extract"
                    "→diff→test→stage→release→rollback）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("detect", help="版本检测")
    sp.add_argument("--all", action="store_true", help="全部项目")
    sp.add_argument("--project", help="单个项目名")

    sp = sub.add_parser("download", help="下载与哈希校验")
    sp.add_argument("project")
    sp.add_argument("--url", help="显式下载地址（默认取 detect 结果）")
    sp.add_argument("--version", help="显式版本号")

    sp = sub.add_parser("ingest", help="人工下载的安装包接管（半自动通道）")
    sp.add_argument("project")
    sp.add_argument("--file", required=True, help="安装包路径")
    sp.add_argument("--version", help="版本号")
    sp.add_argument("--execute", action="store_true",
                    help="实际复制（默认 dry-run 预检）")

    sp = sub.add_parser("extract", help="解包提取")
    sp.add_argument("project")
    sp.add_argument("--file", help="安装包路径（默认取 download/ingest 结果）")
    sp.add_argument("--package-type", help="覆盖配置中的 package_type")

    sp = sub.add_parser("diff", help="新旧版本差异分析")
    sp.add_argument("project")
    sp.add_argument("--candidate", help="候选目录（默认取 extract 结果）")

    sp = sub.add_parser("test", help="候选版本冒烟测试")
    sp.add_argument("project")
    sp.add_argument("--candidate", help="候选目录（默认取 extract 结果）")
    sp.add_argument("--soak", type=int, default=30, help="浸泡秒数")
    sp.add_argument("--launch-timeout", type=int, default=40,
                    help="启动检测超时秒数")

    sp = sub.add_parser("stage", help="候选归档")
    sp.add_argument("project")
    sp.add_argument("--version", help="版本号（默认取 detect/ingest 结果）")
    sp.add_argument("--execute", action="store_true",
                    help="实际归档（默认 dry-run 预检）")

    sp = sub.add_parser("release", help="门禁发布与切换")
    sp.add_argument("project")
    sp.add_argument("--confirm", action="store_true",
                    help="manual_confirm 策略的人工确认")
    sp.add_argument("--allow-risk", action="store_true",
                    help="显式放行高危差异")
    sp.add_argument("--execute", action="store_true",
                    help="实际切换（默认 dry-run 预检）")

    sp = sub.add_parser("rollback", help="回滚至指定历史版本")
    sp.add_argument("project")
    sp.add_argument("--to", required=True, help="目标旧版本号")
    sp.add_argument("--execute", action="store_true",
                    help="实际回滚（默认 dry-run 预检）")

    sub.add_parser("report", help="生成更新状态报告")
    return p


HANDLERS = {"detect": cmd_detect, "download": cmd_download,
            "ingest": cmd_ingest, "extract": cmd_extract,
            "diff": cmd_diff, "test": cmd_test, "stage": cmd_stage,
            "release": cmd_release, "rollback": cmd_rollback,
            "report": cmd_report}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    args = build_parser().parse_args()
    if args.cmd == "detect" and not (args.all or args.project):
        print("detect 需 --all 或 --project", file=sys.stderr)
        return 2
    r = HANDLERS[args.cmd](args)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return r["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
