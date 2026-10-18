# _shared —— 便携项目公共工具链

本目录**不是**一个便携项目，而是 39 个独立项目（`<仓库根>/<项目>`）
共用的构建与维护基础设施。

## 为什么要集中

PortableApps.com Launcher（PAL）工具链含 NSIS 编译器，约 **14 MB**。
若复制进 39 个项目需 **546 MB**冗余；且更新一次要同步 39 处。
故集中到本目录，各项目经 `toolchain.py` 解析引用，**不硬编码任何绝对路径**。

## 目录结构

```
_shared/
├── toolchain.py                工具链定位器（各项目 scripts/toolchain.py 转发到此）
├── toolchain/
│   └── PortableApps.comLauncher/   PAL 官方源码树（含 makensis.exe）
├── build_launcher.py           启动器编译器：注入 appinfo.ini + Launcher/*.ini → makensis
├── update_engine.py            八阶段更新流水线
├── gen_update_configs.py       从各项目结构重新生成 configs/*.yaml
├── configs/<项目>.yaml         39 份项目更新策略
└── *.py                        迁移、校验、审计、报告脚本
```

## 工具链解析优先级

`toolchain.py` 按以下顺序查找，找不到则报错并给出修复建议：

1. 环境变量 `PAF_TOOLCHAIN`
2. `<项目>/../../_shared`（标准布局：`PortableApps\<项目>\scripts` → `PortableApps\_shared`）
3. `<项目>/../_shared`
4. `<项目>/toolchain`（单项目自带）

自检：

```bash
python _shared/toolchain.py
```

## 常用命令

```bash
# 构建任一项目（在项目目录内执行）
cd <仓库根>/<项目>
python scripts\build-portable.py

# 结构校验
python tests\test_structure.py            # 含 dist 产物校验
python tests\test_structure.py --ini-only # 仅校验仓库骨架与 ini

# 全量合规审计（39 项目）
python _shared\final_audit.py

# 更新流水线（在 _shared 下执行）
cd _shared
python update_engine.py report                 # 全部项目的更新状态报告（无参数）
python update_engine.py detect --project CursorPortable
python update_engine.py detect --all

# 重新生成全部更新配置
python gen_update_configs.py

# 批量补齐骨架（新增项目时用）
python scaffold.py            # 预演
python scaffold.py --execute  # 执行
```

## 更新流水线

```
detect → download/ingest → extract → diff → test → stage → release（门禁） → rollback
```

强制约束：

- 破坏性操作默认 `dry_run=True`，需显式 `--execute` 才落地
- `Data/` 目录只读，任何阶段不写入/删除用户数据
- 状态文件原子写（临时文件 + `os.replace`）
- 仅最新版本接收更新；保留最近 3 个版本以支持回滚

### 版本源诚实原则

`configs/<项目>.yaml` 的 `version_source.type` 为 `manual` 表示**尚无已实证的
在线版本源**——此时由人工下载安装包后用 `ingest` 子命令接管后续全流程，
**不会虚构 URL 或版本号**。已实证的源才会联网检测。

当前已实证 7 个：`JoplinPortable` `SoloMDPortable` `ZenBrowserPortable`
（`github_releases`）、`CursorPortable` `FeishuPortable`（`api`）、
`FSCapturePortable` `ReNamerPortable`（`lanzou_folder`）。

### 维护节奏

| 策略 | 含义 | 项目 |
| --- | --- | --- |
| `weekly` | P0 周检 | Cursor / Qoder 系 / CodeArts 系 / CodeBuddy / Comate / JoyCode / WorkBuddy / TraeCN |
| `monthly` | 月检 | 其余常规项目 |
| `blocked` | 暂不接入 | WinClaw / LobsterAI |
| `manual_only` + `none` | 不自动更新/不自动发布 | FoxitPDF / SublimeText / WPSOffice（任务书特例） |

## 重新获取 PAL 工具链

若 `toolchain/PortableApps.comLauncher/` 丢失，从官方获取后放回原位：

<https://portableapps.com/development/launcher/>