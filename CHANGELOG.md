# 更新日志

本项目采用「配方开源（MIT）+ 二进制不随仓库分发」的模式。版本号遵循语义化版本。

## [1.4.0] — 2026-10-18

### 修复
- **★ Electron / VSCode 系的 `~/.xxx` 点目录完全漏管（数据保存不对）**
  - 根因：`app.getPath('userData')` 走 `SHGetKnownFolderPath`，**不读 %APPDATA% 环境变量**；
    VSCode 系的扩展/插件/ripgrep 走 `os.homedir()` → `%USERPROFILE%\.<name>`。
    只做环境变量重定向对这两条路径**无效**
  - 实测：`~/.trae-cn` 102.9MB、`~/.ai_completion` 4.8MB 在运行时被改写；
    `.codeartsdoer` 1209MB、`.cherrystudio` 281MB 等长期堆积在宿主
  - 修法：junction 接管（沿用"先 robocopy 合并进 Data 再移除，不丢数据"语义）
  - 涉及：TraeCN / CherryStudio / CodeArts / KukuAI / Cursor 共 7 个点目录
  - 刻意不做：`~/.workbuddy`、`~/.codebuddy`（宿主实例正在使用，接管会打断会话）
- **★ 卡顿：QQPortable 冷启动 20.9s → 1.2s**
  - 实测 `powershell -File` 单次 **1.37s**、`cmd /c` 单次 **0.082s**（差 16 倍）；
    QQ 一次冷启动派生 24 次子进程调用
  - 修法：junction 三路判定改 NSIS 原生快速路径（写探针文件判定 0/3），
    只有"联接存活但不属本包"才回退 PowerShell。QQ 系 PowerShell 24 → 1 次
  - 涉及：QQ / QQNT / TIM / Weixin / WXWork
- **WPS 五个入口完全没有 Custom.nsh** → 无自愈钩子（上一轮 76 份统计漏掉了它）
  - 已补最小 Custom.nsh（只含自愈钩子）+ 重编 5 个 exe
  - `build_launcher.py` 新增 AppID 覆盖参数以支持多入口包
- **ZoomPortable 缺 TEMP/TMP 重定向**（全库唯一），临时文件落宿主，双树已补

### 新增
- `audit_launch_health.py` / `scan_host_leak.py` / `scan_redirect_coverage.py` /
  `probe_leak_perf.py` / `fix_dot_home_dirs.py` / `opt_fast_junction_probe.py`
- `docs/04-避坑手册.md` §1.7（两条落盘路径）、§1.8（PowerShell 1.37s）
- `docs/reports/全库启动-数据-卡顿专项检查报告-20261018.md`

### 精简
- 移除 `Qoder CN IDEPortable.ini`（无对应 exe，永不被读取），备份保留

### 已知遗留
- 多数 Electron 包 WM_CLOSE 关不掉（最小化到托盘），被强杀会留 junction，
  下次启动由 Scavenge + 自愈钩子接管
- `%LOCALAPPDATA%\Temp\nope\` 约 1.7GB 为构建期临时副本，非运行期产物
- `WorkBuddyPortable` 的 exe 仍被宿主运行中实例占用，本轮未重编（钩子已注入）

## [1.3.0] — 2026-10-18

### 修复（阻断级）
- **★「上次未正常关闭」残留导致便携包拒绝启动**（QQNTPortable 实测复现）
  - 现象：双击弹 `... did not close properly ... Please then start ... again
    manually.`，点确定后**什么都没发生**，程序根本没启动 —— 用户视角就是
    「一直打不开 / 启动异常」，且不知道还要再点一次
  - 根因（PAL 源码实证）：`Data\PortableApps.comLauncherRuntimeData-<BaseName>.ini`
    存在时，PAL 只弹 `$(LauncherCrashCleanup)` 就走 Post/Unload，
    **永不进入 Execute**；该 ini 仅在正常收尾时删除，任何强杀/断电/崩溃都会留下。
    ini 里没有任何开关能关掉这个行为
  - 修法：新增 `Custom.nsh_Init` 自愈钩子（PAL `Function Init` 第 1 段，
    早于上面的判断）：先用 `FindFirst` 探测（无残留则零开销跳过），
    再确认「除自身外包内无存活进程」才删除；有存活实例则完全保持 PAL 原有行为，
    不绕过"已在运行"保护、不破坏 junction 互斥
  - 影响面：全库 **38/39 个包**（PAL 通用行为，非 QQNT 独有）
- **为什么之前一直没发现**：冒烟脚本 `smoke_real.py` / `smoke_all_projects.py`
  的 `pre_clean_rt()` 会主动删掉这个 ini，**冒烟永远 PASS**，问题只在真实用户
  手里复现（工具注释里其实早有记载，但只在测试侧绕过，产品侧从未修）

### 新增
- `_shared/tools/fix_launcher_rtdata.py`：幂等注入自愈钩子（默认 dry-run，
  需 `--apply`），同时覆盖 `portableapps/` 与 `dist/` 双树
- `_shared/tools/build_launcher.py`：PAL 启动器重编译器（从 `Work/_analysis`
  迁入，路径改为自适应 + `PAL_TOOLCHAIN` 可覆盖）
- `docs/04-避坑手册.md` §1.6 与速查表新增该坑

### 实测
- QQNT 修复前：残留存在 → 弹框 → 不启动（75s 观察始终无程序）
- QQNT 修复后：残留存在 → 无弹框 → t+14s 程序正常起来
- QQNT 3 轮冷启动（不做任何预清理）：PASS / PASS / PASS，
  junction 6 条建链与拆链全对称、runtime ini 零残留
- 重编 38 个启动器 exe；`audit_repo --tree dist` 39/39、
  `check_custom_nsh` 全库无病态、Custom.nsh 编码 76/76 UTF-8 无 BOM

### 已知遗留
- `WorkBuddyPortable` 的 exe 因便携实例正在运行被占用，本次**未重编**
  （`Can't open output file`）。其 `Custom.nsh` 已注入钩子，关闭该实例后
  执行 `python _shared/tools/build_launcher.py WorkBuddyPortable/dist/WorkBuddyPortable`
  即可补上；旧 exe 功能不受影响

---

## [1.2.0] — 2026-10-18

### 新增
- **一包一更新脚本**：39 个便携包目录各生成 `dist/<Pkg>/update.py`，
  自包含引擎（不依赖 `_shared/`，整个目录拷走也能单独运行）
- 更新策略生成器：`_shared/tools/update_template.py`（引擎模板）
  + `gen_update_strategies.py`（39 包 SPEC），改 SPEC 后重生成，不手改产物
- 批量执行器 `_shared/update/runner.py`：并发 subprocess 调用各包
  `update.py --check --json` 并汇总，可出 Markdown 报告
- 事实扫描器 `scan_update_facts.py`：从磁盘读入口 exe / App 子目录 /
  当前版本，避免手抄产生漂移
- `docs/reports/更新策略报告-20261018.md`、`docs/04-避坑手册.md` §8

### 更新源判定（实测，非猜测）
- 7 个在线自动源：Cursor / Feishu / SublimeText（api 2 + html 1）、
  CherryStudio / Joplin / SoloMD / ZenBrowser（github 4）
- 32 个人工接管源：诚实标记 `manual` + `--ingest` 全流程
- **打回 5 个假信号**：TIM `2.1.1`（sea.js）、BaiduNetdisk `2.1.1`
  （badjs-sdk）、Quark `0.1.78`（静态资源）、TraeCN `2.0.0.401`
  （内联 JSON 其他组件）、Foxit `476.233.31.949`（**SVG path 坐标**）

### 修复
- **更新后便携性被破坏**：上游包自带 `Data/`（覆盖 PAL 重定向）与
  自带更新器（`update_installer.exe` 等会把便携版改写成安装版）。
  新增 `post_unpack()`：剥外壳目录 / 剔除 `drop_paths` / 禁用 `disable_exe`。
  禁用清单从磁盘既有的 `*.disabled-by-engine` 反推（4 个包命中）
- **`--rollback` 不可用**：回滚必然是新进程，进程内 `_last_backup` 恒为
  None。改为去备份目录取最新一份，并同步回退 `appinfo.ini`
- **备份落错位置**：`update.py` 在 `dist/<Pkg>/` 下，上溯少了层级，
  备份被写进包目录。改用显式的 `parents[N]`
- **备份无限增长**：新增 `prune_backups(keep=3)`（单份 172MB）
- **appinfo 备份污染包目录**：改为写进备份区，不再落在 `App/AppInfo/`
- **半截下载包**：改 `.part` + 原子改名，并校验 content-length
- **GitHub API 限流（403，未认证 60 次/小时）**：支持 `GITHUB_TOKEN` /
  `GH_TOKEN`（5000 次/小时）；403 给出明确提示；取新失败时退回上次成功的
  结果（状态 `CACHED`），不再把临时故障误报成"策略写错了"
- **批量执行器超时一刀切**：检测 90s / 更新 900s 分开（原统一 180s，
  一个卡住的请求会拖住整批）
- `smoke_real.py` 目标进程猜测错误（`sublimetext.exe` → 实为
  `sublime_text.exe`），补登 11 个包名与进程名不同形的包
- `test_structure.py` 白名单新增 `update.py`

### 实测（3 个包真实升级，全部冒烟 PASS）
- SublimeText 4200 → 4215（html + zip）：剔除上游 Data、禁用自带更新器、
  结构校验 PASS、真启动冒烟 PASS；回滚链路 4215 → 4200 文件与版本号同步退回
- ZenBrowser 1.23.2 → 1.23.3（github + NSIS）：进入 `core/`、禁用 5 个
  自带更新器、结构校验 PASS、真启动冒烟 PASS
- SoloMD 5.0.1 → 5.0.3（github + zip）：结构校验 PASS、真启动冒烟 PASS
- 全库检测：39 包 **0 异常、0 待更新**（7 最新 + 32 人工）

### 实测中额外修掉的 3 个问题
- **PATH 里靠前的 7-Zip 是坏的**：`<本机工具目录>/tools\7z.EXE` 缺 `7z.dll`，
  `7z` 无参数 rc=0（看起来正常）但解包 rc=2，导致 NSIS/Inno 包静默失败。
  改为拿**真实文件**逐个试候选，失败时打印 7z 输出尾巴
- **安装器多层结构**：`zen.installer.exe` 解出 `core/` + `setup.exe`，
  "剥单层外壳"只在只有 1 个顶层项时生效。新增 `strip_root` 字段 + `--strip`
- `smoke_real.py` 猜进程名错两次（`sublime_text.exe` / `zen.exe`），
  表现为"Data 有写入、0 弹框却判 FAIL"，已显式登记

---

## [1.1.0] — 2026-10-18

### 新增
- `_shared/tools/` 生产级工具链（18 个脚本）：静态审计、3 轮动态冒烟、
  CI 结构自检、BOM 剥离、ini 编码矩阵验证等，全部去除绝对路径硬编码，
  仓库根由脚本自身位置推导，支持 `PORTABLEAPPS_ROOT` 覆盖
- `audit_repo.py`：CI 友好结构自检（不依赖任何第三方二进制，clone 即可跑）
- `docs/04-避坑手册.md`（14 KB）：7 大类坑位 + 速查表 + 编解码矩阵
- 仓库根开源配套：`README.md` / `CONTRIBUTING.md` / `LICENSE` / `.gitignore`
  / `CHANGELOG.md` / `CODE_OF_CONDUCT.md` / `.editorconfig` / `SECURITY.md`
  / `.github/`（PR 模板、Issue 模板、CI）
- 文档整体迁入 `docs/`（36 份，含 `archive/` 19 份历史文档），
  文档内绝对路径已按新位置重写 61 处

### 修复
- **WPS 分体启动全部落到首页**：定位到 WPS 2023「首页壳」机制
  （所有组件先落 `Kx<Wps|Et|Wpp|Pdf>PromeMainWindow`），靠 UI Automation
  控制树 + 截图像素哈希取证，穷举 14 组开关后确认唯一可用解
  `/nostartpage`。5 个入口现分别为 首页 / 文字 / 表格 / 演示 / PDF
- **`Custom.nsh` 带 UTF-8 BOM**（`BaiduNetdiskPortable`、
  `CodeArtsAgentPortable` 双树共 4 个文件）：BOM 会让 NSIS 报
  `Invalid command`，已剥离并备份，回归冒烟双 PASS
- **`appinfo.ini` 缺 `[Format]`/`[Control]`**：23 个包的 dist 树用文本级合并补齐，
  保留原注释，改后重新解析校验
- **`ExtractIcon` 路径错误**：`CodeArtsPortable` / `FoxitPDFPortable` /
  `QuarkCloudDrivePortable` 3 包修正
- **工具自身缺陷**：`check_custom_nsh.py` 包名上溯层数少一级，
  导致 38 个包全输出 `[dist]`；`smoke_real.py` 未登记的包直接 `KeyError` 崩溃

### 已确认非缺陷（留档）
- 11 个 Electron 类包重定向 `USERPROFILE`：实测可正常启动与写入，
  但存在崩溃风险，标记为已知风险而非阻断项
- `MiaoshouPortable.ini` 为 UTF-16LE：因含中文路径（`妙手\妙手.exe`）必须保持，
  **禁止转 UTF-8**（转码会直接导致启动失败，见 `docs/04-避坑手册.md` §1.4）

## [1.0.0] — 2026-10-17

### 新增
- 39 个便携软件包的双树结构：`portableapps/`（构建输入，仅元数据）
  与 `dist/`（可运行产物，含真实程序文件）
- 全库 3 轮连续冒烟：43 个单元 × 3 轮，全 PASS
- 数据落地核查：39/39 包 `APPDATA` / `LOCALAPPDATA` 均重定向到
  `%PAL:DataDir%`

### 变更
- WPS 拆分为 5 个入口（主程序 / 文字 / 表格 / 演示 / PDF）
- 项目从 `Work/` 迁入独立仓库 `PortableApps/`
