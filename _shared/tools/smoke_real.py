# -*- coding: utf-8 -*-
# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
REPO_ROOT_F = REPO_ROOT.replace("\\", "/")
_TOOLS_DIR_F = str(_Path(__file__).resolve().parent).replace("\\", "/")
# <<< 路径自适应
"""smoke_real.py —— 真启动冒烟（参数化）。
判定：应用进程出现(按名) + Data 目录新写入 + 捕获中止框文本(应为空)。
用法：python smoke_real.py <PkgName> [观察秒数]

产品目录由 _paths.product_dir() 解析：迁移后 <产品根>/<Pkg>，
迁移前 <Repo>/<Pkg>/dist/<Pkg>，无需改配置自动切换。
"""
import ctypes, glob, os, subprocess, sys, time
from pathlib import Path
import psutil

# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
REPO_ROOT_F = REPO_ROOT.replace("\\", "/")
_TOOLS_DIR_F = str(_Path(__file__).resolve().parent).replace("\\", "/")
# <<< 路径自适应

# 产品根唯一解析处（dist 迁移到 D:\Portapps 后由它接管产品路径）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

BASE_ROOT = REPO_ROOT_F
STRIP_ENV = ("ELECTRON_RUN_AS_NODE", "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS")
WATCH_S = int(sys.argv[2]) if len(sys.argv) > 2 else 25

# 各包目标应用进程名（小写）
TARGETS = {
    "QQPortable": ("qq.exe",),
    "TIMPortable": ("tim.exe",),
    "QQNTPortable": ("qq.exe", "qqex.exe"),
    "BaiduNetdiskPortable": ("baidunetdisk.exe",),
    "CodeArtsAgentPortable": ("codearts-agent.exe",),
    # 进程名与包名不同形（去掉 Portable 猜不出来），必须显式登记：
    "SublimeTextPortable": ("sublime_text.exe",),   # 不是 sublimetext.exe
    "ZenBrowserPortable": ("zen.exe",),             # 不是 zenbrowser.exe
    "WPSOfficePortable": ("wps.exe",),
    "ZoomPortable": ("zoom.exe",),
    "WeixinPortable": ("weixin.exe",),
    "WXWorkPortable": ("wxwork.exe",),
    "eDiaryPortable": ("ediary.exe",),
    "FSCapturePortable": ("fscapture.exe",),
    "ReNamerPortable": ("renamer.exe",),
    "JoplinPortable": ("joplin.exe",),
}


def targets_of(pkg):
    """未登记的包按 <Pkg 去掉 Portable>.exe 推测，避免 KeyError 直接崩"""
    if pkg in TARGETS:
        return TARGETS[pkg]
    guess = pkg[:-len("Portable")].lower() + ".exe" if \
        pkg.endswith("Portable") else pkg.lower() + ".exe"
    print("[hint] %s 未登记目标进程，按 %s 推测" % (pkg, guess))
    return (guess,)


def pre_clean_rt(base):
    data = os.path.join(base, "Data")
    for d in (data, os.path.join(data, "settings")):
        for pat in ("PortableApps.comLauncherRuntimeData-*.ini", "RuntimeData.ini"):
            for f in glob.glob(os.path.join(d, pat)):
                os.remove(f)


def snapshot(root):
    snap = {}
    for dp, dn, fn in os.walk(root):
        for f in fn:
            q = os.path.join(dp, f)
            try:
                snap[q] = os.path.getmtime(q)
            except OSError:
                pass
    return snap


user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsWindowVisible = user32.IsWindowVisible
GetWindowTextW = user32.GetWindowTextW
GetClassNameW = user32.GetClassNameW


def dialogs_for(launcher_pid):
    out = []

    def cb(hwnd, _):
        pid = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        cls = ctypes.create_unicode_buffer(64)
        GetClassNameW(hwnd, cls, 64)
        t = ctypes.create_unicode_buffer(512)
        GetWindowTextW(hwnd, t, 512)
        if cls.value == "#32770" and pid.value == launcher_pid:
            texts = []

            def cb2(ch, _):
                tt = ctypes.create_unicode_buffer(1024)
                GetWindowTextW(ch, tt, 1024)
                if tt.value:
                    texts.append(tt.value)
                return True

            user32.EnumChildWindows(hwnd, ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb2), 0)
            out.append((t.value, texts))
            user32.SendMessageW(user32.GetDlgItem(hwnd, 2), 0x00F5, 0, 0)  # 点确定
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out


def run(pkg):
    base = str(_paths.product_dir(pkg))
    if not os.path.isdir(base):
        print(f"[{pkg}] [FAIL] 产品目录不存在: {base}"
              f"（产品根={_paths.product_root()}，"
              f"来源：{_paths.product_root_source()}）")
        return
    print(f"[{pkg}] 产品目录: {base}")
    targets = targets_of(pkg)
    pre_clean_rt(base)
    for n in targets:
        subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True)
    time.sleep(1)
    env = {k: v for k, v in os.environ.items() if k not in STRIP_ENV}
    before = snapshot(os.path.join(base, "Data"))
    p = subprocess.Popen([os.path.join(base, pkg + ".exe")], cwd=base,
                         env=env, stdin=subprocess.PIPE)
    t0 = time.time()
    first = None
    dlgs = []
    while time.time() - t0 < WATCH_S:
        for n in targets:
            for pr in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    if (pr.info["name"] or "").lower() == n and first is None:
                        first = round(time.time() - t0, 2)
                        print(f"[{pkg}] t+{first}s 应用进程 {n} 出现", flush=True)
                except psutil.Error:
                    pass
        newd = dialogs_for(p.pid)
        for d in newd:
            if d not in dlgs:
                dlgs.append(d)
                print(f"[{pkg}] t+{time.time()-t0:.1f}s 框: {d[1][:1]}", flush=True)
        if p.poll() is not None:
            print(f"[{pkg}] t+{time.time()-t0:.1f}s launcher rc={p.returncode}", flush=True)
        time.sleep(0.7)
    after = snapshot(os.path.join(base, "Data"))
    changed = [q for q, m in after.items() if before.get(q) != m]
    print(f"[{pkg}] Data 新写入 {len(changed)}; 框 {len(dlgs)} 个", flush=True)
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    for n in targets:
        subprocess.run(["taskkill", "/F", "/IM", n], capture_output=True)
    verdict = "PASS" if (first is not None and changed and not dlgs) else (
        "WARN(有进程/有写入但有框)" if first is not None else "FAIL")
    print(f"[{pkg}] => {verdict}", flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
