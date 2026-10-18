# `_shared/tools/` —— 生产级工具链

本目录是**可复用**的验收/修复工具（一次性调试脚本已剔除）。所有脚本
**不硬编码绝对路径**：仓库根由脚本自身位置推导（`_shared/tools/x.py` → 上溯两级），
也支持 `PORTABLEAPPS_ROOT` 环境变量覆盖，换机器/换盘符直接可用。

```bash
# 直接跑（Windows 示例）
python _shared/tools/audit_production.py        # 静态生产级审计
python _shared/tools/check_custom_nsh.py        # Custom.nsh 硬约束扫描
python _shared/tools/smoke_real.py CursorPortable 25
```

> 动态冒烟类脚本需要 `psutil`：`pip install psutil`。

## 1. 只读检查类（随时可跑，不改任何文件）

| 脚本 | 作用 | 关键输出 |
|---|---|---|
| `audit_production.py` | 39 包静态审计：开源完备性 9 项 / PAL 结构 / 数据落地重定向 / 风险项 | `docs/reports/生产级审计-<stamp>.md` + `.json` |
| `check_custom_nsh.py` | 扫描全部 `Custom.nsh` 的 PowerShell 内联病态（`''` 引号、裸 `$变量`、`^|` 管道） | 逐包 `无病态` / `病态 N 处` |
| `enum_portable_projects.py` | 枚举全部项目：启动器 exe、`appinfo.ini`、`Data` 现状 | 控制台清单 |
| `scan_broken_quotes.py` | NSIS 引号配对/病态行扫描 | 问题行号 |
| `scan_sick_lines.py` | `Custom.nsh` 病态行扫描（与上一项互补，覆盖不同模式） | 问题行号 |
| `verify_migration.py` | 校验源树 → 目标树迁移后逐文件一致性 | 差异清单 |
| `audit_launch_health.py` | **启动/数据/卡顿**静态审计（双树）：exe↔ini 配对、`ProgramExecutable` 真实性、重定向完整性、Data 落地、App 内混入数据目录、`Custom.nsh` 编码与自愈钩子 | `ERROR/WARN` 清单 + 卡顿榜 |
| `scan_host_leak.py` | 宿主侧泄漏扫描：`%APPDATA%`/`%LOCALAPPDATA%`/`%ProgramData%`/Documents/`%USERPROFILE%` 下哪些是**真实目录**（非 junction）并归属到包 | junction 清单 + 疑似泄漏清单 |
| `scan_redirect_coverage.py` | 按「接管手段」给 39 包分级（junction / 仅环境变量 / 是否重定向 USERPROFILE） | 分级表 |

## 2. 动态冒烟类（会真启动应用，务必先存档）

| 脚本 | 作用 | 判定口径 |
|---|---|---|
| `smoke_real.py <Pkg> [秒数]` | 单包真启动探针 | 目标进程出现 **且** `Data` 有新写入 |
| `smoke_sample.py <Pkg>...` | 批量抽样冒烟（复用 `smoke_real`） | 同上 |
| `smoke_all_projects.py` | 全量 43 单元冒烟（含 WPS 4 分体） | 见过子进程或 Data 有写入即 PASS |
| `smoke_3rounds.py` | **3 轮连续全库冒烟**（QQ 系每题前做冷启动清场） | 3 轮矩阵 + 汇总报告 |
| `smoke_clean.py` | 被 `smoke_3rounds` 依赖的底层探针（预清 RuntimeData → 剥污染环境变量 → 启动 → 轮询 → 有序收场） | 库，不单独跑 |
| `smoke_wps_final.py` | WPS 5 入口专项验收（首页 / 文字 / 表格 / 演示 / PDF）+ 弹窗监控 | 每入口期望界面 + 弹窗数 |
| `probe_leak_perf.py` | **实测探针**：一次跑同时拿「宿主泄漏」与「卡顿耗时」。与 smoke 的关键区别是**不预清理**运行时数据（走真实用户路径），并记录 PS/cmd 派生次数 | `t_child` / `ps_spawned` / `cmd_spawned` / `t_exit` / 宿主新增变更目录 |

**冒烟前必读**：`PortableApps.comLauncherRuntimeData-*.ini` 残留会让 PAL 走
`CrashCleanup` 分支永不 `Exec`（自锁），探针已内置"预清 RuntimeData"；
junction 检测必须用 `GetFileAttributesW` 的 `REPARSE_POINT` 属性
（`os.path.islink` 对 `mklink /J` **返回 False**）。

## 3. 修复类（会写文件，均已内置 `.bak-<tag>-<时间戳>` 备份）

| 脚本 | 作用 | 护栏 |
|---|---|---|
| `fix_appinfo_production.py` | 修 `ExtractIcon` 路径 + 补齐 `appinfo.ini` 缺失的 `[Format]`/`[Control]`（文本级合并，保留原注释） | 改前备份 `.bak-appfix-<stamp>`，改后重新解析校验 |
| `fix_directory_move_ok.py` | 修迁移后 `DirectoryMoving` 误判 | 备份后改 |
| `sync_portableapps.py` | 把 `dist` 侧已修好的 `Custom.nsh` 同步回 `portableapps` 源树 | 内容相同则跳过 |
| `normalize_ini_encoding.py` | ⚠️ **危险**：UTF-16LE → UTF-8 转码 | **含非 ASCII 直接拒绝**（见下） |
| `fix_launcher_rtdata.py` | 给所有 `Custom.nsh` 注入 `Custom.nsh_Init` 自愈钩子，根治「上次未正常关闭」残留导致 PAL 拒绝启动（详见 [`docs/04-避坑手册.md` §1.6](../../docs/04-避坑手册.md)） | 幂等（已有钩子则跳过）；默认 dry-run，需 `--apply`；不依赖 LogicLib |
| `fix_dot_home_dirs.py` | 接管 `%USERPROFILE%\.<name>` 点目录（Electron/VSCode 系漏管的那条落盘路径，详见 §1.7） | 默认 dry-run；宿主真实目录先 robocopy 进 Data 再移除（不丢数据）；已是 junction 不抢不拆；刻意跳过 `~/.workbuddy`、`~/.codebuddy` |
| `opt_fast_junction_probe.py` | 卡顿优化：junction 三路判定改 **NSIS 原生快速路径**，只有真正冲突才回退 PowerShell（详见 §1.8） | 默认 dry-run；快速路径不读包名，对含 `NP_JunctionProbe` 的包无损适用 |

## 3b. 启动器编译类（改了 `Custom.nsh` / `Launcher\*.ini` 必须走这一步）

| 脚本 | 作用 |
|---|---|
| `build_launcher.py` | 调 `makensis` 重新编译 PAL 启动器 exe |

```bash
python _shared/tools/build_launcher.py QQNTPortable/dist/QQNTPortable
```

要点：

- **`Custom.nsh` 是编译进 exe 的**，只改文件不重编 = 没改（这是本库最容易被忽略的一条）。
- 工具链默认取 `<仓库根>/_shared/toolchain/PortableApps.comLauncher`，可用 `PAL_TOOLCHAIN` 覆盖。
- Git-Bash 下必须设 `MSYS2_ARG_CONV_EXCL=*`，否则 `/D` 参数会被改写成路径。
- 目标 exe 若正在运行，makensis 会报 `Can't open output file`——关掉该便携包再编。 |

## 4. 验证类

| 脚本 | 作用 |
|---|---|
| `test_ini_encoding_matrix.py` | ini 编码 × 中文路径启动矩阵实测 |

### ⚠️ ini 编码矩阵（本仓库最重要的血泪结论）

| 文件 | 编码要求 | 错用的后果 |
|---|---|---|
| `Custom.nsh` | UTF-8 **无 BOM** | 带 BOM → NSIS 报 `Invalid command` |
| `appinfo.ini` | UTF-8 即可 | — |
| `Launcher\*.ini` **含中文路径** | **必须 UTF-16LE** | 转 UTF-8（**带不带 BOM 都会挂**）→ NSIS 按 ANSI 解码 → 中文路径乱码 → 程序起不来 |

2026-10-18 曾把 `MiaoshouPortable.ini`（`ProgramExecutable=妙手\妙手.exe`）从 UTF-16LE
转成 UTF-8，直接造成该包 2 轮冒烟 FAIL（`子进程 0 / Data 0`）。
`normalize_ini_encoding.py` 已加"含非 ASCII 即拒绝转码"护栏，把教训固化在工具层。

## 4b. 更新策略类

| 脚本 | 作用 |
|---|---|
| `scan_update_facts.py` | 只读扫描全部包，产出 `_shared/update/_facts.json`（入口 exe / App 子目录 / 当前版本 / 既有配置）。生成策略前先跑它 |
| `update_template.py` | **更新脚本模板**（引擎内联，占位符写成合法字面量故可 compile）。不要直接运行 |
| `gen_update_strategies.py` | 读模板 + `_facts.json` + 磁盘上的 `*.disabled-by-engine` 痕迹，生成 39 个 `dist/<Pkg>/update.py` |
| `_shared/update/runner.py` | 批量执行器：并发 subprocess 调各包 `update.py --check --json` 并汇总，可出报告 |

生成物不是 `_shared/` 下的脚本，而是**每个便携包目录里的
`dist/<Pkg>/update.py`**——因为那个目录常被整个拷走，脚本必须自包含。

```bash
python _shared/tools/scan_update_facts.py            # 刷新事实
python _shared/tools/gen_update_strategies.py        # 生成/覆盖
python _shared/update/runner.py --check --all --report
```

改策略请改 `gen_update_strategies.py` 里的 `SPEC` 后重新生成，
**不要手改 `dist/<Pkg>/update.py`**（下次生成会被覆盖）。
详细设计与踩坑见 `docs/reports/更新策略报告-20261018.md`
与 `docs/04-避坑手册.md` §8。

## 5. 与文档的关系

- 使用流程见 `docs/03-构建与发布.md`
- 验收口径见 `docs/05-验收与排查.md`
- 全部坑位与证据见 `docs/04-避坑手册.md`
