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

G, A, H, M, W, C, R = ("github", "api", "html", "manual", "huawei_release",
                       "cdn_probe", "redirect")

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

    # ===================== 实测可用的在线源（新增 12 个，2026-10-20）=====
    "TIMPortable": dict(
        kind=A, pt="nsis", sched="monthly",
        url=("https://jsonschema.qpic.cn/99c2de7e3c0daa2e1eb6fa548bbf0c88"
             "/d80bde56620e0c005f06232ef2582bfc/versions"),
        params=None, vf="download_link.windows", uf="download_link.windows",
        vre=r"TIM([\d.]+)\.exe",
        note="页面 tim.qq.com/download.html 内 jQuery.ajax 调用的接口，"
             "需带 Referer。返回 download_link.windows 直链"
             "（TIM3.5.1.22172.exe，实测 200 / 87.0MB）；"
             "完整 4 段版本号从直链文件名正则抠（接口里只有 3 段）"),
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
    "AiPyProPortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        page="https://aipy.pro/",
        note="2026-10-20 复测：aipy.pro 是 SPA，所有路径（/api/version、"
             "/download、download.aipy.pro/latest.yml）都返回同一份 "
             "975B HTML；asar 里无明文更新 URL（electron-updater 相关"
             "命中全是 npmmirror 的包元数据）。"
             "GitHub 上的 knownsec/aipyapp 是 Python 包（whl/tar.gz），"
             "非 Windows 桌面安装包，不能用作源"),
    "CodeArtsAgentPortable": dict(
        kind=W, pt="electron_installer", sched="monthly",
        url="https://ide.cn-north-4.myhuaweicloud.com/v1/release-info/latest",
        subp="ai", arch="X86-64", ostype="windows",
        note="⚠️sub_product_name 必须是 ai（取自 product.json 的 "
             "subProductName）；传空/codearts-agent/agent/doer 都返回 "
             "空 result。实测 version=26.9.902，带 url + hash。"
             "本地 26.9.901 → 有更新"),
    "CodeBuddyCNPortable": dict(
        kind=A, pt="electron_installer", sched="monthly",
        url="https://copilot.tencent.com/v2/update",
        params={"platform": "ide-win32-x64-user"},
        vf="version", uf="url",
        note="platform 拼装规则来自客户端 out/main.js 的 buildUpdateFeedUrl："
             "`{updateUrl}/v2/update?platform=ide-{arch}-user`。"
             "实测 version=4.12.2.41207131 + sha256hash，157.0MB。"
             "⚠️版本双轨制：product.json 的 genieVersion=1.106.1，"
             "服务端返回 4 段 genieVersion，两者不可直接比较——"
             "首次运行需建立基线，之后与上次抓取值比对"),
    "CodeArtsPortable": dict(
        kind=W, pt="electron_installer", sched="monthly",
        url="https://ide.cn-north-4.myhuaweicloud.com/v1/release-info/latest",
        subp="work", arch="X86-64", ostype="windows",
        note="实测 2026-10-19：HTTP 200，version=0.2.6，直链 "
             "CodeArts-0.2.6-fb9a622-x64-prod.exe（带 sha256）；"
             "接口在客户端 resources/product.json 的 updateUrl，"
             "current_version 传任意值都返回同一最新版，必须自行比版本"),
    "ComatePortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        page="https://comate.baidu.com/",
        note="2026-10-20 复测：product.json 的 updateUrl "
             "（comate-ide.bj.bcebos.com/updates）只是 dev 模式兜底默认值，"
             "out/main.js 里另有自定义更新器（走 this.j.request，"
             "返回体含 url/version/productVersion），但请求 URL 由"
             "运行时拼装、asar 里无明文。bcebos 桶下列了 9 种 "
             "latest.yml/RELEASES 路径组合全部 404（桶关闭公开列举）。"
             "真实更新源未能定位"),
    "eDiaryPortable": dict(
        kind=M, pt="zip", sched="yearly",
        note="2026-10-20 复测：官网域名 haoxueseo.com 可达但 /ediary/ "
             "路径与 ediary.haoxueseo.com 均连接失败（SSL/连接错误）。"
             "站点为静态页，未见版本接口或带版本号的下载直链。"
             "另注：本包 schedule 原为 yearly，eDiary 实际更新极慢，"
             "保持 yearly 合理"),
    "JoyCodePortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        page="https://joycode.jd.com/",
        note="2026-10-20 复测：GitHub 上 jd-opensource/joycode-agent "
             "releases 返回 404（仓库无 release 或已私有）；"
             "asar 未找到 app.asar（非标准 Electron 打包结构）。"
             "官网为京东内部风格 SPA，无可直接调用的版本接口"),
    "KukuAIPortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        note="2026-10-20 复测：asar 里 electron-updater 关键词有命中"
             "（autoUpdater/setFeedURL/checkForUpdates），但**无任何"
             "更新 URL 明文**——feed 地址应为运行时注入或经登录态下发。"
             "外网域名 kuku.ai / genflow.cn / genflow.pro 均不可达"
             "（DNS 或连接失败）。产品需登录使用，版本接口很可能带鉴权"),
    "LobsterAIPortable": dict(
        kind=G, pt="electron_installer", sched="monthly",
        repo="netease-youdao/lobsterai",
        are=r"LobsterAI--win-x64\.exe",
        note="客户端 resources/app-update.yml 写死 provider: github，"
             "owner=netease-youdao repo=lobsterai。"
             "实测 tag=2026.10.16，资产 LobsterAI--win-x64.exe（332.0MB）"
             "+ SHA256SUMS。本地 2026.10.13 → 有更新"),
    "QoderCNPortable": dict(
        kind=A, pt="electron_installer", sched="monthly",
        url=("https://static.qoder.com.cn/qoder-app/releases/latest.yml"),
        params=None, vf="version", uf="files.0.url",
        note="electron-updater generic feed（基址取自客户端 "
             "resources/app-update.yml + product.json 的 "
             "desktopUpdateDownloadBaseUrl）。YAML 明文，自带 sha512+sha256；"
             "实测 version=0.4.8，本地 0.4.4 → 有更新"),
    "MiaoshouPortable": dict(
        kind=M, pt="nsis", sched="monthly",
        note="2026-10-20 复测：妙手（跨境电商ERP），官网需登录。"
             "GitHub 上 miaoshouai/* 是 Stable Diffusion 辅助工具，"
             "与桌面客户端无关。未定位到公开版本接口"),
    "MiniMaxCodePortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        note="2026-10-20 复测：asar 里找到热更新 CDN "
             "filecdn.minimax.chat/public/minimax-agent/hot-update/zh/prod "
             "（及 .io 镜像、en/staging/test 变体），但该路径下 "
             "latest.yml / win32-x64/latest.yml / version.json 全部 404。"
             "GitHub MiniMax-AI/minimax-code 的 release 只有 CLI 的 "
             "tar.gz + sha256，非 Windows 桌面安装包。"
             "桌面版版本源未定位"),
    "OfficeAcePortable": dict(
        kind=C, pt="nsis", sched="monthly",
        cdn="https://res-static.hc-cdn.cn/cloudbu-site/china/zh-cn/OfficeAce",
        npat="OfficeAce-{version}-windows-x64-setup.exe",
        # 应用自己写的更新任务状态（taskId 形如 version-1.4.1），
        # 拿它当探测线索可把常见情况压到 1 次 HEAD
        hints=[r"Data\settings\local\OfficeClaw\updates\state.json"],
        hashes={"1.4.1": "a34390dfe3f69a42714583f958d60fb89e4e268fe48c9dc9138f6c2e83be6416"},
        drop=["Data"]),
    "QoderCNIDEPortable": dict(
        kind=M, pt="electron_installer", sched="monthly",
        page="https://qoder.com/",
        note="2026-10-20 复测：product.json 的 updateUrl 指向 "
             "lingma-api.tongyi.aliyun.com/algo（阿里灵码后端），"
             "实测该路径返回 503。与 QoderCNPortable 不同的是："
             "IDE 版走阿里云 algo 接口，桌面版走 "
             "static.qoder.com.cn/qoder-app/releases 的 electron feed。"
             "IDE 版的更新协议与桌面版不同源，未能复现"),
    "QQNTPortable": dict(
        kind=A, pt="nsis", sched="monthly",
        url=("https://cdn-go.cn/qq-web/im.qq.com_new/latest/rainbow"
             "/windowsConfig.js"),
        params=None, vf="ntDownloadUrl", uf="ntDownloadUrl",
        vre=r"/([\d.]+)/release/",
        note="与 QQ 共用 windowsConfig.js，取 ntDownloadUrl 字段。"
             "⚠️本机实测 403：qqfile/QQNTV2/ 前缀被腾讯 EdgeOne WAF "
             "按出口 IP 封锁（Server: Lego Server），已排除 UA/Referer/"
             "构建哈希因素。换网络环境很可能即可用；"
             "另注意 version 字段是 NT 版 4 段号，需从 URL 路径解析"),
    "QQPortable": dict(
        kind=A, pt="nsis", sched="monthly",
        url=("https://cdn-go.cn/qq-web/im.qq.com_new/latest/rainbow"
             "/windowsConfig.js"),
        params=None, vf="downloadUrl", uf="downloadUrl",
        vre=r"/PCQQ[\d.]+/QQ([\d.]+)\.exe",
        note="页面 im.qq.com/pcqq 内联的 rainbowConfigUrl。"
             "⚠️坑：配置里的 \"version\" 字段（9.9.36）是 **QQNT** 的版本，"
             "经典 QQ 已停在 9.7.25.29417；必须从 downloadUrl 路径里解析。"
             "直链实测 200 / 229207216 B"),
    "TodayCNPortable": dict(
        kind=A, pt="electron_installer", sched="monthly",
        url=("https://releases.todayai.cn/apps/today/desktop/windows-cn"
             "/release/x64/latest.yml"),
        params=None, vf="version", uf="path",
        note="electron-updater generic feed（基址取自客户端 "
             "resources/app-update.yml）。YAML 明文，自带 sha512 + size；"
             "实测 version=1.22.1，本地 1.21.5 → 有更新。"
             "⚠️需 yaml 解析，模板暂按 JSON 处理，此条待补解析器"),
    "TyporaPortable": dict(
        kind=M, pt="inno", sched="monthly", page="https://typora.io/",
        note="⚠️首页的 2024.11.0 是 Cloudflare Beacon 版本，不是 Typora；"
             "直链 typora-setup-x64.exe 无版本号。真实版本需从 release "
             "notes 页取，暂降级人工"),
    "WeixinPortable": dict(
        kind=H, pt="nsis", sched="monthly",
        url="https://pc.weixin.qq.com/",
        vre=(r'WeChatWin_([0-9]+(?:\.[0-9]+)+)\.exe'),
        note="⚠️坑：页面 HTML 注释里另有 3.9.12（32位旧版），"
             "裸正则 \\d+\\.\\d+\\.\\d+ 会误抓；必须锚定 WeChatWin_ 文件名。"
             "实测 4.1.15 / 256569752 B。"
             "⚠️该模式只从页面 HTML 抠版本号，直链需用 "
             "download_url_template 拼（见 tmpl 字段）",
        tmpl=("https://dldir1v6.qq.com/weixin/Universal/Windows"
              "/WeChatWin_{version}.exe")),
    "WeMeetPortable": dict(
        kind=A, pt="nsis", sched="monthly",
        url=("https://meeting.tencent.com/web-service/query-download-info"),
        params={"q": '[{"package-type":"app","channel":"0300000000",'
                     '"platform":"windows","arch":"x86_64"}]'},
        nonce="nonce", ref="https://meeting.tencent.com/download/",
        vf="info-list.0.version", uf="info-list.0.url",
        note="⚠️两个必要参数：channel 必须 0300000000（官网正式版，"
             "换 1410000197 会拿到国际版旧包）；nonce 随机 16 位十六进制，"
             "不带会返回 code:1 + 空 info-list（看不出是缺参数）。"
             "还需带 Referer。"
             "⚠️坑：下载页 HTML 里的 1.43.5 是 aegis-web-sdk 版本，"
             "真实版本是 3.46.11.413（目录名级差异）。"
             "返回体自带 md5 + size，实测 301998824 B"),
    "WinClawPortable": dict(
        kind=A, pt="electron_installer", sched="monthly",
        url=("https://wnt.oss-cn-beijing.aliyuncs.com/winclaw/releases"
             "/latest/latest.yml"),
        params=None, vf="version", uf="path",
        note="electron-updater generic feed（基址取自客户端 "
             "resources/app-update.yml）。YAML 明文，自带 sha512 + size；"
             "实测 version=2.6.6，本地 2.5.7 → 有更新。"
             "⚠️需 yaml 解析，模板暂按 JSON 处理，此条待补解析器"),
    "WorkBuddyPortable": dict(
        kind=A, pt="electron_installer", sched="monthly",
        url="https://copilot.tencent.com/v2/update",
        params={"platform": "workbuddy-win32-x64-user"},
        vf="version", uf="url",
        note="与 CodeBuddy CN 同族接口，platform 前缀换成 workbuddy。"
             "⚠️版本双轨制：product.json 是 5.8.2，服务端返回 "
             "5.8.3.41334564（4 段 genieVersion），两者不可直接比。"
             "返回体带 sha256hash，实测 157.0MB"),
    "WorkBuddyAIPortable": dict(kind=M, pt="electron_installer",
                              sched="monthly",
                              note="manual：官方安装包人工下载；实测 HKLM 自有键 0 条、无服务/驱动，" 
                                   "监控原始记录见 Other/Source/Monitor"),
    "WPSOfficePortable": dict(kind=M, pt="nsis", sched="monthly",
                              page="https://www.wps.cn/"),
    "WXWorkPortable": dict(
        kind=R, pt="nsis", sched="monthly",
        url=("https://work.weixin.qq.com/wework_admin/commdownload"
             "?platform=win&from=wwindex"),
        vre=r"WeCom_(\d+\.\d+\.\d+\.\d+)\.exe",
        note="302 重定向即版本接口：Location 为 "
             "dldir1.qq.com/wework/work_weixin/WeCom_5.0.12.6018.exe"
             "（实测 200 / 658582280 B）。一次请求同时拿版本+直链。"
             "⚠️注意：HTML 下载页 work.weixin.qq.com/download 已 404，"
             "正确入口是 #index_download 的 commdownload 端点"),
    "ZoomPortable": dict(
        kind=A, pt="msi", sched="monthly",
        url="https://zoom.us/rest/download?os=win",
        vf="result.downloadVO.zoomX64.version",
        tmpl="https://cdn.zoom.us/prod/{version}/x64/ZoomInstallerFull.exe",
        note="✅2026-10-20 二次排查后接通（此前误判为不可自动化，已翻案）。"
             "官网下载页静态 HTML 确实无版本号（Vue 运行时渲染），"
             "但版本数据来自 https://zoom.us/rest/download?os=win "
             "（从 meeting-base-V3/js/download.YIwc8fjL.js 挖出的接口）。"
             "返回 JSON 的 downloadVO.zoomX64.version = 7.2.1.48556 "
             "（与 zoom.us/download 页面'版本 7.2.1 (48556)'完全一致），"
             "下载直链按 CDN 规律拼："
             "https://cdn.zoom.us/prod/{version}/x64/ZoomInstallerFull.exe，"
             "HEAD 实测 200 / 181560368 B。"
             ""
             "⚠️此前'client/latest 是旧版'的结论需要修正表述："
             "downloadVO.zoom（32 位分支）确实是 6.6.11.23272 且已停更"
             "（Zoom 公告 2025-12 终止 32 位 Windows 支持），"
             "/client/latest 别名跟随的就是这个 32 位包；"
             "x64 版本在 downloadVO.zoomX64，取对字段即为最新。"
             "⚠️别用 downloadVO.zoom 做源；arm 版字段是 zoomArm64。"),
}

KIND_CLS = {G: "GithubReleases", A: "ApiJson", H: "HtmlPage", M: "Manual",
            W: "HuaweiReleaseInfo", C: "CdnProbe", R: "RedirectProbe"}
KIND_SRC = {G: "github_releases", A: "api", H: "html", M: "manual",
            W: "api", C: "cdn_probe", R: "redirect"}


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
        if spec.get("nonce"):
            f.append('    nonce_param = "%s"' % spec["nonce"])
        if spec.get("ref"):
            f.append('    referer = "%s"' % spec["ref"])
        f.append('    version_field = "%s"' % spec["vf"])
        if spec.get("tmpl"):
            # 接口只回版本号时按模板拼直链（Zoom /rest/download），
            # 支持 {version} 与 {点号路径} 占位符；设了 tmpl 就不回灌 url_field
            f.append('    url_template = "%s"' % spec["tmpl"])
        else:
            f.append('    url_field = "%s"' % spec.get("uf", "downloadUrl"))
        if spec.get("vre"):
            f.append('    version_regex = r"%s"' % spec["vre"])
    elif kind == H:
        f.append('    url = "%s"' % spec["url"])
        f.append('    version_regex = r"%s"' % spec["vre"])
        if spec.get("tmpl"):
            f.append('    download_url_template = "%s"' % spec["tmpl"])
    elif kind == W:
        f.append('    url = "%s"' % spec["url"])
        f.append('    sub_product_name = "%s"' % spec["subp"])
        f.append('    arch = "%s"' % spec.get("arch", "X86-64"))
        f.append('    os_type = "%s"' % spec.get("ostype", "windows"))
    elif kind == R:
        # 跟随 302，从 Location 头抠版本号与直链
        f.append('    url = "%s"' % spec["url"])
        f.append('    version_regex = r"%s"' % spec["vre"])
        if spec.get("relbase"):
            f.append('    base_for_relative = "%s"' % spec["relbase"])
    elif kind == C:
        # CDN HEAD 探测：按版本号拼 URL 试存在性
        f.append('    cdn_base = "%s"' % spec["cdn"])
        f.append('    name_pattern = "%s"' % spec["npat"])
        if spec.get("hints"):
            f.append("    hint_files = [%s]"
                     % ", ".join("%r" % h for h in spec["hints"]))
        if spec.get("look"):
            f.append('    patch_lookahead = %d' % spec["look"])
        if spec.get("mspan"):
            f.append('    minor_span = %d' % spec["mspan"])
        if spec.get("mcap"):
            f.append('    minor_patch_cap = %d' % spec["mcap"])
        if spec.get("hashes"):
            f.append("    known_hashes = {")
            for ver, sha in spec["hashes"].items():
                # sha256 长 64 字符，单行放得下（整行约 80 列）
                f.append('        "%s":' % ver)
                f.append('            "%s",' % sha)
            f.append("    }")
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
        if spec.get("tmpl"):
            link = "模板     : %s" % spec["tmpl"]
        else:
            link = "直链字段 : %s" % spec.get("uf", "downloadUrl")
        return ("接口     : %s\n版本字段 : %s\n%s\n"
                % (spec["url"], spec["vf"], link))
    if k == H:
        return ("页面     : %s\n版本正则 : %s\n直链模板 : %s\n"
                % (spec["url"], spec["vre"], spec.get("tmpl", "（无）")))
    if k == W:
        return ("升级接口 : %s\n子产品名 : %s\n平台参数 : %s / %s\n"
                % (spec["url"], spec["subp"],
                   spec.get("ostype", "windows"),
                   spec.get("arch", "X86-64")))
    if k == R:
        return ("重定向端点 : %s\n版本正则   : %s\n"
                % (spec["url"], spec["vre"]))
    if k == C:
        return ("CDN 基址 : %s\n命名规则 : %s\n"
                "探测方式 : HEAD 逐版本试存在性（403 视为未发布）\n"
                % (spec["cdn"], spec["npat"]))
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
    if spec["kind"] == W:
        L.append("校验     : 上游返回 sha256，下载后强制校验")
    elif spec.get("hashes"):
        L.append("校验     : CDN 不提供摘要；SPEC.known_hashes 登记 %d 个版本的"
                 "sha256，登记则强制校验，其余靠 HTTPS + 解包完整性"
                 % len(spec["hashes"]))
    else:
        L.append("校验     : 上游未提供 sha256，仅靠 HTTPS 传输 + 解包完整性，"
                 "无内容指纹")
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
    L.append("")
    L.append("运行环境：Python 3.8+，仅使用标准库；解包 NSIS/Inno/7z 安装器时")
    L.append("需要外部 7-Zip（缺失时会从 PATH 与 ProgramFiles 环境变量里找）。")
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
        if spec["kind"] != M:      # Manual 之外都是自动源（含 CdnProbe）
            n_auto += 1
    print("已生成 %d 个更新脚本 -> <产品目录>/update.py（产品根=%s）"
          % (len(by_pkg), _paths.product_root()))
    print("  在线自动源 %d / 人工接管 %d / 带自带更新器禁用逻辑 %d"
          % (n_auto, len(by_pkg) - n_auto, n_disable))
    return 0


if __name__ == "__main__":
    sys.exit(main())
