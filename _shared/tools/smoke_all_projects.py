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
"""便携项目全量冒烟探针 v2

修复 v1 缺陷：
1. 启动前预清 RuntimeData ini（否则 PAL 走 CrashCleanup 分支永不 Exec ——
   自锁：Init 每次重写 ini，被弹窗阻塞的启动又留下新 ini）
2. junction 检测改用 GetFileAttributesW 的 REPARSE_POINT 属性
   （python 的 os.path.islink 对 mklink /J 联接返回 False！）
3. teardown 先杀应用子进程、等启动器自行收尾，再兜底强杀
4. verdict：子进程见过(含秒退)或 Data 有写入 即 PASS

单项流程：预清RT->快照->启动->轮询子进程≤CHILD_WAIT_S->观察写入->
快照对照->有序收场->清残留。单项异常全部 try/except 隔离。
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
CHILD_WAIT_S = 20
WRITE_SETTLE_S = 6
TEARDOWN_S = 3
REPORT_DIR = os.path.join(REPO_ROOT, "docs", "reports")
STAMP = datetime.now().strftime('%Y%m%d-%H%M%S')

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
         cmd='wpspdf.exe'),
]
SKIP = {'WPSOfficePortable'}

FILE_ATTRIBUTE_REPARSE_POINT = 0x0400


def is_junction(path):
    """junction/symlink 判定：python islink 对 mklink /J 返回 False，必须看属性"""
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
    """返回清理掉的文件名列表；PAL CrashCleanup 自锁的唯一解药"""
    killed = []
    for f in glob.glob(os.path.join(data_dir, 'PortableApps.comLauncherRuntimeData-*.ini')):
        try:
            os.remove(f)
            killed.append(os.path.basename(f))
        except OSError:
            pass
    return killed


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
    """os.rmdir 对 junction 只删联接本身（RemoveDirectory 语义）"""
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
        return 0
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
    return 0


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
        # WPS 分体：Data 在项目 dist 根
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
        proc = subprocess.Popen([pr['exe']], cwd=pkg_dir)
    except OSError as e:
        rec.update(error=f'launch-failed: {e}', children=[], fresh_files=0,
                   post_data=pre_data, leaks=[], verdict='FAIL')
        return rec

    # 轮询子进程（0.5s 粒度，秒退进程也能命中）
    seen = {}
    deadline = t0 + CHILD_WAIT_S
    launcher_gone = False
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            kids = psutil.Process(proc.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            launcher_gone = True
            break
        for k in kids:
            if k.pid in seen:
                continue
            try:
                exe = k.exe()
            except Exception:
                exe = '?'
            seen[k.pid] = (k.name(), exe, time.time() - t0)
        if seen:
            # 命中后再观察 3 个周期确认存活
            time.sleep(1.5)
            try:
                still = {k.pid for k in psutil.Process(proc.pid).children(recursive=True)}
            except psutil.NoSuchProcess:
                still = set()
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

    # 有序收场：先杀应用子进程，给启动器 3s 自行走 PostPrimary 收尾
    for pid, (nm, exe, born) in list(seen.items()):
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass
    time.sleep(TEARDOWN_S)
    # 兜底强杀启动器
    try:
        proc.kill()
    except Exception:
        pass
    time.sleep(0.8)
    j_left = (clean_pkg_junctions(os.environ['APPDATA'], pkg_dir)
              + clean_pkg_junctions(os.environ['LOCALAPPDATA'], pkg_dir))
    rt_left = len(pre_clean_runtime_data(data_dir))

    verdict = 'PASS' if (seen or fresh > 0) else 'FAIL'
    if seen and fresh == 0:
        verdict = 'WARN'
    rec.update(
        children=[f'{v[0]}@{v[2]:.1f}s' for v in seen.values()],
        children_count=len(seen),
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
    lines = ['# 便携项目启动与数据落地全量核查（2026-10-17）', '',
             f'生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}；'
             f'单项流程：预清RuntimeData→快照→启动→轮询子进程≤{CHILD_WAIT_S}s→'
             f'观察写入{WRITE_SETTLE_S}s→快照对照→有序收场→清残留', '',
             '判定：`PASS`=见到应用子进程且有数据写入；`WARN`=进程起来了但 Data 无新写入；'
             '`FAIL`=无子进程且无写入（含启动即退/被弹窗阻塞）。', '',
             '| 项目 | 子进程 | Data 新增 | Data 总量 | 泄漏 | 结论 |',
             '|---|---|---|---|---|---|']
    for r in results:
        if r.get('error'):
            lines.append(f"| {r['name']} | — | — | — | — | FAIL：{r['error']} |")
            continue
        kids = ', '.join(r['children'][:4])
        if r['children_count'] > 4:
            kids += f" 等{r['children_count']}个"
        if not kids:
            kids = '无'
        leak = '；'.join(r['leaks']) if r['leaks'] else '无'
        pd_ = r['post_data']
        lines.append(
            f"| {r['name']} | {kids} | {r['fresh_files']} | "
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
    print(f'待测 {len(projs)} 个，开始于 {datetime.now():%H:%M:%S}', flush=True)
    results = []
    for i, pr in enumerate(projs, 1):
        print(f'[{i}/{len(projs)}] {pr["name"]} ...', end=' ', flush=True)
        try:
            r = test_project(pr)
        except Exception as e:
            r = dict(name=pr['name'], exe=pr['exe'], error=f'probe-exception: {e}', verdict='FAIL')
        results.append(r)
        print(f"{r.get('verdict')} {r.get('elapsed','?')}s 子进程={r.get('children_count','?')} "
              f"新增={r.get('fresh_files','?')} RT残留={r.get('rt_left','?')}", flush=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    jp = os.path.join(REPORT_DIR, f'便携项目冒烟明细-{STAMP}.json')
    mp = os.path.join(REPORT_DIR, '便携项目启动与数据落地核查报告-20261017.md')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with open(mp, 'w', encoding='utf-8') as f:
        f.write(md_report(results))
    print('DONE ->', jp)
    print('DONE ->', mp)


if __name__ == '__main__':
    main()
