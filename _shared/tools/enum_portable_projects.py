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
"""枚举 PortableApps 下全部项目：启动器 exe、appinfo.ini、Data 目录现状"""
import configparser
import json
import os
import sys

ROOT = REPO_ROOT


def read_ini(path):
    for enc in ('utf-8-sig', 'utf-16', 'gb18030'):
        try:
            with open(path, encoding=enc) as f:
                cp = configparser.ConfigParser(interpolation=None)
                cp.read_file(f)
                return cp
        except (UnicodeDecodeError, UnicodeError):
            continue
        except configparser.Error:
            return None
    return None


def scan():
    projects = []
    for name in sorted(os.listdir(ROOT)):
        proj = os.path.join(ROOT, name)
        if not os.path.isdir(proj) or name.startswith('_'):
            continue
        dist = os.path.join(proj, 'dist')
        if not os.path.isdir(dist):
            projects.append(dict(name=name, error='no dist'))
            continue
        # dist\<Pkg>\<Pkg>.exe
        inner = None
        for d in os.listdir(dist):
            p = os.path.join(dist, d)
            if os.path.isdir(p) and d == name:
                inner = p
                break
        if inner is None:
            # 兜底：dist 下唯一目录
            dirs = [d for d in os.listdir(dist) if os.path.isdir(os.path.join(dist, d))]
            if len(dirs) == 1:
                inner = os.path.join(dist, dirs[0])
        exe = None
        if inner:
            cand = os.path.join(inner, name + '.exe')
            exe = cand if os.path.isfile(cand) else None
        # appinfo
        appinfo = None
        cmd = None
        if inner:
            ai = os.path.join(inner, 'App', 'AppInfo', 'appinfo.ini')
            if os.path.isfile(ai):
                cp = read_ini(ai)
                if cp and cp.has_section('Launch'):
                    cmd = cp.get('Launch', 'Command', fallback=None)
                    appinfo = os.path.relpath(ai, proj)
            if cmd is None:
                ai2 = os.path.join(inner, 'App', 'AppInfo', 'Launcher', 'Custom.nsh')
                if os.path.isfile(ai2):
                    appinfo = (appinfo or '') + ' +Custom.nsh'
        # Data 现状
        data = os.path.join(inner, 'Data') if inner else None
        data_stat = None
        if data and os.path.isdir(data):
            nf = 0
            tot = 0
            last = 0.0
            for root, dirs, files in os.walk(data):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        st = os.stat(fp)
                    except OSError:
                        continue
                    nf += 1
                    tot += st.st_size
                    last = max(last, st.st_mtime)
            data_stat = dict(files=nf, size=tot, last_mtime=last)
        projects.append(dict(
            name=name,
            layout='embedded' if os.path.isdir(os.path.join(proj, 'portableapps')) else 'placeholder',
            exe=exe,
            cmd=cmd,
            appinfo=appinfo,
            data_files=None if data_stat is None else data_stat['files'],
            data_size=None if data_stat is None else data_stat['size'],
        ))
    return projects


if __name__ == '__main__':
    rows = scan()
    ok = [r for r in rows if r.get('exe')]
    bad = [r for r in rows if not r.get('exe')]
    print(json.dumps(dict(total=len(rows), with_exe=len(ok), no_exe=bad), ensure_ascii=False, indent=1))
    with open(os.path.join(os.path.dirname(__file__), '_projects_index.json'), 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print('index ->', os.path.join(os.path.dirname(__file__), '_projects_index.json'))
