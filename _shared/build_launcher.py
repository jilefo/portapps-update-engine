# -*- coding: utf-8 -*-
"""
PAL 启动器构建器 —— 直接调用 makensis 编译 PortableApps.com Launcher

【为什么之前没做】原始提示词第 13 行写「你不执行本地编译」。
   用户已明确要求编译，故此处实现。

【关键格式发现】（读 PAL 源码 Other\\Source\\Segments\\Core.nsh 得出）
   1. launcher.ini 与 Custom.nsh 必须放在  App\\AppInfo\\Launcher\\
      不是 App\\AppInfo\\！（Core.nsh:10  StrCpy $LauncherFile $EXEDIR\\App\\AppInfo\\Launcher\\$BaseName.ini）
   2. appinfo.ini 必须有 [Details] 段，含 Name 与 AppID（Core.nsh:13-14）
   3. appinfo.ini 必须有 [Version] 段的 PackageVersion（GeneratorWizard.nsi 读取）
   4. 编译命令：makensis PortableApps.comLauncher.nsi /DPACKAGE=<目录> /DAppID=<ID>
用法: python build_launcher.py <包目录>
"""
import os, re, subprocess, sys, shutil, configparser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 工具链定位：环境变量 PAF_TOOLCHAIN -> <本文件所在目录> -> 标准布局 _shared
# （迁移前此处硬编码 <旧工作区>/Template Center\...，
#   迁移到 <仓库根>/ 后已失效）
_env_tc = os.environ.get("PAF_TOOLCHAIN")
if _env_tc:
    _TOOLCHAIN = Path(_env_tc)
else:
    _TOOLCHAIN = Path(__file__).resolve().parent
    if not (_TOOLCHAIN / "toolchain" / "PortableApps.comLauncher").is_dir():
        # 兼容把本脚本直接放进 <root>/_shared 之外的层级
        _TOOLCHAIN = _TOOLCHAIN.parent

PAL = str(_TOOLCHAIN / "toolchain" / "PortableApps.comLauncher")
MAKENSIS = os.path.join(PAL, "App", "NSIS", "makensis.exe")
NSI = os.path.join(PAL, "Other", "Source", "PortableApps.comLauncher.nsi")

if not os.path.isfile(MAKENSIS):
    sys.stderr.write(
        "[build_launcher] 未找到 makensis: %s\n"
        "  请设置 PAF_TOOLCHAIN 指向含 toolchain\\PortableApps.comLauncher 的目录，\n"
        "  或从 https://portableapps.com/development/launcher/ 获取工具链。\n"
        % MAKENSIS
    )

REQUIRED_FILES = [
    "License.txt", "RequireLatestNSIS.nsh", "Languages.nsh", "LangStrings.nsh",
    "NewTextReplace.nsh", "ReplaceInFileWithTextReplace.nsh", "ForEachINIPair.nsh",
    "ForEachPath.nsh", "SetFileAttributesDirectoryNormal.nsh", "ProcFunc.nsh",
    "EmptyWorkingSet.nsh", "SetEnvironmentVariable.nsh",
    "CheckForPlatformSplashDisable.nsh", "LogicLibAdditions.nsh",
    "TextFunc.nsh", "XML.nsh", "MyXML.nsh", "Segments.nsh", "Debug.nsh",
    "Registry.nsh", "UAC.nsh", "CallANSIPlugin.nsh", "TrimWhite.nsh",
    "NullByte.nsh", "Languages", "Plugins", "Segments",
]



def _patch_nsi_defines(appid, nsisver, pkg, nameportable):
    """把编译期变量直接写进 .nsi 的 !ifndef 兜底值。

    makensis 2.46 在 Git-Bash 环境下不认 /D 参数（会被 MSYS 改写成路径），
    而 !ifndef 会在编译期取兜底值 —— 直接改写最可靠。

    变量清单来自 GeneratorWizard.nsi:285 的官方调用：
        /DPACKAGE="$PACKAGE" /DNamePortable="$Name" /DAppID="$AppID" /DVersion="$1"
    注意 NamePortable 必须在 .nsi 里有对应的 !ifndef 兜底，
    否则窗口标题会显示成字面量 ${NamePortable}，且启动器不会加载任何配置。
    """
    nsi = os.path.join(PAL, "Other", "Source", "PortableApps.comLauncher.nsi")
    t = open(nsi, encoding="utf-8", newline="").read()

    # ★ 必须用 [^\r\n]+ 吃掉**整行**：早期用 \S+ 只替换第一个非空白 token，
    #   若上一次写入的兜底值含空格（如 "TyporaPortable CN IDEPortable"），
    #   \S+ 只覆盖首 token，残留 " CN IDEPortable" 尾巴，污染所有后续编译。
    defs = [
        (r"(!ifndef PACKAGEID\s*\r?\n\s*!define PACKAGEID )[^\r\n]+", appid),
        (r"(!ifndef Version\s*\r?\n\s*!define Version )[^\r\n]+", nsisver),
        (r"(!ifndef PACKAGE\s*\r?\n\s*!define PACKAGE )[^\r\n]+", '"' + pkg + '"'),
    ]
    for pat, val in defs:
        t = re.sub(pat, lambda m, v=val: m.group(1) + v, t)

    # NamePortable：官方靠 /DNamePortable 传入（GeneratorWizard.nsi:285）。
    # 本构建器改用「直接改写兜底值」的方式，故每次都要同步更新其值，
    # 否则窗口标题与运行期 $AppName 会停留在上一次的包名。
    if "!ifndef NamePortable" not in t:
        t = t.replace("!ifndef PACKAGEID",
                      "!ifndef NamePortable\n  !define NamePortable PLACEHOLDER\n!endif\n\n"
                      "!ifndef PACKAGEID", 1)
    t = re.sub(r"(!ifndef NamePortable\s*\r?\n\s*!define NamePortable )[^\r\n]+",
               lambda m: m.group(1) + '"' + nameportable.replace('"', "'") + '"', t)

    open(nsi, "w", encoding="utf-8", newline="").write(t)



DEBUG_BLOCK_MARK = "!define DEBUG_ALL 1"


def _patch_nsi_debug(enable):
    """开启/关闭 .nsi 调试块。

    注意：Debug.nsh 的 !getdebug 宏会先 !undef DEBUG 再按
    DEBUG_ALL / DEBUG_SEGMENT_* / DEBUG_GLOBAL 重新判定，
    所以只定义 DEBUG 无效，必须定义 DEBUG_ALL。

    ★ 关闭时必须把调试块**删干净**：残留的 DEBUG_ALL 会让之后所有
    普通编译都变成调试构建（把 Data\\debug.log 写进用户数据目录）。
    """
    nsi = os.path.join(PAL, "Other", "Source", "PortableApps.comLauncher.nsi")
    t = open(nsi, encoding="utf-8", newline="").read()
    block = ("!define DEBUG_ALL 1" + chr(10)
             + "!define DEBUG_SEGWRAP 1" + chr(10)
             + "!define DEBUG_OUTPUT file" + chr(10) + chr(10))
    # 先删旧块，再按需重加
    while DEBUG_BLOCK_MARK in t:
        t = t.replace(block, "", 1)
        if DEBUG_BLOCK_MARK in t:  # 兜底：块格式与预期不符时逐行剔除
            lines = [l for l in t.splitlines(True)
                     if not l.startswith("!define DEBUG_ALL")
                     and not l.startswith("!define DEBUG_SEGWRAP")
                     and not l.startswith("!define DEBUG_OUTPUT")]
            t = "".join(lines)
    if enable:
        t = t.replace("!ifndef NamePortable", block + "!ifndef NamePortable", 1)
    open(nsi, "w", encoding="utf-8", newline="").write(t)


def _read_text_any(path):
    """按 BOM/内容探测编码读文本（utf-8-sig / utf-16 / gb18030）"""
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16"), "utf-16"
    for enc in ("utf-8-sig", "gb18030"):
        try:
            t = raw.decode(enc)
            if "[" in t:
                return t, ("utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def read_details_name(pkg):
    """从 appinfo.ini 的 [Details] 读 Name —— PAL 用它做窗口标题与运行期 $AppName"""
    ai = os.path.join(pkg, "App", "AppInfo", "appinfo.ini")
    c = configparser.ConfigParser(strict=False, interpolation=None)
    c.optionxform = str
    # utf-8-sig：带 BOM 的 appinfo.ini（WeMeet）也能读；无 BOM 行为不变。
    # 纯 utf-8 读 BOM 文件会得到 \ufeff[Details]，configparser 报
    # MissingSectionHeaderError。WPS 的 appinfo 为 UTF-16，同样兼容。
    t, _enc = _read_text_any(ai)
    c.read_string(t)
    return c.get("Details", "Name", fallback=os.path.basename(pkg)) if \
        c.has_section("Details") else os.path.basename(pkg)


def fix_layout(pkg):
    """把 App\\AppInfo\\*.ini|nsh 迁到 App\\AppInfo\\Launcher\\"""
    info = os.path.join(pkg, "App", "AppInfo")
    launcher = os.path.join(info, "Launcher")
    os.makedirs(launcher, exist_ok=True)
    moved = []
    # PAL 用 $BaseName（= 启动器 exe 名，不含扩展名）拼出配置文件名：
    #   $EXEDIR\App\AppInfo\Launcher\$BaseName.ini
    # 见 Segments/Core.nsh:9-10。故 launcher.ini 必须重命名为 <AppID>.ini，
    # 否则启动器找不到配置，会弹「is missing [Launch]:ProgramExecutable」。
    appid = os.path.basename(pkg)
    # 关键：ini 按 $BaseName（=启动器exe名）命名，但 **nsh 必须是 Custom.nsh**
    #   Segments/Core.nsh:10  ${LauncherFile} = $EXEDIR\App\AppInfo\Launcher\$BaseName.ini
    #   Segments.nsh:122     !include /nonfatal "${PACKAGE}\App\AppInfo\Launcher\Custom.nsh"
    # 之前把 Custom.nsh 也改名成 <AppID>.nsh，导致所有自定义逻辑静默失效。
    ren = [("launcher.ini", appid + ".ini")]
    for old_fn, new_fn in ren:
        src = os.path.join(info, old_fn)
        if os.path.exists(src):
            shutil.move(src, os.path.join(launcher, new_fn))
            moved.append(f"{old_fn} -> {new_fn}")
        src2 = os.path.join(launcher, old_fn)
        if os.path.exists(src2):
            shutil.move(src2, os.path.join(launcher, new_fn))
            moved.append(f"{old_fn} -> {new_fn}")
    # appinfo.ini 留在 AppInfo 下，但要补 [Details] 与 [Version]
    ai = os.path.join(info, "appinfo.ini")
    ver = None
    if os.path.exists(ai):
        _, ver = fix_appinfo(ai, os.path.basename(pkg))
    return moved, ver


def _section_body(t, name):
    """返回**第一个** [name] 段的正文区间 (start, end)；不存在返回 None。

    ★ 必须取第一个：NSIS 的 ReadINIStr 只认第一个同名段，重复段被忽略。
    """
    m = re.search(r"(?mi)^\[" + re.escape(name) + r"\][ \t]*\r?\n", t)
    if not m:
        return None
    nxt = re.search(r"(?m)^\[", t[m.end():])
    end = m.end() + nxt.start() if nxt else len(t)
    return (m.end(), end)


def fix_appinfo(path, appid):
    """补齐 PAL 必需的 appinfo.ini 关键项。

    ★ 核心约束：`[Details]` 段的 `AppID`/`Name` 必须写在**第一个** `[Details]`
      里。Segments/Core.nsh:12-21 在 .onInit 里
          ReadINIStr $AppID  ... Details AppID
          ReadINIStr $AppNamePortable ... Details Name
      任一缺失即 ${Errors} → 弹 $(LauncherFileNotFound) 并 Quit，
      主程序**永远不启动**、Data 目录零写入。

      踩坑（2026-10-15 实测）：把 `[Details]` + AppID 追加到文件末尾**完全无效**，
      因为 NSIS ReadINIStr 只读第一个同名段。CodeArts / QuarkCloudDrive /
      FoxitPDF 三个包的 appinfo.ini 恰好是「首个 [Details] 无 AppID + 末尾
      重复 [Details] 有 AppID」的结构，于是
      启动器弹一个**空文本**错误框后静默退出（空文本是因为该 LangString 在
      1033 语言表里未设置）。
    """
    t, enc = _read_text_any(path)  # 按编码探测读入（剥 BOM；WPS 为 UTF-16）
    c = configparser.ConfigParser(strict=False, interpolation=None)
    c.optionxform = str
    c.read_string(t)

    def get(sec, key, default=""):
        return c.get(sec, key, fallback=default) if c.has_section(sec) else default

    # 应用名：优先 [Details] → [AppInfo] → 包名
    name = get("Details", "Name") or get("AppInfo", "Name") or appid
    # 版本：优先 [Details] → [AppInfo] → 1.0.0（[Details] Version 是通用写法）
    ver = get("Details", "Version") or get("AppInfo", "Version") or "1.0.0"
    pub = get("Details", "Publisher") or get("AppInfo", "Publisher")

    body = _section_body(t, "Details")
    if body is None:
        # 完全没有 [Details] 段 → 补一个完整的（含 AppID）
        t = (f"[Details]\r\nName={name}\r\nAppID={appid}\r\nPublisher={pub}\r\n"
             "Homepage=\r\nCategory=Development\r\n"
             "Description=Portable application\r\nLanguage=Multilingual\r\n\r\n" + t)
    else:
        s, e = body
        seg = t[s:e]
        ins = ""
        if not re.search(r"(?im)^AppID[ \t]*=", seg):
            ins += f"AppID={appid}\r\n"
        if not re.search(r"(?im)^Name[ \t]*=", seg):
            ins += f"Name={name}\r\n"
        if ins:
            t = t[:s] + ins + t[s:]

    if "[Version]" not in t:
        # NSIS 的 VIProductVersion 要求严格的 X.X.X.X 四段格式
        nums = (ver.split(".") + ["0", "0", "0", "0"])[:4]
        pkgver = ".".join(n if n.isdigit() else "0" for n in nums)
        t = t.rstrip() + "\n\n[Version]\nPackageVersion=" + pkgver + "\n"

    # 写回保留原编码（UTF-16 的 appinfo 写回 UTF-16；其余保留原 BOM 状态，
    # WeMeet 带 BOM，勿静默剥掉）
    if enc == "utf-16":
        open(path, "w", encoding="utf-16", newline="").write(t)
    else:
        had_bom = open(path, "rb").read(3) == b"\xef\xbb\xbf"
        open(path, "w", encoding="utf-8-sig" if had_bom else "utf-8",
             newline="").write(t)
    return name, ver


def build(pkg):
    pkg = os.path.abspath(pkg)
    appid = os.path.basename(pkg)
    print("=" * 68)
    print(f"构建 {appid}")
    print("=" * 68)

    if not os.path.isdir(pkg):
        print(f"[FAIL] 目录不存在: {pkg}")
        return False
    if not os.path.isfile(os.path.join(pkg, "App", "AppInfo", "appinfo.ini")):
        print("[FAIL] 缺少 App\\AppInfo\\appinfo.ini")
        return False

    # 1. 修正目录结构
    moved, ver = fix_layout(pkg)
    nameportable = read_details_name(pkg)
    if moved:
        print(f"  [1] 已迁移到 App\\AppInfo\\Launcher\\: {', '.join(moved)}")

    # 2. 检查 PAL 源文件完整性
    src = os.path.join(PAL, "Other", "Source")
    missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(src, f))]
    if missing:
        print(f"  [FAIL] PAL 源文件缺失: {missing}")
        return False
    print("  [2] PAL 源文件完整")

    # 3. 确保 App\AppInfo\appicon.ico 存在（编译需要）
    ico = os.path.join(pkg, "App", "AppInfo", "appicon.ico")
    if not os.path.exists(ico):
        srcico = os.path.join(PAL, "App", "AppInfo", "appicon.ico")
        if os.path.exists(srcico):
            shutil.copy2(srcico, ico)
            print("  [3] 已复制默认 appicon.ico")
        else:
            print("  [3] 警告: 无 appicon.ico，编译可能失败")

    # 4. 编译
    out = os.path.join(pkg, appid + ".exe")
    # PAL 的 make_release 会 sed 注入 "!define Version X.X.X.X"，
    # 本仓库的 .nsi 缺该行，故改用编译期 /DVersion 传入（格式必须 X.X.X.X）
    nums = (ver.split(".") + ["0", "0", "0", "0"])[:4]
    nsisver = ".".join(n if n.isdigit() else "0" for n in nums)
    # makensis 运行在 Git-Bash 环境下，MSYS 会把 /Dxxx 误当路径转换。
    # 用 MSYS2_ARG_CONV_EXCL 关掉该转换，并传反斜杠路径。
    env = dict(os.environ)
    env["MSYS2_ARG_CONV_EXCL"] = "*"
    env["MSYS_NO_PATHCONV"] = "1"
    # makensis 2.46 的 /D 传参在此环境下不可靠，改为直接改写 .nsi 里的兜底值
    _patch_nsi_defines(appid, nsisver, pkg, nameportable)
    # 调试块：开则加、关则删（防残留把普通构建变成调试构建）
    _patch_nsi_debug(bool(os.environ.get("PAL_DEBUG")))
    cmd = [MAKENSIS, NSI]
    print(f"  [4] 编译中...")
    print(f"      {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=src, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    tail = (r.stdout or "").strip().splitlines()[-12:]
    for l in tail:
        print(f"      | {l}")
    if r.returncode != 0:
        print(f"  [FAIL] 编译失败 rc={r.returncode}")
        if r.stderr:
            print("  stderr:", r.stderr[:500])
        return False

    if not os.path.exists(out):
        print(f"  [FAIL] 未生成 {out}")
        return False
    sz = os.path.getsize(out) / 1024
    print(f"  [OK] 生成 {appid}.exe  ({sz:.0f} KB)")
    print(f"      路径: {out}")
    return True


if __name__ == "__main__":
    ok = True
    for p in sys.argv[1:]:
        if not build(p):
            ok = False
        print()
    sys.exit(0 if ok else 1)
