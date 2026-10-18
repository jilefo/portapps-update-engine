# -*- coding: utf-8 -*-
import io
import os
import sys
from pathlib import Path

# >>> 路径自适应（开源迁移注入，勿删）：仓库根由本文件位置推导，
#     不再写死绝对路径，可用 PORTABLEAPPS_ROOT 环境变量覆盖。
import os as _os
from pathlib import Path as _Path
REPO_ROOT = (_os.environ.get("PORTABLEAPPS_ROOT")
             or str(_Path(__file__).resolve().parents[2]))
# <<< 路径自适应

# 产品根唯一解析处（dist 迁移到 D:\Portapps 后由它接管产品路径）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _paths                                     # noqa: E402

r"""给缺失 DirectoryMoveOK 的包补上 [Launch] DirectoryMoveOK=yes
背景：包从 Work\ 迁移到 PortableApps\ 后，PAL 的 DirectoryMoving 段检测到
路径变更；launcher.ini 未设置 DirectoryMoveOK 时走 MB_YESNO 警告弹窗
（launcher 挂在对话框上永不启动，tasklist 主窗口标题看不出异常）。
产品树（迁移前 dist/、迁移后产品根）与 portableapps 源码树两处都补，
保持编码与 BOM 状态不变。
"""
ROOT = REPO_ROOT
TARGETS = ['AiPyProPortable', 'ComatePortable', 'JoyCodePortable', 'MiaoshouPortable',
           'MiniMaxCodePortable', 'OfficeAcePortable', 'TodayCNPortable', 'CodeArtsAgentPortable']


def read_raw(path):
    return open(path, 'rb').read()


def decode(raw):
    if raw[:3] == b'\xef\xbb\xbf':
        return raw.decode('utf-8-sig'), 'utf-8-sig'
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16'), 'utf-16'
    try:
        return raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return raw.decode('gb18030'), 'gb18030'


def patch(path):
    raw = read_raw(path)
    text, enc = decode(raw)
    if 'DirectoryMoveOK' in text:
        return f'{os.path.basename(path)}: 已有 DirectoryMoveOK，跳过'
    # 在 [Launch] 段首行后插入
    lines = text.splitlines(True)
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip().lower() == '[launch]':
            out.append('DirectoryMoveOK=yes\n')
            inserted = True
    if not inserted:
        return f'{os.path.basename(path)}: 未找到 [Launch] 段，跳过'
    with io.open(path, 'w', encoding=enc, newline='') as f:
        f.write(''.join(out))
    return f'{os.path.basename(path)}: 已插入 DirectoryMoveOK=yes'


for proj in TARGETS:
    # 产品树：迁移前 <Repo>/<Pkg>/dist/<Pkg>，迁移后 <产品根>/<Pkg>
    p = _paths.product_dir(proj) / 'App' / 'AppInfo' / 'Launcher' / (proj + '.ini')
    if p.is_file():
        print(proj, '|产品|', patch(p))
    else:
        print(proj, '|产品| ini 不存在:', p)
    p2 = os.path.join(ROOT, proj, 'portableapps', 'App', 'AppInfo', 'Launcher', proj + '.ini')
    if os.path.isfile(p2):
        print(proj, '|src |', patch(p2))
    else:
        print(proj, '|src | ini 不存在（占位式项目正常）')
