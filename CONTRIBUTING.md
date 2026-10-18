# 贡献指南

欢迎提交新的便携包或修复既有问题。为了让你少走弯路，请先读
[`docs/04-避坑手册.md`](docs/04-避坑手册.md)——里面每一条都对应一次真实返工。

## 一、提交新包

### 必须的脚手架

```
<Pkg>Portable/
├── LICENSE                     MIT（与仓库保持一致）
├── README.md                   用法 + 目录结构 + 许可证声明
├── CHANGELOG.md
├── CONTRIBUTING.md  CODE_OF_CONDUCT.md  SECURITY.md
├── THIRD_PARTY_NOTICES.md      ★ 声明第三方软件权利归属
├── .gitignore  .editorconfig  .gitattributes
├── .github/                    ISSUE_TEMPLATE / PR_TEMPLATE / workflows
├── docs/                       BUILD.md  PORTABLE.md  RELEASE.md
├── portableapps/               构建输入
└── dist/                       产物（已 gitignore 中的 App 二进制）
```

**不要**在包目录下放这些（曾经放过，已全部清理）：

- `scripts/` `tests/` —— 构建与测试脚本统一在 `_shared/scripts/`
  （曾经每个包复制一份，39 份里 4 个 hash 全同、3 个只差包名两行）
- `_制作素材/` `evidence/` —— 制作期取证快照（卸载程序、监控日志，
  含第三方二进制与本机路径）
- `dist/<Pkg>/Backups/` —— 旧版本程序备份（曾有一例 993MB）

### 必须通过的检查

```bash
python _shared/tools/audit_repo.py          # 结构自检，39/39（CI 也跑这个）
python _shared/scripts/test_structure.py <Pkg>   # 单包 PAL 结构校验
python _shared/tools/audit_production.py    # 生产级四维度审计（本机）
python _shared/tools/smoke_real.py <Pkg> 25 # 单包真启动冒烟（需 psutil）
python _shared/tools/smoke_3rounds.py       # 全库 3 轮
```

构建用 `_shared/scripts/build-portable.py`（包名由参数或当前目录推导）。

### 硬性约定

1. **先监控分析，再写配置**。反过来必然返工。
2. `ProgramExecutable` 与 `ExtractIcon` 必须 `ls` 出真实路径，**不要按包名猜**。
3. **不要改 ini 的编码**。含中文路径的 launcher ini 必须是 UTF-16LE；
   `Custom.nsh` 必须是 UTF-8 **无 BOM**。两者要求相反。
4. `Custom.nsh` 钩子宏名必须是 `Custom.nsh_<阶段>`，否则静默失效。
5. `[Environment]` 至少覆盖 `APPDATA` / `LOCALAPPDATA` / `TEMP` / `TMP`。
6. 改 `portableapps/` 后**必须重编并同步 dist**，否则改动不生效。
7. 每个 exe 都要有同名 `Launcher/<BaseName>.ini`。
8. **包目录只放包自己的东西**。构建/测试脚本用 `_shared/scripts/` 的通用版，
   制作期素材做完即清，别留在包里（详见避坑手册 §2.4 §2.5）。

## 二、修复既有问题

- 改 `portableapps/` 源树 → 重编 → 同步 `dist/`；
- 临时热修可以动 `dist/`，但事后要回写源树；
- 提交时说明**复现步骤**与**验证结果**（最好附上冒烟输出行）。

## 三、报告问题

请在对应包的 `.github/ISSUE_TEMPLATE/bug_report.yml` 中填写，并附上：

- 包名与版本（`appinfo.ini` 的 `PackageVersion`）
- 启动方式（双击 / 命令行）
- 现象（弹框文本、是否有进程、Data 是否新增文件）
- 冒烟脚本输出（如有）

## 四、许可证

- 你的贡献（配置、脚本、文档）以 MIT 授权，见 [LICENSE](LICENSE)。
- **不要提交任何第三方软件的二进制文件**。`.gitignore` 已排除
  `App/` 下内容；提交前请确认 `git status` 中没有大体积二进制。
- 若你为新包引入了第三方依赖，请同步更新 `THIRD_PARTY_NOTICES.md`。
