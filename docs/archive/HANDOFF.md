> 📦 **迁移说明**：本文由 `<旧工作区>/HANDOFF.md` 迁入本仓库（2026-10-18）。
> 文中路径已按迁移后的新位置更新；脚本类路径现指向本仓库 `<旧工作区>/scripts\`（2026-10-18 已迁入本仓库 _shared/tools/ 并去除绝对路径硬编码）。

# HANDOFF —— 便携软件项目维护任务交接文档

- 更新时间：2026-10-16
- 执行依据：`今日任务书.md`（唯一执行依据），配套《便携软件自动化更新维护方案（整合定稿版）.md》《开源与PortableApps双轨发布标准.md》
- 工作目录：`<旧工作区>\_analysis\`（临时脚本与扫描产物存放处）
- 项目根：`<旧工作区>`

---

## ① 任务目标

按《今日任务书》完成全部便携软件项目的统一维护，最终交付：

1. 图标完整性、垃圾文件、数据持久化、启动可靠性、App 目录洁净度的全量排查与修复（覆盖所有便携项目，不限于任务书点名项目）。
2. WPS 系列专项检查（WPSOfficePortable 与 WPSPDFPortable 分开，不得混淆）。
3. FastStoneCapture 更新源切换为蓝奏云 `https://osssr.lanzoum.com/b01u8ekhg`；FoxitPDF 标记"不更新"并跳过自动化流程。
4. 第五章开源标准文件补齐 —— 用户已选定 **"完整双轨改造"**：把 26 个平铺项目全部改造成 `repo根 + portableapps/ + dist/<Name>/` 双轨结构并补全 20+ 项开源文件。
5. 产出维护报告（存 `reports\维护报告-<日期时间>.md`），含各项目问题清单及处理结果（WPSOfficePortable 单独列出）、App 清理清单、其他问题建议、未处理事项及原因。

---

## ② 已完成（逐条）

1. **t1 图标完整性全量排查**（31 包）
   - 实测修复 3 处 appicon 错配：QuarkCloudDrive、SublimeText、ZenBrowser（根因 exeico 按体积误取占位图标，改用 pefile 解码最大多尺寸重建）。
   - TraeCN / Comate / WPSPDF 复核正确；WPSOffice 归入 t6 确认正常。
   - 产物：`Work\_analysis\audit_report.json`。

2. **t2 垃圾文件残留排查**（任务书 2.3 / 2.5 / 三.2）
   - `audit_report.json` 已刷新（31 包）；`clean_junk_report.json` count=0。
   - 结论：多数疑似"垃圾"实为运行时必需文件（如 zip 资源），须保留，不清理。

3. **t3 TodayCNPortable 数据持久化修复**（任务书 2.4）
   - 根因：`Data` 内存在 `account-credentials.signed-out` tombstone，导致登录态每轮被清。
   - 修复：Custom.nsh 改为优雅关闭流程，并用 `build_launcher.py` 重编译（启动器 mtime 2026-10-16 12:33）。

4. **t4 启动可靠性验证**（任务书 2.6 + 三.5）
   - 10 包实测全部 BOOT_OK：CodeArtsAgent、CodeBuddyCN、Comate、Cursor、JoyCode、LobsterAI、Miaoshou、QoderCNIDE、WinClaw、WorkBuddy。
   - 注意：Miaoshou 启动时弹 `Error` 窗口但主窗口随后出现（判定 BOOT_OK），维护报告需注明该现象。

5. **t6 WPS 系列专项**（任务书 2.7 / 2.8 / 三.6）
   - WPSPDFPortable：dist 下实测 BOOT_OK（窗口 `WPS PDF专业版`）。
   - WPSOfficePortable：实测 BOOT_OK（`WPS文字` 窗口，收尾无残留进程）；数据落 `Data\Roaming`（240MB）；宿主 `%APPDATA%\Kingsoft`、`%LOCALAPPDATA%\Kingsoft` 为宿主真实 WPS 数据（非 junction，未触碰）。
   - WPSPDF office6 共 1031MB（addons 575MB 为大头，其余为 wps.exe 依赖的全套 Office dll）；**按任务书 2.7 保留版本号目录 `12.8.0.23123` 不动**，可清理项归入 t5 清单。

6. **沙箱泄漏疑点复核**
   - `%APPDATA%\LobsterAI`、`%LOCALAPPDATA%\OpenClaw`、`%LOCALAPPDATA%\lobsterai-updater`、`%APPDATA%\winclaw`、`%LOCALAPPDATA%\winclaw-updater` 均为 **junction 指向各自包内 `Data\settings\*`**，重定向正常生效，非泄漏。
   - 唯一未处理项：`%USERPROFILE%\.meituan-catpaw`（Miaoshou，真实目录 1.8GB，含 auth.json 登录 token，mtime 2026-10-15 22:44）—— MiaoshouPortable 的 Custom.nsh 只收纳 `%APPDATA%\catpaw-moon`，未覆盖家目录 `.meituan-catpaw`。须写入维护报告"未处理事项"。

7. **t7 更新源切换与排除**（任务书 2.1 / 2.10）
   - FSCapturePortable 更新源切换为蓝奏云 `https://osssr.lanzoum.com/b01u8ekhg`；`scripts\update_engine.py` 新增 acw_sc__v2 解盾 + `lanzou_folder` 通道；detect 实证 current 11.3.0.0 / latest 11.3。
   - FoxitPDFPortable 已加入 `scripts\gen_update_configs.py` 的 EXCLUDED 集合，方案 §11 标记"不更新"。

8. **t8 开源标准文件扫描**（任务书 五）
   - 脚本：`Work\_analysis\_t8_scan.py`。
   - 结果：双轨 8 包（FSCapture、Feishu、SoloMD、Typora、SublimeText、ReNamer、ZenBrowser、WPSPDF）各 15/15 项齐全；平铺 26 包 0/15（仅 Joplin 4/15）。
   - 由此确认需全量双轨改造，用户选定"完整双轨改造"方案（见 ④ 待办第 1~3 项）。

---

## ③ 进行中

**t9 双轨改造迁移（尚未落笔，无代码卡点，属刚启动状态）**

- 目标：把 26 个平铺项目改造为双轨结构。26 包清单：AiPyPro、BaiduNetdisk、CherryStudio、CodeArts、CodeArtsAgent、CodeBuddyCN、Comate、Cursor、eDiary、FoxitPDF、Joplin、JoyCode、LobsterAI、Miaoshou、MiniMaxCode、OfficeAce、QoderCN、QoderCNIDE、QuarkCloudDrive、TodayCN、TraeCN、WeMeet、WinClaw、WorkBuddy、WPSOffice、Zoom。
- 迁移规则（已定稿，照 `Work\FSCapturePortable` 模板）：
  1. copy `App/AppInfo/**` → `portableapps/App/AppInfo/**`（appinfo.ini、launcher.ini、appicon.ico、appicon_16/32/75/128.png、Launcher/*.ini、Custom.nsh）；在 `portableapps/App/<AppSubdir>/` 放 `DOWNLOAD.txt` 占位，**不复制大二进制**。
  2. 建 repo 级开源文件全套（.editorconfig/.gitattributes/.gitignore/.github/{CODEOWNERS,PULL_REQUEST_TEMPLATE.md,dependabot.yml,ISSUE_TEMPLATE/*,workflows/{ci.yml,portableapps.yml,release.yml}}/LICENSE/README.md/CHANGELOG.md/CONTRIBUTING.md/CODE_OF_CONDUCT.md/SECURITY.md/SUPPORT.md/THIRD_PARTY_NOTICES.md/docs/{PORTABLE,BUILD,RELEASE}.md/scripts/{build-portable.py,build-portable.ps1,package-paf.py}/tests/test_structure.py）。
  3. 用 `os.rename`（同盘瞬时）把 `<Name>.exe` + `App` + `Data` + `Other`（有则连同 `Backups`、`version.json`）移入 `dist/<Name>/`，补 `dist/<Name>/help.html` 与 `Other/{Help,Source}`。
  4. 迁移前后比对 Data 文件数/体积必须相等；同一项目迁移失败要可回退。
- 卡点：无技术卡点；下一步是写 `Work\_analysis\_t9_dualize.py`，**先 CursorPortable 单包试点（迁移后实测 BOOT_OK + Data 无损）再批量**，脚本需支持 dry_run + 每包日志。
- 注意：`scripts\gen_update_configs.py` 近期被外部修改过（首行出现 BOM 异常字符）——后续如需动它，只做定向 Edit，勿整文件重写、勿还原该改动。

---

## ④ 待办清单（按优先级）

1. **P0｜双轨迁移试点**：写 `Work\_analysis\_t9_dualize.py`，先迁移 CursorPortable，实测 BOOT_OK + Data 文件数/体积无损。
2. **P0｜批量迁移**：对其余 25 个平铺项目执行迁移（dry_run 预演 → 实执行），每包独立日志，失败可回退。
3. **P0｜配置回归**：迁移后**只改**各 `Configs\<项目>.yaml` 的 `dir` 字段为 `<Name>\dist\<Name>`；跑 `python scripts\update_engine.py detect --all` 回归无破坏。**禁止整体重跑 gen_update_configs**（会把 current_version 从 appinfo.ini 重置，造成基线漂移）。
4. **P1｜t5 App 目录清理清单**（任务书 2.9 + 三.4）：从 `audit_report.json` 的 junk 字段汇总，重点 WPSOffice / WPSPDF / Feishu / SublimeText / Typora；区分"真可清"vs"运行时须保留"，逐项写保留理由。
5. **P1｜维护报告**（任务书 四）：存 `reports\维护报告-<日期时间>.md`；WPSOfficePortable 单独列出；含问题清单及处理结果、App 清理清单（项目名→可删除项→保留理由）、其他问题建议、未处理事项（必含 `.meituan-catpaw`、Miaoshou 启动弹 Error 窗口现象）。
6. **P2｜临时文件清理**：删除 `Work\_analysis\` 下 `_osssr_page.html`、`_lanzou_challenge.html`、`_wps_lx.py`（及任务收尾后的一次性 `_t*.py` 扫描脚本，保留有复用价值的）。
7. **P2｜人工确认项**：`.meituan-catpaw` 是否为宿主既有数据（1.8GB，含登录 token），确认后决定是否为 MiaoshouPortable 扩展 Junction 收纳。

---

## ⑤ 关键上下文

### 技术栈与硬约束（违反即返工）

- Python 3.10+，Windows 10/11 64 位；**全程 Python（ctypes/psutil），禁止 PowerShell**（用户 2026-10-16 明确要求）；禁止硬编码坐标。
- **Data 目录神圣不可侵犯**：任何函数不写不删其内容，读取只读；current.txt 类写入用"临时文件 + os.replace"原子替换。
- **禁止 `taskkill /IM`** 按映像名全局杀进程（会误杀宿主 IDE 导致会话中断）；必须按可执行路径限定 PID 关闭。
- 证据驱动：公开函数返回结构化 dict（exit_code、sha256、时间戳、证据路径）；logging 而非 print。
- 所有脚本加 BOM 头防中文乱码；全部 pathlib；subprocess 用 `shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=N`。
- 禁模糊表述（"应该可以/基本正常"）；禁止声称"已测试通过"——只生成代码与测试脚本，真实运行由用户执行或由脚本产出证据文件。
- 依赖白名单：标准库 + requests + psutil + packaging + PyYAML（+ 可选 bsdiff4）。

### 目录约定

- 便携包位于 `Work\<项目名>Portable\`；双轨包的便携根在 `Work\<项目名>\dist\<项目名>\`。
- 更新引擎 `scripts\update_engine.py`：`pkg_dir = WORK / cfg["dir"]`（L153），`version.json`/`Backups`/`Staging` 都在 pkg 目录下 → 迁移后必须随包位于 `dist/<Name>/` 内。
- `scripts\gen_update_configs.py` 扫描逻辑：`repo/App/AppInfo/appinfo.ini` 存在 → dir=repo.name；否则扫 `repo/dist/*` → dir=`repo\dist\pkg`。
- 版本状态数据源：`reports\data\update_versions.json`（原子写）；更新配置：`Configs\<项目名>.yaml`。
- 引擎 7z 依赖：`find_7z` 优先独立版 7za（PATH 残血 7z.EXE 缺 7z.dll 解不了 LZMA）。

### 踩坑记录（与本任务直接相关，按「现象→根因→解决」压缩）

- **exeico 按体积误取图标**：对嵌套版本号目录的包（如 WPS）需 icon_exe 显式路径；部分 ico 文件头损坏需 pefile 手工重建。
- **PAL 钩子宏名**必须是 `Custom.nsh_<阶段>` 格式，旧名静默失效；改 Custom.nsh/ini 后**必须用 build_launcher.py 重编译**（源对二进制旧=钩子失效）；PAL_DEBUG=1 仅取证，验证完须普通模式重编译发布。
- **PAL 互斥体**（PortableApps.comLauncher$AppID-$BaseName）：宿主同 AppID 实例会让新实例走 secondary launch 跳过钩子；测试前须全局查同 AppID 冲突、校验包内进程数为 0。
- **强杀顺序**：先清子进程再让 PAL 走 PostPrimary 拆 junction；连杀启动器必致 junction 残留；VS Code 系收尾须轮询等进程归零。
- **Junction 三重验证**目录归属（进程占用/mtime/宿主同产品）；删 junction 只能 `rmdir` 不带 /s；大目录删除用 robocopy /MIR。
- **USERPROFILE 严禁重定向**（Electron 启动塌缩：SHGetKnownFolderPath 展开出不存在路径 → appData 取不到 → 崩）；Electron 双写 APPDATA+USERPROFILE 两处都要查。
- **Typora 安装包伪装 NSIS（Linker 2.25）实为 Inno**（%TEMP%\is-*.tmp 特征）；安装包识别不能只看 Linker 版本号。
- **PAL [FilesMove] 值必须是目录**（文件名由键追加），带文件名会拼出非法路径且创建同名空目录挡住写文件。
- **设置文件名禁止按品牌臆测**：ReNamer 真实是 Settings.ini、FSCapture 是 fsc.db；首轮浸泡 Data 无预期文件时必须取证。
- **泄漏检测噪声白名单**：%LOCALAPPDATA%\Temp、宿主 IDE 数据目录（~\.workbuddy、~\.trae-cn）、~\Downloads、宿主微信/Zoom 目录、pnpm-cache；SQLite -wal/-shm 正常 checkpoint 需排除；Chromium 会话/指标文件每轮重建属正常轮换。
- **gen_update_configs.py 的 VERIFIED_SOURCES/VERIFIED_PACKAGE 字典**末尾有注释行，Edit 锚点必须含完整结尾块，否则撞字典中间造成语法损坏。
- **TraeCN 严禁对 ~\.trae-cn/~\.trae 建 Junction**（宿主 TraeCode CN IDE 同产品数据，2026-10-15 曾误删靠 robocopy 副本救回）。
- **蓝奏云**：分享页 HTML 拿不到文件列表，token 在内联 JS 且一次性，每次 detect 须重新抓页面 POST /filemoreajax.php；acw_sc__v2 需解盾（已实装）。
- **WM_QUIT 退出**：托盘程序无顶层窗口，须 PostThreadMessage(WM_QUIT) 投包内全部线程。

### 双轨模板参考

`Work\FSCapturePortable` 为标准双轨样板（15/15 项齐全），结构：

```
<Repo>/
  .editorconfig .gitattributes .gitignore .github/{...workflows{ci,portableapps,release}.yml}
  LICENSE README.md CHANGELOG.md CONTRIBUTING.md CODE_OF_CONDUCT.md
  SECURITY.md SUPPORT.md THIRD_PARTY_NOTICES.md
  docs/{PORTABLE,BUILD,RELEASE}.md
  scripts/{build-portable.py,build-portable.ps1,package-paf.py}
  tests/test_structure.py
  portableapps/{App/AppInfo/{appinfo.ini,launcher.ini,appicon.ico,appicon_*.png,Launcher/<Name>Portable.ini,Custom.nsh},help.html,DefaultData/,Other/{Help/Images,Source}}
  dist/<Name>/{<Name>.exe,App/,Data/,Other/,help.html}
```

### 关键证据文件位置

- `Work\_analysis\audit_report.json` —— 31 包图标/垃圾/残留审计快照
- `Work\_analysis\clean_junk_report.json` —— 垃圾清理结果（count=0）
- `Work\_analysis\_t8_scan.py` —— 开源文件覆盖扫描脚本
- `Work\_analysis\probe_sources.json` —— 版本源探测证据（前序任务）
- `Work\_analysis\data-persist-new5-20261016-083758.json` —— 批次5 持久化复测留档（前序任务）
- 后台任务输出（t4 启动验证 10 包 BOOT_OK 日志）已确认，无遗留运行中任务

---

# 历史交接记录

（下方为旧版本内容，随时间往下沉；本文件首次创建，暂无历史版本。）
