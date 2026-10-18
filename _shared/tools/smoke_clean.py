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
"""便携项目全量冒烟探针 v3（干净环境版）

v2 缺陷修正（2026-10-17 重大发现）：
  WorkBuddy/CodeBuddy 等 Electron CLI 宿主进程环境中带有
  ELECTRON_RUN_AS_NODE=1 / NODE_OPTIONS=--require=<language-shim>，
  子进程全部继承 → **所有 Electron 应用被强制降级为 Node 运行**
  （--version 打印 Node 版、GUI 不初始化、无子进程、stdin EOF 即退）。
  v2 冒烟产出的 Electron 类 PASS/WARN/FAIL 判定全部不可信。
  本版：启动子进程一律剥离该组变量，并新增窗口标题捕获，
  判定才同时满足「窗口/子进程」与「Data 写入」两个维度。

单项流程：预清RT→快照(AppData/LocalAppData/Data)→干净环境启动(stdin=PIPE)
→轮询子进程+窗口≤CHILD_WAIT_S→观察写入→快照对照→有序收场→清残留。
"""
import ctypes
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime

try:
    import psutil
except ImportError:
    sys.exit('psutil 未安装')

ROOT = REPO_ROOT
CHILD_WAIT_S = 25
WRITE_SETTLE_S = 6
TEARDOWN_S = 3
REPORT_DIR = os.path.join(REPO_ROOT, "docs", "reports")
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')

# 宿主污染变量：会改变 Electron/Node 应用运行模式的，一律剥离
STRIP_ENV = ('ELECTRON_RUN_AS_NODE', 'NODE_OPTIONS', 'NODE_EXTRA_CA_CERTS')

MANUAL = [
    dict(name='KukuAIPortable',
         exe=os.path.join(ROOT, 'KukuAIPortable', 'dist', 'KukuAIPortable', 'KukuAIPortable.exe'),
         cmd='GenFlowPro.exe'),
    dict(name='WPSOfficePortable-Writer',
         exe=os.path.join(ROOT, 'WPSOfficePortable', 'dist', 'WPSOfficePortable', 'WriterPortable.exe'),
         cmd='wps.exe'),
    dict(name='WPSOfficePortable-Spreadsheets',
         exe=os.path.join(ROOT, 'WPSOfficePortable', 'dist', 'WPSOfficePortable', 'SpreadsheetsPortable.exe'),
         cmd='et.exe'),
    dict(name='WPSOfficePortable-Presentation',
         exe=os.path.join(ROOT, 'WPSOfficePortable', 'dist', 'WPSOfficePortable', 'PresentationPortable.exe'),
         cmd='wpp.exe'),
    dict(name='WPSOfficePortable-PDF',
         exe=os.path.join(ROOT, 'WPSOfficePortable', 'dist', 'WPSOfficePortable', 'wpsPDFPortable.exe'),
         cmd='wpsoffice.exe'),
]
SKIP = {'WPSOfficePortable'}

FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsWindowVisible = user32.IsWindowVisible
GetWindowTextW = user32.GetWindowTextW


def app_env():
    return {k: v for k, v in os.environ.items() if k not in STRIP_ENV}


def windows_for_pids(pids):
    found = {}

    def cb(hwnd, _):
        p = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value in pids and IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(512)
            GetWindowTextW(hwnd, buf, 512)
            if buf.value:
                found.setdefault(p.value, []).append(buf.value)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found


def is_junction(path):
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1:
        return False
    return bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT)


def read_link_target(path):
    try:
        return os.readlink(path)
    except OSError:
        try:
            out = subprocess.run(['cmd', '/c', 'fsutil', 'reparsepoint', 'query', str(path)],
                                 capture_output=True, text=True, errors='replace', timeout=5)
            return out.stdout.strip()[:200]
        except Exception:
            return '?'


def snap_appdata(base):
    out = {}
    try:
        names = os.listdir(base)
    except OSError:
        return out
    for n in names:
        p = os.path.join(base, n)
        try:
            if is_junction(p):
                out[n] = ('junction', read_link_target(p))
            elif os.path.isdir(p):
                out[n] = ('dir', None)
            else:
                out[n] = ('file', None)
        except OSError:
            continue
    return out


def data_stats(data_dir):
    nf = tot = 0
    if not data_dir or not os.path.isdir(data_dir):
        return dict(files=0, size=0)
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            nf += 1
            tot += st.st_size
    return dict(files=nf, size=tot)


def fresh_writes(data_dir, since_ts):
    n = 0
    if not data_dir or not os.path.isdir(data_dir):
        return 0
    for root, dirs, files in os.walk(data_dir):
        for f in files:
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            if st.st_mtime >= since_ts:
                n += 1
    return n


def pre_clean_runtime_data(data_dir):
    """清理两代 PAL 约定的运行时数据文件（自锁解药）：
    - 新版：Data\\PortableApps.comLauncherRuntimeData-<BaseName>.ini
    - 2021/2022 旧构建：Data\\RuntimeData.ini（无 BaseName 后缀，实测存在）
    """
    killed = []
    pats = ['PortableApps.comLauncherRuntimeData-*.ini', 'RuntimeData.ini']
    dirs = [data_dir]
    if data_dir:
        parent = os.path.dirname(data_dir)
        if parent and parent != data_dir:
            dirs.append(parent)
    for d in dirs:
        for pat in pats:
            for f in glob.glob(os.path.join(d, pat)):
                try:
                    os.remove(f)
                    killed.append(os.path.basename(f))
                except OSError:
                    pass
    return killed


def pkg_app_procs(pkg_dir, exclude_pid):
    """按 exe 路径找包内应用进程（含被 PAL 启动器退出后孤儿化的孙子进程）"""
    out = {}
    for pr in psutil.process_iter(["pid", "name", "exe"]):
        pid = pr.info["pid"]
        if pid == exclude_pid:
            continue
        try:
            exe = (pr.info["exe"] or "").lower()
        except Exception:
            continue
        if exe.startswith(pkg_dir.lower()):
            out[pid] = (pr.info["name"], pr.info["exe"])
    return out


def external_main_running(cmd_base, pkg_dir):
    if not cmd_base:
        return None
    hits = []
    for p in psutil.process_iter(['name', 'exe']):
        try:
            if (p.info['name'] or '').lower() != cmd_base.lower():
                continue
            exe = p.info['exe'] or ''
            if exe and not exe.lower().startswith(pkg_dir.lower()):
                hits.append(exe)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return hits or None


def remove_junction(path):
    try:
        os.rmdir(path)
        return True
    except OSError:
        return False


def clean_pkg_junctions(base, pkg_marker):
    n = 0
    try:
        names = os.listdir(base)
    except OSError:
        return 0
    for name in names:
        p = os.path.join(base, name)
        if is_junction(p):
            tgt = read_link_target(p)
            if pkg_marker.lower() in (tgt or '').lower():
                if remove_junction(p):
                    n += 1
    return n


def kill_tree(pid):
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        kids = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        kids = []
    for k in kids:
        try:
            k.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(kids, timeout=3)
    try:
        parent.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def load_projects():
    with open(os.path.join(os.path.dirname(__file__), '_projects_index.json'), encoding='utf-8') as f:
        rows = json.load(f)
    projs = []
    for r in rows:
        if r['name'] in SKIP or not r.get('exe'):
            continue
        projs.append(dict(name=r['name'], exe=r['exe'], cmd=(r.get('cmd') or '').strip()))
    for m in MANUAL:
        if os.path.isfile(m['exe']):
            projs.append(m)
    return projs


def test_project(pr):
    pkg_dir = os.path.dirname(pr['exe'])
    data_dir = os.path.join(pkg_dir, 'Data')
    if not os.path.isdir(data_dir):
        cand = os.path.join(os.path.dirname(os.path.dirname(pr['exe'])), 'Data')
        if os.path.isdir(cand):
            data_dir = cand
    rec = dict(name=pr['name'], exe=pr['exe'], pkg_dir=pkg_dir)
    t0 = time.time()

    rec['rt_preclean'] = pre_clean_runtime_data(data_dir)
    pre_ad = snap_appdata(os.environ['APPDATA'])
    pre_ld = snap_appdata(os.environ['LOCALAPPDATA'])
    pre_data = data_stats(data_dir)
    rec['pre_external'] = external_main_running(pr.get('cmd'), pkg_dir)

    try:
        proc = subprocess.Popen([pr['exe']], cwd=pkg_dir, env=app_env(),
                                stdin=subprocess.PIPE)
    except OSError as e:
        rec.update(error=f'launch-failed: {e}', children=[], fresh_files=0,
                   post_data=pre_data, leaks=[], verdict='FAIL')
        return rec

    seen = {}
    first_window = None
    windows = []
    launcher_gone = False
    deadline = t0 + CHILD_WAIT_S
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            kids = psutil.Process(proc.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            launcher_gone = True
            kids = []
        for k in kids:
            if k.pid in seen:
                continue
            try:
                exe = k.exe()
            except Exception:
                exe = '?'
            seen[k.pid] = (k.name(), exe, time.time() - t0)
        # 孤儿检测：应用进程按 exe 路径归属本包（启动器先退、应用存活的场景）
        for pid, (nm, exe) in pkg_app_procs(pkg_dir, proc.pid).items():
            if pid not in seen:
                seen[pid] = (nm, exe, time.time() - t0)
        if seen or launcher_gone:
            titles = windows_for_pids(set(seen) | {proc.pid})
            if titles and first_window is None:
                first_window = round(time.time() - t0, 1)
                windows = sorted({t for v in titles.values() for t in v})
            if seen:
                time.sleep(1.5)
                try:
                    still = {k.pid for k in psutil.Process(proc.pid).children(recursive=True)}
                except psutil.NoSuchProcess:
                    still = set()
                still |= set(pkg_app_procs(pkg_dir, proc.pid))
                if still & set(seen):
                    break

    time.sleep(WRITE_SETTLE_S)

    fresh = fresh_writes(data_dir, t0 - 5)
    post_data = data_stats(data_dir)
    post_ad = snap_appdata(os.environ['APPDATA'])
    post_ld = snap_appdata(os.environ['LOCALAPPDATA'])

    leaks, junctions = [], []
    for label, pre, post in (('APPDATA', pre_ad, post_ad), ('LOCALAPPDATA', pre_ld, post_ld)):
        for n, (kind, tgt) in post.items():
            if n in pre:
                continue
            if kind == 'junction':
                if pkg_dir.lower() in (tgt or '').lower():
                    junctions.append(f'{label}\\{n}')
                else:
                    leaks.append(f'{label}\\{n}->非包内联接({tgt})')
            elif kind == 'dir':
                leaks.append(f'{label}\\{n} 实体目录')
            elif kind == 'file':
                leaks.append(f'{label}\\{n} 散落文件')

    for pid, (nm, exe, born) in list(seen.items()):
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass
    time.sleep(TEARDOWN_S)
    # 兜底：按 exe 路径清扫包内残留（含启动器早退后孤儿化的应用进程）
    for pid in pkg_app_procs(pkg_dir, None):
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass
    time.sleep(0.8)
    j_left = (clean_pkg_junctions(os.environ['APPDATA'], pkg_dir)
              + clean_pkg_junctions(os.environ['LOCALAPPDATA'], pkg_dir))
    rt_left = len(pre_clean_runtime_data(data_dir))

    ran = bool(seen) or first_window is not None
    if ran and fresh > 0:
        verdict = 'PASS'
    elif ran:
        verdict = 'WARN'
    else:
        verdict = 'FAIL'
    rec.update(
        children=[f'{v[0]}@{v[2]:.1f}s' for v in seen.values()],
        children_count=len(seen),
        first_window_s=first_window,
        window_titles=windows[:3],
        launcher_gone=launcher_gone,
        fresh_files=fresh,
        post_data=post_data,
        leaks=leaks,
        junctions=junctions,
        junction_left=j_left,
        rt_left=rt_left,
        elapsed=round(time.time() - t0, 1),
        verdict=verdict,
    )
    return rec


def md_report(results):
    lines = ['# 便携项目启动与数据落地全量核查 v3（干净环境，2026-10-17）', '',
             f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}；'
             f'单项流程：预清RuntimeData→快照→**剥离ELECTRON_RUN_AS_NODE/NODE_OPTIONS的干净环境**启动'
             f'(stdin=PIPE)→轮询子进程+窗口≤{CHILD_WAIT_S}s→观察写入{WRITE_SETTLE_S}s→'
             f'快照对照→有序收场→清残留', '',
             '判定：`PASS`=见到窗口或应用子进程且 Data 有新写入；'
             '`WARN`=进程/窗口出现过但 Data 无新写入；`FAIL`=两者皆无。', '',
             '| 项目 | 子进程 | 首窗 | 窗口标题 | Data 新增 | Data 总量 | 泄漏 | 结论 |',
             '|---|---|---|---|---|---|---|---|']
    for r in results:
        if r.get('error'):
            lines.append(f"| {r['name']} | — | — | — | — | — | — | FAIL：{r['error']} |")
            continue
        kids = ', '.join(r['children'][:4])
        if r['children_count'] > 4:
            kids += f" 等{r['children_count']}个"
        if not kids:
            kids = '无'
        leak = '；'.join(r['leaks']) if r['leaks'] else '无'
        pd_ = r['post_data']
        fw = f"{r['first_window_s']}s" if r.get('first_window_s') else '-'
        titles = (r.get('window_titles') or ['-'])[0][:24]
        lines.append(
            f"| {r['name']} | {kids} | {fw} | {titles} | {r['fresh_files']} | "
            f"{pd_['files']}文件/{pd_['size']/1048576:.1f}MB | {leak} | {r['verdict']} |")
    n_pass = sum(1 for r in results if r.get('verdict') == 'PASS')
    n_warn = sum(1 for r in results if r.get('verdict') == 'WARN')
    n_fail = len(results) - n_pass - n_warn
    lines += ['', f'**合计：PASS {n_pass} / WARN {n_warn} / FAIL {n_fail} / 共 {len(results)}**']
    return '\n'.join(lines)


def main():
    only = None
    if '--only' in sys.argv:
        only = sys.argv[sys.argv.index('--only') + 1]
    projs = load_projects()
    if only:
        projs = [p for p in projs if only.lower() in p['name'].lower()]
    print(f'待测 {len(projs)} 个，开始于 {datetime.now():%H:%M:%S}（干净环境）', flush=True)
    results = []
    for i, pr in enumerate(projs, 1):
        print(f'[{i}/{len(projs)}] {pr["name"]} ...', end=' ', flush=True)
        try:
            r = test_project(pr)
        except Exception as e:
            r = dict(name=pr['name'], exe=pr['exe'], error=f'probe-exception: {e}', verdict='FAIL')
        results.append(r)
        print(f"{r.get('verdict')} {r.get('elapsed','?')}s 子进程={r.get('children_count','?')} "
              f"首窗={r.get('first_window_s','-')} 新增={r.get('fresh_files','?')} "
              f"RT残留={r.get('rt_left','?')}", flush=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    jp = os.path.join(REPORT_DIR, f'便携项目冒烟明细v3-{STAMP}.json')
    mp = os.path.join(REPORT_DIR, f'便携项目启动与数据落地核查报告v3-{STAMP}.md')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with open(mp, 'w', encoding='utf-8') as f:
        f.write(md_report(results))
    print('DONE ->', jp)
    print('DONE ->', mp)


if __name__ == '__main__':
    main()
