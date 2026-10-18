> 📦 **迁移说明**：本文由 `<旧工作区>/README.md` 迁入本仓库（2026-10-18）。
> 文中路径已按迁移后的新位置更新；脚本类路径现指向本仓库 `<旧工作区>/scripts\`（2026-10-18 已迁入本仓库 _shared/tools/ 并去除绝对路径硬编码）。

# GreenSoftMake — 绿色软件与便携软件工业化制作项目

把日常高频 Windows 软件改造为 **可迁移、零残留** 的绿色版 / 便携版：**删除目录即完全脱离系统**，不向系统目录复制文件，不在宿主环境留下持久数据。

本项目不是脚本集合，而是一套 **方法论完备、工具链闭环、双路线并行** 的工业化生产体系：从安装行为监控、日志分析、配置生成、启动器编译，到数据重定向验证与便携性测试，全流程标准化、可复现、可审计。

---

## 目录

- [核心理念：双技术路线](#核心理念双技术路线)
- [项目特性](#项目特性)
- [目录结构](#目录结构)
- [成品清单](#成品清单)
- [快速上手](#快速上手)
- [技术原理简介](#技术原理简介)
- [文档导航](#文档导航)
- [系统要求](#系统要求)
- [许可与免责](#许可与免责)

---

## 核心理念：双技术路线

不同软件的系统集成程度不同，本项目按写入行为将其分流到两条路线：

| 维度 | 绿色化（Green） | 便携化（Portable） |
|------|----------------|--------------------|
| 核心机制 | 注册表 CLSID / TIP 映射到绿色目录 | PAL 启动器 + 环境变量重定向数据目录 |
| 系统侵入 | 仅写注册表，不复制文件到系统目录 | 不写系统目录，数据全部落在 `Data\` |
| 适用对象 | 输入法（TSF 框架）、WPS Office | Electron / VS Code 系 AI 客户端、Zoom 等 |
| 卸载方式 | 运行 `_卸载.bat` 清理注册表 | 直接删除整个目录 |
| 典型模板 | WeType 输入法模板 | PortableApps.com Launcher（PAL） |
| 分流红线 | 需要服务 / 驱动 / Shell 扩展 / 实时监控的软件：**不适合便携化，直接标记并说明原因** | 同左 |

**选路原则**：输入法和 WPS 制作绿色版；AI 类软件优先便携版，无法便携时降级为"PAL + 临时清理"的绿色版；官方已有便携版的直接整理收录，不重复造轮子；社区已有成熟方案的优先复用。

## 项目特性

- **九步工业化工作流**：读日志 → 分析写入 → 判定等级 → 选模板 → 生成 appinfo.ini → 生成 launcher.ini → 生成 Custom.nsh → 人工操作指南 → 制作报告，每个软件强制执行，所有注册表键与文件路径必须可溯源到监控日志。
- **自动化工具链**：`_analysis` 目录下 70+ 个 Python 脚本覆盖启动器构建、Electron 启动包装、图标提取、数据重定向验证、便携性测试，质量不靠人肉保证。
- **企业级部署能力**：静默参数 `/silent`、自动 UAC 提权、文件完整性校验、注册表备份恢复、语义化退出码。
- **可审计可回滚**：日志先行、dry-run 清理清单、绿化/卸载前自动备份注册表到 `backup\`。
- **质量红线**：不猜测注册表键、不把卸载注册表项导入用户系统、不强行便携化系统级软件、分批处理逐批确认。

## 目录结构

```
GreenSoftMake\
├── README.md                      # 本文件：项目门面
├── docs\                          # 开源文档
│   ├── 制作方法.md                #   九步工作流 + 各软件制作要点 + 更新维护
│   ├── 踩坑记录.md                #   所有已知错误、根因分析、解决方案
│   └── 工具说明.md                #   exeico / PAL / 7z / Sandboxie / 工具链
│
├── Template Center\               # 模板库（复用优先）
│   ├── ZoomPortable\              #   PAL 标准结构参考
│   ├── LibreWolf-Portable\        #   Profiles 目录管理参考
│   ├── VscodiumPortable\          #   VS Code 系 user-data-dir 重定向参考
│   ├── WeType\                    #   输入法绿色化参考
│   └── PortableApps.comLauncher\  #   PAL 编译工具（仅供人工编译）
│
├── Work\                          # 便携版成品输出（21 个 *Portable 包）
│   ├── ZoomPortable\  WeMeetPortable\  CursorPortable\  ...
│   ├── _analysis\                 #   构建 / 验证 / 测试 Python 工具链
│   └── _stage\                    #   构建暂存目录
│
├── Logs\                          # 17 个软件的安装监控日志（分析事实来源）
│
├── Iime\  WindInput\  wps\        # 绿色化原料与脚本（输入法 / WPS）
├── webex\  Cursor\  LobsterAI\ …  # 各软件分析原料（.reg 导出 + 文件清单）
│
├── todolist.md                    # 近期任务清单
├── cleanup-manifest.json          # 批量清理 / 归档清单（dry-run）
└── portable-green-software-full-prompt.md.md  # 核心方法论主提示词
```

## 成品清单

### 便携版（`Work\` 目录，21 个）

| 批次 | 成品包 |
|------|--------|
| 一 | ZoomPortable、WeMeetPortable |
| 二 | WetypePortable、WindInputPortable、IimePortable、WPSPortable |
| 三 | CursorPortable、TraeCNPortable、QoderCNPortable、CodeBuddyCNPortable |
| 四 | CodeArtsPortable、CodeArtsAgentPortable、ComatePortable、JoyCodePortable |
| 五 | AiPyProPortable、OfficeAcePortable、TodayCNPortable、MiaoshouPortable、WorkBuddyPortable、MiniMaxCodePortable、FoxitPDFPortable、QuarkCloudDrivePortable |

> LibreWolf 官方已有便携版，按项目规则**不重复制作**，`Template Center\LibreWolf-Portable` 仅作模板参考。

### 绿色版（根目录）

| 软件 | 内容 | 脚本版本 |
|------|------|----------|
| 冰凌输入法（Iime） | `Iime32/64_13.9.1.260819.ime` + Iimsrv/Iimpe/Iimkit + 词库 | v2.0 |
| 清风输入法（WindInput） | `wind_tsf.dll`（64/32 位）+ wind_input/wind_setting/wind_portable + 词库 | v2.0 |
| WPS | 绿化原料（install.ini / installfilelist.dat / diffbase 差分备份） | 制作中 |

## 快速上手

### 便携版：开箱即用

便携版无需安装，解压后双击启动器即可：

```bat
:: 例如启动 Zoom 便携版
Work\ZoomPortable\ZoomPortable.exe
```

用户数据全部写入便携包内的 `Data\` 目录；删除整个便携包目录即完成卸载，宿主系统零残留。

**Data 目录自动生成**：首次启动时 `Data\` 目录结构由启动器自动创建（无需预置），软件随即在空配置下完成初始化——与新装软件首次运行行为一致。以 WeMeetPortable 为例，用户数据目录通过**目录联接（Junction）**机制落盘：启动时启动器在宿主 `%APPDATA%\Tencent\WeMeet` 建立指向 `Data\settings\Tencent\WeMeet` 的联接，退出时自动拆除——数据物理上始终只存在于 `Data`，宿主零残留，且对 `SHGetFolderPath` / KnownFolder API 等顽固写入路径完全透明。登录态、会议设置、缓存等全部保存于 `Data` 内，随包迁移。

**软件更新**：便携结构将程序（`App\`）与数据（`Data\`）完全分离，更新只动程序、不碰数据：

- **自带更新器默认拦截**（十条更新原则第 9 条），仅当实测验证"只写 App 目录、零宿主残留、不破坏重定向、无需提权"后才例外放行（详见 [docs\archive\更新维护方案.md](docs\archive\更新维护方案.md)；腾讯会议为当前唯一候选，待发版实测）；
- **或用随包更新工具**：双击包根目录 `_更新.bat`，按提示从官网下载新版安装包，脚本自动完成解压、替换 `App\` 程序文件、更新版本号，`Data\` 全程不受影响（需要系统安装 7-Zip）。

### 绿色版（输入法）：一键绿化 / 卸载

```bat
:: 以管理员身份（脚本会自动请求 UAC 提权）
Iime\_绿化.bat
WindInput\_绿化.bat

:: 卸载
Iime\_卸载.bat
WindInput\_卸载.bat
```

**常用参数**

| 参数 | 说明 |
|------|------|
| `/silent` | 静默模式，全程不暂停、不弹提示（适合企业无人值守分发） |
| `/noshortcut` | 不创建桌面快捷方式 |

**退出码**

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 参数错误 |
| 2 | 提权被取消 |
| 3 | 目录内文件缺失（不完整，拒绝半成品注册） |
| 4 | 注册表写入失败 |
| 5 | 自检失败（注册不完整 / 有残留） |

### 部署注意事项

- **先卸载原版**：使用官方卸载程序清理原版后再绿化，切勿与原版并行（CLSID 冲突）。
- **部署后请勿移动目录**：注册表路径指向绿色目录，移动后即失效。
- **多用户**：HKCU 项仅对当前用户生效，其他用户需各自运行一次绿化脚本。
- **备份恢复**：如需回滚，双击 `backup\` 内对应时间戳的 `.reg` 文件即可。

## 技术原理简介

**绿色化（输入法为例）**：参考 WeType 模板手工重建 TSF（Text Services Framework）注册结构 —— COM 组件注册在 `HKLM\SOFTWARE\Classes\CLSID` 并指向绿色目录（`%~dp0`），CTF TIP 注册在 `HKLM\SOFTWARE\Microsoft\CTF\TIP`，用户级切换列表注册在 `HKCU\Software\Microsoft\CTF\SortOrder`（保证 Win+Space 可切换），快捷键注册在 `HKCU\Software\Microsoft\CTF\DirectSwitchHotkeys`。

**便携化（PAL 结构）**：标准目录为 `App\`（程序）+ `App\AppInfo\`（配置）+ `Data\`（用户数据）。启动器通过 `[Environment]` 把 `APPDATA / LOCALAPPDATA / USERPROFILE` 重定向到 `%PAL:DataDir%`，通过 `[RegistryKeys]` + `[RegistryCleanupIfEmpty]` 在启动时导入、退出时清理注册表，通过 `Custom.nsh` 处理开机自启、计划任务、后台进程强杀。

完整技术细节见 [docs\archive\制作方法.md](docs\archive\制作方法.md)。

## 文档导航

| 文档 | 内容 |
|------|------|
| [docs\archive\制作方法.md](docs\archive\制作方法.md) | 九步工作流详解、各软件制作要点、绿色版降级方案、更新维护十条原则、升级器开发指引 |
| [docs/04-避坑手册.md](docs/04-避坑手册.md) | 所有已知错误的根因分析与解决方案（清风切换列表、Electron 脏环境变量、Zoom 协议唤醒等） |
| [docs\archive\工具说明.md](docs\archive\工具说明.md) | exeico、PAL/makensis、7-Zip、Total Uninstall、Sandboxie Plus、`_analysis` 工具链用法 |
| [docs\archive\更新维护方案.md](docs\archive\更新维护方案.md) | 更新路线对比与推荐：离线包解包为主干、沙盒提取兜底、自带更新器例外放行 |
| [portable-green-software-full-prompt.md.md](portable-green-software-full-prompt.md.md) | 核心方法论主提示词原文（制作 / 更新维护 / 升级器三部分） |
| [todolist.md](todolist.md) | 近期任务清单与执行规格 |

## 系统要求

- **操作系统**：Windows 10 22H2 (19045) 已验证；Windows 11 理论兼容（TSF 机制一致）。
- **权限**：绿化脚本需管理员权限（双击自动请求 UAC 提权）；便携版无需管理员权限。
- **依赖**：便携版启动器使用 [PortableApps.com Launcher](https://portableapps.com/apps/development/portableapps.com_launcher) 人工编译；Electron 系软件依赖系统自带 WebView2 运行时（Win10/11 通常已内置）。

## 许可与免责

本项目仅提供 **注册表绿化方案、便携化配置与部署编排**，不含任何商业软件的本体程序文件与授权。请在获取相应软件的正版授权后使用本项目成果；部分商业软件（如 Foxit PDF Editor、Zoom、腾讯会议等）的再分发可能受其自身许可协议限制，分发前请自行确认合规性。

绿化与便携化造成的任何系统或软件异常，本项目作者不承担责任。仓库开源协议按实际配置补充（建议 MIT，配置与脚本部分；商业软件素材不入库）。
