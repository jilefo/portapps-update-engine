# -*- coding: utf-8 -*-
r"""gen_update_strategies.py —— 生成「一包一更新脚本」

产出位置：**<产品目录>/update.py**（每个便携包目录下各自一个，自包含，
把整个产品目录拷走也能单独运行）。产品目录迁移前是 dist/<Pkg>/，
2026-10-18 起是 <产品根>/<Pkg>/（默认 D:\\Portapps\\<Pkg>），
由 _paths.product_dir() 统一解析。

模板：  _shared/tools/update_template.py（引擎内联，不 import _shared）
事实：  _shared/update/_facts.json（由 scan_update_facts.py 扫描产出，
        app_subdir / entry_exe / 当前版本 都从磁盘读，不手抄）
痕迹：  disable_exe 从磁盘上已有的 `*.disabled-by-engine` 反推——
        现在被禁用的更新器，更新后必须再禁一次，否则便携性会被破坏。

铁的纪律（很重要）：
  * **只写实测确认能取到确定版本号的源**。探针匹配到的 JS / SDK /
    静态资源 / SVG 坐标版本号，一律降级 manual。宁可人工，不给假信号。

用法：
  python _shared/tools/gen_update_strategies.py
  python _shared/tools/gen_update_strategies.py --clean    # 先删掉旧的
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = Path(__file__).resolve().parent / "update_template.py"
FACTS = REPO_ROOT / "_shared" / "update" / "_facts.json"

G, A, H, M = "github", "api", "html", "manual"

# ------------------------------------------------------------------ 规格表
SPEC = {
    # ===================== 实测可用的在线源（7 个）=====================
    "CursorPortable": dict(
        kind=A, pt="nsis", sched="weekly",
        url="https://www.cursor.com/api/download",
        params={"platform": "win32-x64", "releaseTrack": "stable"},
        vf="version", uf="downloadUrl",
        note="实测 2026-10-18：返回 version=3.25.6 + "
             "CursorSetup-x64-3.25.6.exe（HTTP 200 JSON）"),
    "FeishuPortable": dict(
        kind=A, pt="nsis", sched="monthly",
        url="https://www.feishu.cn/api/downloads", params=None,
        vf="versions.Windows_x64.version_number",
        uf="versions.Windows_x64.download_link",
        vre=r"(\d+\.\d+\.\d+)",
        note="实测 2026-10-18：version_number=Windows@V8.2.14，正则抠 8.2.14；"
             "旧的 package_info 接口已失效（bind error），改用 /api/downloads"),
    "SublimeTextPortable": dict(
        kind=H, pt="zip", sched="monthly", drop=["Data"],
        url="https://www.sublimetext.com/download",
        vre=r"Version:</i>\s*Build\s+(\d+)",
        tmpl="https://download.sublimetext.com/"
             "sublime_text_build_{version}_x64.zip",
        note="实测 2026-10-18：页面 <p class=latest><i>Version:</i> "
             "Build 4215</p>；直链 HEAD 200 / 26.8MB。上游 zip 自带 Data/，"
             "会覆盖 PAL 的数据重定向，已剔除"),
    "CherryStudioPortable": dict(
        kind=G, pt="7z_sfx", sched="monthly",
        repo="CherryHQ/cherry-studio",
        are=r"^Cherry-Studio-[\d.]+-win-x64-portable\.exe$",
        note="实测 2026-10-18：latest=v2.1.6，win-x64-portable.exe 存在"),
    "JoplinPortable": dict(
        kind=G, pt="nsis", sched="monthly",
        repo="laurent22/joplin", are=r"^Joplin-Setup-[\d.]+\.exe$",
        note="实测 2026-10-18：latest=v3.7.21，Joplin-Setup-3.7.21.exe 存在"),
    "SoloMDPortable": dict(
        kind=G, pt="zip", sched="monthly",
        repo="zhitongblog/solomd",
        are=r"^SoloMD_[\d.]+_x64-portable\.zip$",
        note="实测 2026-10-18：latest=v5.0.3（当前 5.0.1.0，确有更新）"),
    "ZenBrowserPortable": dict(
        kind=G, pt="nsis", sched="monthly", strip="core",
        repo="zen-browser/desktop", are=r"^zen\.installer\.exe$",
        note="实测 2026-10-18：latest=1.23.3b（当前 1.23.2.0，确有更新）。"
             "安装器解出 core/ + setup.exe，正主在 core/（已配 strip_root）"),

    # ============ 探针命中但为假信号，已诚实降级为 manual ==============
    "TIMPortable": dict(
        kind=M, pt="nsis", sched="monthly", page="https://tim.qq.com/",
        note="曾抓到 2.1.1，查上下文是页面 sea.js 的版本号，非 TIM 版本"),
    "BaiduNetdiskPortable": dict(
        kind=M, pt="nsis", sched="monthly", page="https://pan.baidu.com/download",
        note="曾抓到 2.1.1，查上下文是 badjs-sdk 的版本号"),
    "QuarkCloudDrivePortable": dict(
        kind=M, pt="nsis", sched="monthly", page="https://pan.quark.cn/download",
        note="曾抓到 0.1.78，查上下文是静态 CSS 资源版本号"),
    "TraeCNPortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        page="https://www.trae.com.cn/",
        note="曾抓到 2.0.0.401，查上下文是内联 JSON 里别的组件版本"),
    "FoxitPDFPortable": dict(
        kind=M, pt="nsis", sched="monthly",
        page="https://www.foxit.com/downloads/",
        note="曾抓到 476.233.31.949，查上下文是 SVG path 的坐标值"),

    # ===================== 蓝奏云（需签名，自动化不可行）================
    "FSCapturePortable": dict(
        kind=M, pt="zip", sched="monthly",
        page="https://www.faststone.org/FSCaptureDetail.htm",
        note="原配置走蓝奏云文件夹；实测页面无版本号且需二次签名跳转"),
    "ReNamerPortable": dict(
        kind=M, pt="zip", sched="monthly",
        page="https://www.den4b.com/products/renamer",
        note="原配置走蓝奏云文件夹；实测页面无版本号"),

    # ===================== 其余：无可靠在线源 =========================
    "AiPyProPortable": dict(kind=M, pt="electron_installer", sched="monthly"),
    "CodeArtsAgentPortable": dict(kind=M, pt="electron_installer",
                                  sched="monthly"),
    "CodeArtsPortable": dict(kind=M, pt="electron_installer", sched="monthly"),
    "CodeBuddyCNPortable": dict(kind=M, pt="electron_installer",
                                sched="monthly",
                                page="https://copilot.tencent.com/"),
    "ComatePortable": dict(kind=M, pt="electron_installer", sched="monthly",
                           page="https://comate.baidu.com/"),
    "eDiaryPortable": dict(kind=M, pt="zip", sched="yearly"),
    "JoyCodePortable": dict(kind=M, pt="electron_installer", sched="monthly"),
    "KukuAIPortable": dict(kind=M, pt="electron_installer", sched="monthly"),
    "LobsterAIPortable": dict(kind=M, pt="electron_installer",
                              sched="monthly"),
    "MiaoshouPortable": dict(kind=M, pt="nsis", sched="monthly"),
    "MiniMaxCodePortable": dict(kind=M, pt="electron_installer",
                                sched="monthly"),
    "OfficeAcePortable": dict(kind=M, pt="nsis", sched="monthly"),
    "QoderCNIDEPortable": dict(kind=M, pt="electron_installer",
                               sched="monthly", page="https://qoder.com/"),
    "QoderCNPortable": dict(kind=M, pt="electron_installer", sched="monthly",
                            page="https://qoder.com/"),
    "QQNTPortable": dict(kind=M, pt="nsis", sched="monthly",
                         page="https://im.qq.com/"),
    "QQPortable": dict(kind=M, pt="nsis", sched="monthly",
                       page="https://im.qq.com/pcqq"),
    "TodayCNPortable": dict(kind=M, pt="electron_installer", sched="monthly"),
    "TyporaPortable": dict(kind=M, pt="inno", sched="monthly",
                           page="https://typora.io/",
                           note="官网下载链接不含版本号，页面也抓不到"),
    "WeixinPortable": dict(kind=M, pt="nsis", sched="monthly",
                           page="https://pc.weixin.qq.com/"),
    "WeMeetPortable": dict(kind=M, pt="nsis", sched="monthly",
                           page="https://meeting.tencent.com/download"),
    "WinClawPortable": dict(kind=M, pt="electron_installer", sched="monthly"),
    "WorkBuddyPortable": dict(kind=M, pt="electron_installer",
                              sched="monthly"),
    "WPSOfficePortable": dict(kind=M, pt="nsis", sched="monthly",
                              page="https://www.wps.cn/"),
    "WXWorkPortable": dict(kind=M, pt="nsis", sched="monthly",
                           page="https://work.weixin.qq.com/"),
    "ZoomPortable": dict(kind=M, pt="msi", sched="monthly",
                         page="https://zoom.us/download"),
}

KIND_CLS = {G: "GithubReleases", A: "ApiJson", H: "HtmlPage", M: "Manual"}
KIND_SRC = {G: "github_releases", A: "api", H: "html", M: "manual"}


def esc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def one_line(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ---------------------------------------------------------- 从磁盘反推痕迹
def engine_traces(pkg, app_subdir):
    """返回现在被禁用的更新器文件名列表（去掉 .disabled-by-engine 后缀）。"""
    root = _paths.product_dir(pkg) / "App" / app_subdir
    if not root.is_dir():
        return []
    out = []
    for p in list(root.glob("*.disabled-by-engine")):
        out.append(p.name[:-len(".disabled-by-engine")])
    return sorted(set(out))


def build_config(spec, app_subdir, entry_exe, disable):
    """生成 S 类的字段块（缩进 4 空格）"""
    f = []
    kind = spec["kind"]
    if kind == G:
        f.append('    repo = "%s"' % spec["repo"])
        f.append('    asset_regex = r"%s"' % spec["are"])
    elif kind == A:
        f.append('    url = "%s"' % spec["url"])
        f.append("    params = %r" % (spec.get("params") or None,))
        f.append('    version_field = "%s"' % spec["vf"])
        f.append('    url_field = "%s"' % spec["uf"])
        if spec.get("vre"):
            f.append('    version_regex = r"%s"' % spec["vre"])
    elif kind == H:
        f.append('    url = "%s"' % spec["url"])
        f.append('    version_regex = r"%s"' % spec["vre"])
        if spec.get("tmpl"):
            f.append('    download_url_template = "%s"' % spec["tmpl"])
    else:
        if spec.get("page"):
            f.append('    download_page = "%s"' % spec["page"])
    f.append('    app_subdir = "%s"' % app_subdir)
    f.append('    entry_exe = r"%s"' % entry_exe)
    f.append('    package_type = "%s"' % spec["pt"])
    f.append('    schedule = "%s"' % spec["sched"])
    if spec.get("strip"):
        f.append('    strip_root = "%s"' % spec["strip"])
    if spec.get("drop"):
        f.append("    drop_paths = %r" % (list(spec["drop"]),))
    if disable:
        f.append("    disable_exe = %r" % (list(disable),))
    f.append('    note = "%s"' % esc(one_line(spec.get("note", ""))[:150]))
    return "\n".join(f)


def upstream_doc(spec):
    k = spec["kind"]
    if k == G:
        return ("上游仓库 : %s\n资产匹配 : %s\n" % (spec["repo"], spec["are"]))
    if k == A:
        return ("接口     : %s\n版本字段 : %s\n直链字段 : %s\n"
                % (spec["url"], spec["vf"], spec["uf"]))
    if k == H:
        return ("页面     : %s\n版本正则 : %s\n直链模板 : %s\n"
                % (spec["url"], spec["vre"], spec.get("tmpl", "（无）")))
    return ("下载页   : %s\n" % (spec.get("page") or "（见包 README）"))


def doc_header(pkg, spec, sub, entry, cur):
    L = []
    L.append("%s 便携版 —— 更新脚本" % pkg)
    L.append("")
    L.append("本文件由 `_shared/tools/gen_update_strategies.py` 自动生成，")
    L.append("改策略请改生成器里的 SPEC 再重新生成，不要直接手改本文件。")
    L.append("")
    L.append("源类型   : %s" % KIND_SRC[spec["kind"]])
    L.append(upstream_doc(spec).rstrip("\n"))
    L.append("包类型   : %s" % spec["pt"])
    L.append("检查周期 : %s" % spec["sched"])
    L.append("程序目录 : App\\%s" % sub)
    L.append("入口     : %s" % entry)
    L.append("生成时版本: %s" % cur)
    if spec.get("strip"):
        L.append("程序子目录: 解包后进入 %s/（安装器外层还有 setup.exe 等）"
                 % spec["strip"])
    if spec.get("drop"):
        L.append("剔除     : %s（上游自带，会破坏 PAL 数据重定向）"
                 % ", ".join(spec["drop"]))
    note = spec.get("note")
    if note:
        L.append("")
        L.append("说明：%s" % one_line(note))
    L.append("")
    L.append("用法（在本目录下执行）：")
    L.append("  python update.py --check                 只检测，只读，最安全")
    L.append("  python update.py --update                演练全流程（不落地）")
    L.append("  python update.py --update --execute      真正下载并替换")
    L.append("  python update.py --ingest <安装包> --execute   人工下载后接管")
    L.append("  python update.py --rollback              回滚到上一备份")
    L.append("  python update.py --check --json          机器可读输出")
    L.append("")
    L.append("安全设计：默认 dry-run；自动备份到")
    L.append("`_shared/update/_backups/%s/`；Data/ 目录永不触碰；失败自动回滚。"
             % pkg)
    return "\n".join(L)


def render(pkg, spec, fact, disable):
    t = TEMPLATE.read_text(encoding="utf-8")
    cfg = build_config(spec, fact["sub"], fact["entry"], disable)
    doc = doc_header(pkg, spec, fact["sub"], fact["entry"], fact["cur"])

    cls = KIND_CLS[spec["kind"]]
    # 1) 模板自己的 docstring 换成针对本包的说明
    #    注意用函数的返回值做替换，别用 % 格式化 —— 模板里有 %%PKG%% 这类
    #    占位符，走 % 运算符会被转义成 %PKG%，匹配不上（踩过）。
    m = re.search(r'^r""".*?"""', t, flags=re.S | re.M)
    if m:
        t = t[:m.start()] + 'r"""' + doc + '\n"""' + t[m.end():]
    # 2) 基类换成源类型子类（只替换真实代码里那一处）
    t = t.replace("\nclass S(Strategy):\n", "\nclass S(" + cls + "):\n", 1)
    # 3) S 类的 pkg / 配置块（模板里 %%CONFIG%% 在注释行上，
    #    这样模板自身也是合法 Python，不会被 compileall 报错）
    #    .* 吃掉该行 %%CONFIG%% 之后的注释尾巴，否则会剩半句注释在代码里
    pat = re.compile(r'class S\(' + cls + r'\):\n    pkg = "%%PKG%%"\n'
                     r'    # %%CONFIG%%.*')
    t, n = pat.subn(lambda _m: 'class S(' + cls + '):\n    pkg = "'
                    + pkg + '"\n' + cfg, t, count=1)
    if n != 1:
        raise RuntimeError("%s：配置块替换失败（命中 %d 次）" % (pkg, n))
    if "%%CONFIG%%" in t:
        raise RuntimeError("%s：配置块替换失败，检查模板占位符" % pkg)
    return t


def main():
    argv = sys.argv[1:]
    if not FACTS.is_file():
        print("缺少 %s，请先跑 scan_update_facts.py" % FACTS)
        return 2
    if not TEMPLATE.is_file():
        print("缺少模板 %s" % TEMPLATE)
        return 2
    rows = json.loads(FACTS.read_text(encoding="utf-8"))
    by_pkg = {r["pkg"]: r for r in rows}

    miss = [p for p in by_pkg if p not in SPEC]
    extra = [p for p in SPEC if p not in by_pkg]
    if miss:
        print("[警告] SPEC 缺少：%s" % ", ".join(miss))
    if extra:
        print("[警告] SPEC 多出（磁盘上没有）：%s" % ", ".join(extra))

    if "--clean" in argv:
        n = 0
        for pkg in _paths.packages():
            f = _paths.product_dir(pkg) / "update.py"
            if f.is_file():
                f.unlink()
                n += 1
        print("已删除旧的 update.py：%d 个（产品根=%s）"
              % (n, _paths.product_root()))

    n_auto = 0
    n_disable = 0
    for pkg in sorted(by_pkg):
        spec = SPEC.get(pkg)
        r = by_pkg[pkg]
        if not spec:
            continue
        entry = r.get("entry_exe") or ""
        sub = entry.split("\\")[0] if entry else (
            (r.get("app_subdirs") or [""])[0])
        if not sub and r.get("app_subdirs"):
            sub = r["app_subdirs"][0]
        fact = dict(sub=sub, entry=entry or "",
                    cur=r.get("appinfo_version") or "-")
        disable = engine_traces(pkg, sub)
        if disable:
            n_disable += 1
        text = render(pkg, spec, fact, disable)
        out = _paths.product_dir(pkg) / "update.py"
        if not out.parent.is_dir():
            print("[跳过] 产品目录不存在：%s" % out)
            continue
        out.write_text(text, encoding="utf-8")
        if spec["kind"] != M:
            n_auto += 1
    print("已生成 %d 个更新脚本 -> <产品目录>/update.py（产品根=%s）"
          % (len(by_pkg), _paths.product_root()))
    print("  在线自动源 %d / 人工接管 %d / 带自带更新器禁用逻辑 %d"
          % (n_auto, len(by_pkg) - n_auto, n_disable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
