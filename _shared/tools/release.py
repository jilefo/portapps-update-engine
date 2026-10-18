# -*- coding: utf-8 -*-
r"""四平台自动发布工具 —— 准备产物 / 上传发行版。

设计前提（重要）
--------------
本仓库是「配方开源（MIT）+ 二进制不随仓库分发」模式：
  - 入库的是 portableapps/ 元数据 + _shared/ 工具链 + 文档（10.5 MB）
  - 59 GB 的 dist/ 可运行产物**不在仓库里**，CI 在新克隆上拿不到，也无法构建
因此 CI 自动发布的产物是**配方包**，不是便携程序本体：
    PortableApps-formula-v<版本>.zip   = git archive（全部入库文件）
    SHA256SUMS                          = 逐文件校验值
    RELEASE-NOTES.md                    = 从 CHANGELOG.md 节取本版条目
    release_manifest.json               = 机器可读元数据（版本、时间、各门禁结果）
便携程序本体的分发走 docs/06-开源与发布.md 的三个选项（GitHub/Gitee Releases
手工上传、网盘 + update.py 拉取、Gitee Releases），不在本流水线范围内。

用法
----
    python release.py prepare --out <目录> [--tag vX.Y.Z]
    python release.py upload  --dir <目录> --platform github|gitee|gitcode \
        --tag vX.Y.Z [--repo owner/name] [--prerelease] [--dry-run]

四大平台如何对接本脚本，见 docs/07-四平台自动发布.md。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                      # <Repo>
TOOLS = REPO / "_shared" / "tools"

# 产品根唯一解析处（dist 迁移后由它接管产品路径）。
sys.path.insert(0, str(REPO / "_shared"))
import _paths                                     # noqa: E402

UA = "PortableApps-release-bot/1.0 (+https://github.com/)"


def log(msg=""):
    print(msg, flush=True)


def die(msg, code=2):
    log("[FAIL] %s" % msg)
    sys.exit(code)


# ------------------------------------------------------------------ 版本
CHANGELOG_VER = re.compile(
    r"^##\s*\[(?P<ver>\d+\.\d+\.\d+)\]\s*[—-]\s*(?P<date>\d{4}-\d{2}-\d{2})")


def read_changelog_top():
    """取 CHANGELOG.md 最新一条：[版本, 日期, 正文]。

    正文取到下一个 `## [` 或 `## ` 之前，用于拼 Release Notes。
    """
    p = REPO / "CHANGELOG.md"
    if not p.is_file():
        return None
    lines = p.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines):
        m = CHANGELOG_VER.match(ln)
        if m:
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith("## "):
                    break
                body.append(nxt)
            while body and not body[0].strip():
                body.pop(0)
            while body and not body[-1].strip():
                body.pop()
            return m.group("ver"), m.group("date"), "\n".join(body).strip()
    return None


def norm(v):
    """规范成 4 段整数，兼容 PAL 的 4 段式与上游的 3 段式。"""
    if not v:
        return (0, 0, 0, 0)
    s = str(v).strip().lstrip("vV")
    s = re.sub(r"[bB]$", "", s)
    out = []
    for seg in s.split("-")[0].split("+")[0].split(".")[:4]:
        m = re.match(r"\d+", seg)
        out.append(int(m.group()) if m else 0)
    while len(out) < 4:
        out.append(0)
    return tuple(out[:4])


def appinfo_version(path):
    """读 appinfo.ini 的 PackageVersion。"""
    if not path.is_file():
        return None
    for enc in ("utf-8-sig", "utf-8", "utf-16-le", "mbcs"):
        try:
            txt = path.read_text(encoding=enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
        m = re.search(r"(?im)^\s*PackageVersion\s*=\s*([0-9][0-9.\-]*)", txt)
        if m:
            return m.group(1).strip()
    return None


# ------------------------------------------------------------------ 门禁
def run(cmd, **kw):
    log("  $ %s" % " ".join(str(c) for c in cmd))
    t0 = time.time()
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **kw)
    dt = time.time() - t0
    tail = (r.stdout or "").strip().splitlines()[-3:]
    log("    exit=%d  %.1fs" % (r.returncode, dt))
    for ln in tail:
        log("    | %s" % ln)
    return r


def packages():
    """仓库根下真正的包（含 portableapps/ 或 dist/ 的一级目录）。

    与 _paths.packages() 同源：迁移后仓库里仍有 portableapps/ 源树，
    产物已迁到产品根，故「有 dist/」只是历史兼容条件，不依赖它也能枚举全。
    """
    return _paths.packages()


def gates():
    """跑四道只读门禁；任一失败即中止发布。"""
    log("[1/5] 门禁校验")
    py = sys.executable
    pkgs = packages()
    if not pkgs:
        die("未枚举到任何包（含 portableapps/ 或 dist/ 的一级目录为 0）")
    log("    包数：%d" % len(pkgs))

    results = []
    specs = [
        [py, TOOLS / "audit_repo.py"],
        [py, TOOLS / "check_custom_nsh.py"],
        # test_structure.py 是【单包】脚本（_pkg.py 按参数/CWD 定包），
        # 必须逐包传包名；在仓库根裸跑会推出不存在的包名而假红。
        # 它在 _shared/scripts/ 而不在 tools/ 下。
    ]
    for cmd in specs:
        r = run(cmd)
        results.append({"cmd": Path(cmd[1]).name, "packages": None,
                        "exit": r.returncode, "ok": r.returncode == 0})
        if r.returncode != 0:
            die("门禁 %s 未通过（exit=%d），终止发布"
                % (Path(cmd[1]).name, r.returncode))

    tst = REPO / "_shared" / "scripts" / "test_structure.py"
    bad = []
    for pkg in pkgs:
        r = run([py, tst, pkg, "--ini-only"])
        if r.returncode != 0:
            bad.append(pkg)
    results.append({"cmd": "test_structure.py --ini-only",
                    "packages": len(pkgs),
                    "exit": 0 if not bad else 1,
                    "ok": not bad, "failed": bad})
    if bad:
        die("test_structure.py 未通过的包（%d/%d）：%s"
            % (len(bad), len(pkgs), ", ".join(bad)))

    r = run([py, TOOLS / "audit_before_push.py"])
    results.append({"cmd": "audit_before_push.py", "packages": None,
                    "exit": r.returncode, "ok": r.returncode == 0})
    if r.returncode != 0:
        die("门禁 audit_before_push.py 未通过（exit=%d），终止发布"
            % r.returncode)
    return results


def check_versions():
    """版本一致性：CHANGELOG / 每包 version.json / 每包 appinfo.ini。

    ★ 覆盖度必须自报：version.json 由更新引擎运行期写入，很多包可能根本没有。
      早先的实现只 glob 到几个就报「0 不一致」，属于瞒报覆盖面的假绿。
      现在按 packages() 的全集逐包找，找不到的明确计数并写进清单。
    """
    log("[2/5] 版本一致性")
    top = read_changelog_top()
    repo_ver = top[0] if top else None
    if not repo_ver:
        die("CHANGELOG.md 缺少 `## [X.Y.Z] — YYYY-MM-DD` 形式的版本条目")

    pkgs = packages()
    rows, bad, missing = [], [], []
    for pkg in pkgs:
        # version.json 由更新引擎写进产品目录；迁移后跟随产品根
        vj = _paths.product_dir(pkg) / "version.json"
        ai = appinfo_version(REPO / pkg / "portableapps/App/AppInfo/appinfo.ini")
        if ai is None:
            ai = appinfo_version(_paths.product_dir(pkg) /
                                 "App/AppInfo/appinfo.ini")
        if not vj.is_file():
            missing.append(pkg)
            rows.append((pkg, None, ai or "-"))
            continue
        try:
            cur = json.loads(vj.read_text(encoding="utf-8")).get("current_version")
        except Exception as e:
            bad.append("%s: version.json 解析失败 %s" % (pkg, e))
            continue
        if ai is not None and norm(cur) != norm(ai):
            bad.append("%s: version.json=%s 与 appinfo.ini=%s 不一致"
                       % (pkg, cur, ai))
        rows.append((pkg, cur, ai or "-"))

    have = len(rows) - len(missing)
    log("    仓库版本（CHANGELOG 顶部）: %s" % repo_ver)
    log("    覆盖度: %d/%d 个包有 version.json" % (have, len(pkgs)))
    log("    已核对 %d 个，不一致 %d 个" % (have, len(bad)))
    if missing:
        log("    [i] 无 version.json 的包（%d 个）：%s"
            % (len(missing), ", ".join(missing)))
    for b in bad:
        log("    [X] %s" % b)
    if bad:
        die("版本一致性校验失败，终止发布（共 %d 项）" % len(bad))
    return repo_ver, rows, top


# ------------------------------------------------------------------ 产物
def sha256(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def build_artifact(outdir, tag, repo_ver, notes, gate_res, vrows):
    log("[3/5] 组装产物 → %s" % outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = "PortableApps-formula-%s" % tag
    zpath = outdir / (base + ".zip")

    # git archive 只收入库文件，天然排除 dist/ 二进制与 Data/
    git = "git"
    r = subprocess.run([git, "archive", "--format=zip", "-o", str(zpath),
                        "HEAD"], cwd=str(REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die("git archive 失败: %s" % (r.stderr or r.stdout))

    # Release Notes
    (outdir / "RELEASE-NOTES.md").write_text(
        "# PortableApps 配方 %s\n\n%s\n" % (tag, notes or "(无)"), encoding="utf-8")

    # 机器可读清单（含门禁结论，供事后追溯"这个包是怎么发布出去的"）
    manifest = {
        "tag": tag,
        "repo_version": repo_ver,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tracked_files": int(subprocess.run(
            [git, "ls-files"], cwd=str(REPO), capture_output=True,
            text=True).stdout.count("\n")),
        "gates": gate_res,
        "packages": [{"name": n, "current": c, "appinfo": a}
                     for n, c, a in vrows],
        "artifacts": [],
    }

    files = sorted([p for p in outdir.iterdir() if p.is_file()])
    sums = []
    for p in files:
        if p.name == "SHA256SUMS":
            continue
        d = sha256(p)
        sums.append("%s  %s" % (d, p.name))
        manifest["artifacts"].append(
            {"file": p.name, "bytes": p.stat().st_size, "sha256": d})
    (outdir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    manifest["artifacts"].append(
        {"file": "SHA256SUMS", "bytes": (outdir / "SHA256SUMS").stat().st_size,
         "sha256": sha256(outdir / "SHA256SUMS")})
    (outdir / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for a in manifest["artifacts"]:
        log("    %-42s %10d B  %s" % (a["file"], a["bytes"], a["sha256"][:16]))
    return manifest


# ------------------------------------------------------------------ 上传
def _api(url, method="GET", data=None, headers=None, token=None, timeout=120):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if token:
        h["Authorization"] = "Bearer %s" % token
    if headers:
        h.update(headers)
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            h["Content-Type"] = "application/json"
        else:
            body = data if isinstance(data, bytes) else str(data).encode()
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct and raw:
                return resp.status, json.loads(raw.decode("utf-8"))
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, raw.decode("utf-8", "replace")


def _multipart(fields, filefield, filepath):
    """构造 multipart/form-data（Gitee attach_files 用）。"""
    b = "----portableapps%d" % int(time.time())
    out = []
    for k, v in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\""
                    "\r\n\r\n%s\r\n" % (b, k, v)).encode())
    fn = filepath.name
    out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                "filename=\"%s\"\r\nContent-Type: application/octet-stream"
                "\r\n\r\n" % (b, filefield, fn)).encode())
    out.append(filepath.read_bytes())
    out.append(("\r\n--%s--\r\n" % b).encode())
    return b"".join(out), "multipart/form-data; boundary=%s" % b


def upload(repo, tag, platform, outdir, token, dry=False, prerelease=False):
    owner, _, name = repo.partition("/")
    manifest = json.loads((outdir / "release_manifest.json").read_text("utf-8"))
    notes = (outdir / "RELEASE-NOTES.md").read_text("utf-8")
    assets = [Path(outdir) / a["file"] for a in manifest["artifacts"]]
    assets = [p for p in assets if p.is_file()]

    log("[4/5] 上传到 %s（%s）" % (platform, repo))

    if platform == "github":
        base = "https://api.github.com"
        st, rel = _api("%s/repos/%s/%s/releases" % (base, owner, name),
                       "POST", {"tag_name": tag, "name": tag, "body": notes,
                                "prerelease": prerelease, "draft": False},
                       token=token)
        if st not in (200, 201):
            die("创建 GitHub Release 失败 HTTP %s: %s" % (st, str(rel)[:400]))
        up = rel["upload_url"].split("{")[0]
        log("    release id=%s" % rel.get("id"))
        for p in assets:
            st, r = _api("%s?name=%s" % (up, urllib.parse.quote(p.name)),
                         "POST", p.read_bytes(),
                         headers={"Content-Type": "application/octet-stream"},
                         token=token)
            if st not in (200, 201):
                die("上传 %s 失败 HTTP %s: %s" % (p.name, st, str(r)[:300]))
            log("    ↑ %s (%d B)" % (p.name, p.stat().st_size))
        return rel.get("html_url")

    if platform == "gitee":
        base = "https://gitee.com/api/v5"
        st, rel = _api("%s/repos/%s/%s/releases" % (base, owner, name), "POST",
                       {"tag_name": tag, "name": tag, "body": notes,
                        "prerelease": prerelease,
                        "target_commitish": os.environ.get("GITEE_TARGET_REF",
                                                           "master")},
                       token=token)
        if st not in (200, 201):
            die("创建 Gitee Release 失败 HTTP %s: %s" % (st, str(rel)[:400]))
        rid = rel.get("id")
        log("    release id=%s" % rid)
        for p in assets:
            body, ct = _multipart({}, "file", p)
            st, r = _api("%s/repos/%s/%s/releases/%s/attach_files"
                         % (base, owner, name, rid), "POST", body,
                         headers={"Content-Type": ct}, token=token)
            if st not in (200, 201):
                die("上传 %s 失败 HTTP %s: %s" % (p.name, st, str(r)[:300]))
            log("    ↑ %s (%d B)" % (p.name, p.stat().st_size))
        return "https://gitee.com/%s/%s/releases/%s" % (owner, name, tag)

    if platform == "gitcode":
        base = "https://api.gitcode.com/api/v5"
        st, rel = _api("%s/repos/%s/%s/releases" % (base, owner, name), "POST",
                       {"tag": tag, "name": tag, "body": notes,
                        "target_commitish": os.environ.get("GITCODE_TARGET_REF",
                                                           "main"),
                        "release_status": "pre" if prerelease else "latest"},
                       token=token)
        if st not in (200, 201):
            die("创建 GitCode 发行版失败 HTTP %s: %s" % (st, str(rel)[:400]))
        log("    release created")
        for p in assets:
            st, info = _api("%s/repos/%s/%s/releases/%s/upload_url"
                            "?access_token=%s&file_name=%s"
                            % (base, owner, name, urllib.parse.quote(tag),
                               urllib.parse.quote(token),
                               urllib.parse.quote(p.name)),
                            token=token)
            if st != 200 or not isinstance(info, dict) or "url" not in info:
                die("获取 %s 上传地址失败 HTTP %s: %s"
                    % (p.name, st, str(info)[:300]))
            hdrs = {k: v for k, v in (info.get("headers") or {}).items()
                    if k.lower() not in ("host", "content-length")}
            st, r = _api(info["url"], "PUT", p.read_bytes(), headers=hdrs,
                         timeout=1800)
            if st not in (200, 201, 204):
                die("上传 %s 失败 HTTP %s: %s" % (p.name, st, str(r)[:300]))
            log("    ↑ %s (%d B)" % (p.name, p.stat().st_size))
        return "https://gitcode.com/%s/%s/releases" % (owner, name)

    die("未知平台 %s（支持 github / gitee / gitcode）" % platform)


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="四平台自动发布工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="构建发布产物")
    p.add_argument("--out", required=True)
    p.add_argument("--tag", default=None, help="如 v1.5.0；缺省用 CHANGELOG 版本")
    p.add_argument("--skip-gates", action="store_true")

    u = sub.add_parser("upload", help="上传并创建发行版")
    u.add_argument("--dir", required=True)
    u.add_argument("--platform", required=True,
                   choices=["github", "gitee", "gitcode"])
    u.add_argument("--repo", required=True, help="owner/name")
    u.add_argument("--tag", required=True)
    u.add_argument("--prerelease", action="store_true")
    u.add_argument("--dry-run", action="store_true")

    a = ap.parse_args()

    if a.cmd == "prepare":
        gates_ = [] if a.skip_gates else gates()
        repo_ver, vrows, top = check_versions()
        tag = a.tag or ("v" + repo_ver)
        notes = top[2] if top else ""
        m = build_artifact(Path(a.out), tag, repo_ver, notes, gates_, vrows)
        (Path(a.out) / "TAG").write_text(tag + "\n", encoding="utf-8")
        log("    TAG=%s  仓库版本=%s" % (tag, repo_ver))
        log("[5/5] 产物就绪：%s" % a.out)
        return

    # upload
    token = None
    for env in ("RELEASE_TOKEN", "GITHUB_TOKEN", "GITEE_TOKEN",
                "GITCODE_TOKEN"):
        if os.environ.get(env):
            token = os.environ[env]
            break
    if not token and not a.dry_run:
        die("未找到发布令牌：请在 Secrets 注入 RELEASE_TOKEN"
            "（或平台内置的 GITHUB_TOKEN / GITEE_TOKEN）")
    url = upload(a.repo, a.tag, a.platform, Path(a.dir), token,
                 a.dry_run, a.prerelease)
    log("[5/5] 发布完成：%s" % url)


if __name__ == "__main__":
    main()
