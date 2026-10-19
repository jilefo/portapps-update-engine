# 更新日志

本项目采用「配方开源（MIT）+ 二进制不随仓库分发」的模式。版本号遵循语义化版本。

## [1.7.0] — 2026-10-19

### 新增
- `_shared/tools/migrate_dist.py` —— dist → 产品根逐包原子迁移工具：同卷 `os.rename`
  （零拷贝、零额外空间、原子），四道安全栅（进程占用检查 / 预迁移逐文件 SHA-256
  manifest / 包内绝对目标 junction 重定点 / 迁移后全等比对），
  另附 `dist` 根额外产物搬运与空目录清理
- `_shared/_paths.py` —— 产品根路径唯一解析处（`PORTAPPS_ROOT` >
  `_shared/portapps_root.txt` > 内置默认 `D:\Portapps` > 回退仓库内旧 `dist/`），
  63 处 dist 硬编码全部收敛，迁移前后工具链零配置自动切换

### 变更
- **可运行产物迁出仓库**：59.12 GB / 598,293 个文件从 `<Repo>/<Pkg>/dist/<Pkg>/`
  整体迁到 `<产品根>/<Pkg>/`（默认 `D:\Portapps`），迁移前后逐文件 SHA-256 全等；
  `update.py` 改由生成器按需产出（生成器即配方），仓库只留
  `_shared/configs/<Pkg>.yaml` + `gen_update_strategies.py`
- 共享产物改为包唯一命名：`<Pkg>-SHA256SUMS.txt` / `<Pkg>-sbom.spdx.json`
  （迁移后 39 包共用一个产物根，旧命名会跨包覆盖）
- 清理 228 个旧版更新引擎遗留的包内 `_shared/update/` 空骨架目录
- `.gitignore` 新增 `_shared/migration/` 与 `_shared/portapps_root.txt`
  （迁移明细可再生成、产品根指针属本机配置）

### 文档
- `docs/01`~`docs/07` 七份现行文档按三树结构（源树 / 产品树 / 工具链）全面更新；
  `04-避坑手册` §2.1、§8.5 补迁移后的探测式仓库根定位说明
- 更新策略 `update.py` 脱离仓库后：靠 `PORTABLEAPPS_REPO` 环境变量或向上探测
  定位仓库，找不到退临时目录，脚本永远能跑

### 迁移后复验（同日完成）
- **39 / 39 全部迁移完成**（含补迁的 WorkBuddyPortable）：
  596,311 文件 / 60,364 MiB（= 58.95 GiB = 63.30 GB 十进制），`verify` 39 PASS / 0 FAIL
- 新增 `audit_launcher_freshness.py`：查 exe 是否落后 Custom.nsh、两棵树 Custom.nsh
  是否一致、是否缺件。首次扫描扫出 2 包 exe 滞后并修好（WorkBuddyPortable
  自 10-17 搁置、SublimeTextPortable 落后 5.6 小时），现 39/39 新鲜
- 新增 `migrate_dist.py repoint` 子命令（幂等、可预览），用于修历史损伤与交叉确认

### 修复
- **junction 重定点整段曾是死代码**：按迁移**前**的路径去 `jp.exists()`，
  而 rename 之后源树整棵消失 → 恒 False → 全部 continue，一个都没修，
  工具却报 PASS。改为存 `rel`、执行时用 `dst / rel` 定位
- 存在性判定 `jp.exists()` → `is_junction(jp)`：前者跟随目标，
  目标悬空即返回 False，恰好跳过最需要修的 junction
- 校验只比 junction **数量** → 改为逐个比 `(rel, inside, target_rel)`；
  此前悬空联接照样判 PASS（真实包上受控复现：旧判定 PASS 假绿、新判定 FAIL）
- `update/runner.py` 的操作提示仍指向已搬走的 `<Pkg>/dist/<Pkg>`，
  改为由 `_paths.product_dir()` 解析

### 包级发布链路（同日完成，此前 64 份 workflow 全坏但全绿）
- **★★ 34 份包级 `release.yml` 曾产出 0 个附件却一路绿灯**：三处缺陷彼此掩盖——
  ① 附件写 `*.7z` 而 `package-paf.py` 只产 `.zip`；② 打包步带 `--checksum-only`
  会跳过打包；③ `package-paf.py` 无产物时 `[WARN] + return 0` 不失败。
  根因是 workflow 由 scaffold 复制生成、之后只用文本替换修路径，
  而**文本替换改字符串、改不了语义**
- **附件路径不再写死**：原先 64 份写 `<Pkg>/dist/*`（工作区相对路径），
  但产物路径由 `_paths.artifact_root()` 动态解析，实测 CI 新克隆上解析出的位置
  与写死的必然不同。改由 `print_artifact_paths.py` 从唯一定义处解析后输出
- **包级发布改发「配方」**：第三方程序被 `.gitignore` 排除（实测 CursorPortable
  源树 `App/` 只入库 9 个元数据文件，产品树 `App/` 有 995 MB 程序），
  CI 上构建出的是"有启动器、无程序"的空壳。改为发布
  `portableapps/` + LICENSE + THIRD_PARTY_NOTICES.md + README.md
- **tag 作用域加包名前缀**：39 份原都用 `v*`，推一个 `v1.7.0` 会触发 39 条流水线
  抢建同一个 Release。改为 `<Pkg>@v*`（如 `CursorPortable@v3.25.6`），
  且不匹配整仓级的 `v[0-9]+.[0-9]+.[0-9]+`
- 补齐 3 个包缺失的 `release.yml` 与 `portableapps.yml`
  （FoxitPDFPortable / SublimeTextPortable / WPSOfficePortable）
- 36 份 `portableapps.yml` 的 `path: <Pkg>/dist/` 在迁移后已不存在，改为动态路径
- 补 `permissions: contents: write`（34 份缺失，会导致建 Release 时 403）

### 新增
- `_shared/scripts/package_formula.py` —— 单包配方打包器。★ 以 **git 跟踪集**为准
  （用 `rglob` 会把本机未跟踪的 `.bak` 备份打进公开产物，实测 18 项混进 2 个垃圾），
  带体积护栏，并报告打包文件数 / 总字节 / 缺失的可选文件
- `_shared/tools/print_artifact_paths.py` —— 产物路径解析，复用
  `package_formula.artifact_paths()` 与 `_paths.artifact_root()`，
  按 GITHUB_OUTPUT 格式输出；**缺产物 exit 1**（不再 WARN 后 return 0）
- `_shared/tools/gen_release_workflows.py` —— 78 份包级 workflow 的唯一生成源，
  `--check` 逐个比对一致性 + YAML 解析，并报出检查量 / 缺失数 / 不符数

### 清理
- 删除 `JoplinPortable` 下 4 份上游模板遗留工作流（`automerge` /
  `build-linux` / `build-windows` / `up-release`）：引用上游的
  `Other/Update/Update.ps1`、`endsWith(github.repository,'Portable')` 在本仓恒假、
  运行时从第三方仓库 master 拉脚本
- 删除 6 个**已入库**的备份文件（QQ/QQNT/TIM 各 2 个 `Custom.nsh.bak6/bak7-20261017`），
  它们会让根 CI 的"未混入二进制"检查失败，且会被发布流程带出去
  （备份已另存 `build/cleanup-backup-20261019/`，该目录被 `.gitignore` 覆盖）

### 已知限制（不阻塞发布）
- CI 自动发布的是**配方包**（git archive + SHA256SUMS + Release Notes），
  不是产品根里的 59 GB 便携产物——后者在仓库外，CI 拿不到也无法构建。
  二进制分发见 `docs/06-开源与发布.md`，接入方法见 `docs/07` §7
- Gitee Go 的「执行 shell」插件 id 随实例版本变化，首次配置需在流水线编辑器里
  核对一次（`.workflow/release.yml` 内有说明）
- `version.json` 仅 1/39 个包存在，门禁如实报覆盖度，待补齐

## [1.6.0] — 2026-10-18

### 新增
- `docs/07-四平台自动发布.md` + 四份流水线配置（`.github/workflows/release.yml`、
  `.workflow/release.yml`、`.gitcode/workflows/release.yml`、`.cnb.yml`）——
  GitHub / Gitee / GitCode / CNB.COOL 四平台推送版本 Tag 即自动发版，
  统一入口为 `_shared/tools/release.py`（`prepare` 门禁打包 / `upload` 上传）
- `docs/reports/开源前审计与清理报告-20261018.md` —— 开源文件审计、逐包启动/存储/更新
  静态检查、清理清单与回滚命令的合并交付报告

### 修复
- **★ `_pkg.py` 推导不出真实包名时假红**：`pkg_name()` 的回退分支直接取当前目录名，
  于是在仓库根跑 `test_structure.py` 会推出 `PKG=<仓库目录名>`，报一串
  「缺 appinfo.ini」的假错。改为校验包目录存在性，不存在则退出并列出全部可用包名
- **★ `audit_before_push.py` 覆盖面虚报**：只扫 `git add -A --dry-run` 的**未跟踪**
  文件，改动已跟踪文件往里塞本机路径门禁看不见。改为「已跟踪 ∪ 待新增」并集，
  分别计数上报（实测 1710 + 9 = 1719）
- **★ `audit_before_push.py` 假阳性**：`SECRET_CFG` 会命中扫描器自身的
  `SECRET = re.compile(...)` 字面量。把 `audit_pre_release.py` /
  `quarantine_junk.py` / `release.py` 加入自排除集
- `release.py` 版本一致性检查不再瞒报覆盖度：`version.json` 由更新引擎运行期写入，
  实际只有 1/39 个包存在；旧实现 glob 到几个就报「0 不一致」。现按包全集逐包核对并
  明确输出 `覆盖度: N/39`

### 已知限制（不阻塞发布）
- CI 自动发布的是**配方包**（git archive + SHA256SUMS + Release Notes），
  不是 59 GB 的 dist/ 便携产物——后者不入库，CI 在新克隆上拿不到也无法构建。
  二进制分发见 `docs/06-开源与发布.md`，接入方法见 `docs/07` §7
- Gitee Go 的「执行 shell」插件 id 随实例版本变化，首次配置需在流水线编辑器里
  核对一次（`.workflow/release.yml` 内有说明）
- `version.json` 仅 1/39 个包存在，门禁如实报覆盖度，待补齐

## [1.5.0] — 2026-10-18

### 新增
- `docs/06-开源与发布.md` —— GitHub / Gitee 双远端推送步骤、二进制分发三选项、
  体积配额实测、推送前自检清单
- `_shared/tools/verify_roundtrip.py` —— 比对克隆前后每个文件的编码/BOM 是否被改写
  （实测 1707 文件零漂移，UTF-16LE 保护生效）

### 修复
- **★ CI 在新克隆里「假红」**：`audit_repo.py` 默认同审 dist/portableapps 两棵树，
  而 `.gitignore` 排除了 dist 下的二进制，克隆里 39 个包全员报「缺 appinfo.ini」→ 0/39。
  改为按包自适应：portableapps 恒审，dist 仅在本机已装配时才审；
  跳过时打印提示而非静默；0 个包被审计时判失败
- **★ CI 病态扫描「假绿」（源仓库里同样是假绿）**：`check_custom_nsh.py` 的过滤条件
  仍是 `ExecToStack + Command`，但 2026-10-17 起全仓已改为 FileWrite 生成 .ps1
  + `-File` 传参，该条件命中 **0 行**，门禁实际上一直在扫空集且恒 exit 0。
  重建为句柄感知 + 目标后缀分类的扫描面；病态逻辑收敛到 `scan_file()` 单一实现，
  `audit_repo.py` 改为复用；扫到 0 个文件 / 0 个相关行时判失败
- 修复 3 份活跃文档里已失效的脚本路径（`<旧工作区>/scripts\*.py` → `_shared/tools\*.py`），
  并移除已被精简掉的 `batch_rebuild.py` 引用

### 文档
- `docs/README.md`、根 `README.md` 文档地图加入 06
- `docs/03-构建与发布.md` 的「首次开源前收尾」按已完成状态更新
- `docs/README.md` 的「脚本仓库」一节改为反映工具链已入仓的事实

### 已知遗留
- WeMeetPortable 两棵树的 `Custom.nsh` 差 18 字节（dist 略旧），重建后可消除
- 本地 git 身份仍是占位符，推送前须 `--amend --reset-author`（见 06 §2）

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
