# GreenSoftMake PortableApps

> 39 款 Windows 软件的 PortableApps.com Format 便携化集合 —— 零安装、数据随身、可移动、可开源复现。

本仓库存放的是**便携化配方**（PAL 启动器配置、NSIS 源码、构建与审计脚本、文档），
不存放任何第三方应用程序二进制。按 `docs/01-快速开始.md` 放入官方安装包后即可本地构建。

---

## 一、它解决什么问题

| 痛点 | 本仓库做法 |
|---|---|
| 软件装完就在 `AppData` / 注册表 / 各盘留一堆垃圾 | 全部重定向进包内 `Data\`，整包拷走即可 |
| 重装系统后配置全丢 | 配置随包走，换机即用 |
| 便携版做了但数据还是写宿主 | 每条重定向都有动态落盘测试兜底（见 `docs/05-验收与排查.md`） |
| 多版本共存、U 盘随身 | 每包独立 `AppID`，互不干扰 |

---

## 二、软件清单（39 包 / 43 个启动单元）

**开发编码（18）**：AiPyPro、CherryStudio、CodeArts、CodeArtsAgent、CodeBuddyCN、Comate、Cursor、JoyCode、KukuAI、LobsterAI、MiniMaxCode、QoderCN、QoderCNIDE、TraeCN、WinClaw、WorkBuddy、SublimeText、OfficeAce

**办公文档（6）**：WPSOffice（5 个分体入口：主/文字/表格/演示/PDF）、Typora、FoxitPDF、Joplin、SoloMD、eDiary

**即时通讯与会议（6）**：QQ、TIM、QQNT、Weixin、WXWork、WeMeet

**工具与网盘（9）**：BaiduNetdisk、QuarkCloudDrive、Zoom、Feishu、FSCapture、ReNamer、WeMeet、ZenBrowser、Miaoshou

> WPSOfficePortable 一个包提供 5 个启动器（主入口 + 文字/表格/演示/PDF），
> 因此启动单元是 43 个而非 39 个。

---

## 三、快速开始

工具链全部在仓库内，无需外部脚本目录；仓库根由脚本位置自动推导，
也可用 `PORTABLEAPPS_ROOT` 环境变量指向别处。

```bash
# 1. 结构自检（纯文本校验，clone 下来就能跑，CI 用的就是它）
python _shared/tools/audit_repo.py

# 2. 静态生产级审计（不启动任何应用，本机已装配时可用）
python _shared/tools/audit_production.py

# 3. 构建某个包的启动器（需 NSIS 3）
python _shared/build_launcher.py CursorPortable

# 4. 单包真启动冒烟（需 pip install psutil）
python _shared/tools/smoke_real.py CursorPortable 25

# 5. 全库启动冒烟（43 单元 × N 轮）
python _shared/tools/smoke_3rounds.py

# 6. 构建/结构校验（通用脚本，包名由参数或当前目录推导）
python _shared/scripts/build-portable.py CursorPortable
python _shared/scripts/test_structure.py CursorPortable

# 7. 更新检测：每包自带 dist/<Pkg>/update.py（自包含，可随包拷走）
cd CursorPortable/dist/CursorPortable
python update.py --check                  # 只检测，只读
python update.py --update --execute       # 真更新（自动备份+回滚）
python update.py --ingest <包> --execute  # 人工下载后接管全流程

# 批量检测全部 39 个包
python _shared/update/runner.py --check --all --report
```

详细步骤见 [`docs/01-快速开始.md`](docs/01-快速开始.md)。

---

## 四、文档地图

| 文档 | 内容 |
|---|---|
| [`docs/README.md`](docs/README.md) | 文档总索引 |
| [`docs/01-快速开始.md`](docs/01-快速开始.md) | 从零构建第一个便携包 |
| [`docs/02-架构与目录规范.md`](docs/02-架构与目录规范.md) | 双树结构、PAL 机制、配置字段含义 |
| [`docs/03-构建与发布.md`](docs/03-构建与发布.md) | 构建流程、版本号、发布与开源合规 |
| [`docs/04-避坑手册.md`](docs/04-避坑手册.md) | **踩坑清单（务必先读）** |
| [`docs/05-验收与排查.md`](docs/05-验收与排查.md) | 冒烟/审计工具用法与判定标准 |
| [`docs/06-开源与发布.md`](docs/06-开源与发布.md) | 推 GitHub / Gitee、二进制分发、体积配额实测 |
| [`_shared/tools/README.md`](_shared/tools/README.md) | 生产级工具链用法（审计 / 冒烟 / 修复 / 验证） |
| [`_shared/scripts/README.md`](_shared/scripts/README.md) | 通用构建与测试脚本（39 包共用一份） |
| [`docs/reports/`](docs/reports/) | 历次验收与排查报告 |
| [`docs/archive/`](docs/archive/) | 历史文档与方法论沉淀 |

---

## 五、当前质量状态（2026-10-18）

| 检查项 | 结果 |
|---|---|
| 全库 3 轮启动排查（43 单元 × 3 轮） | **43/43 三轮全 PASS**（Miaoshou 曾因 ini 编码被改坏，已还原复验 PASS） |
| 数据落地重定向（APPDATA / LOCALAPPDATA） | 39/39 全部指向 `%PAL:DataDir%` |
| CI 结构自检（元数据 + appinfo + Launcher + Custom.nsh + 编码铁律，双树） | **39/39 通过** |
| Custom.nsh 病态扫描 | 38 个包全部「无病态」；另修掉 2 包 4 个文件的 UTF-8 BOM |
| 生产级静态审计 | 已修复 3 个 ExtractIcon 路径错误、23 个包 dist appinfo 缺段 |
| 开源完备性（LICENSE/README/.github/docs） | 包级 39/39 齐备；根级脚手架本轮补齐（CHANGELOG / CoC / .editorconfig / SECURITY / CI） |
| 更新策略脚本 | **39/39**，每包一个 `dist/<Pkg>/update.py`；在线自动源 7 个，其余诚实标记人工 + `--ingest` 接管；全量检测 0 异常 |
| 更新端到端实测 | SublimeText 4200 → 4215 真实更新成功（剔除上游 Data、禁用自带更新器、结构校验 PASS、真启动冒烟 PASS）；回滚链路实测通过 |

### 已知遗留（非阻断）

- 11 个 Electron 类包重定向 `USERPROFILE`：实测可正常启动与写入，
  但存在崩溃风险，审计列为「已知风险」而非阻断项。
- `MiaoshouPortable.ini` 必须保持 UTF-16LE（含中文路径），**禁止转 UTF-8**。
- 工具链中一次性调试脚本已剔除，仅保留 19 个可复用脚本。

---

## 六、许可证

仓库内的配置、脚本与文档以 **MIT** 发布（见 [LICENSE](LICENSE)）。
第三方软件的二进制不属于本仓库，其权利归原厂商所有，请遵守各自 EULA；
仓库通过 `.gitignore` 将其排除，不做分发。

## 七、贡献

见 [CONTRIBUTING.md](CONTRIBUTING.md)。提交新的便携包前请先读
[`docs/04-避坑手册.md`](docs/04-避坑手册.md)，能省下大量返工。
