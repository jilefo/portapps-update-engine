# 安全策略

## 本仓库的范围

**本仓库只包含便携化「配方」**：目录结构、`appinfo.ini`、Launcher 配置、
`Custom.nsh` 脚本、工具链与文档。**不包含也不分发任何第三方软件的二进制
文件**（`.gitignore` 已排除 `App/` 下的程序文件、`Data/`、`*.paf.exe`）。

因此本仓库的安全问题主要限于：

- 脚本/配置导致的数据写入位置错误（本应写入 `Data/`，实际写到宿主机器）
- `Custom.nsh` 中的命令注入面（PowerShell 内联命令拼接）
- 工具脚本的路径处理缺陷

**第三方软件自身的安全漏洞不属于本仓库范围**，请直接向对应厂商报告。

## 报告方式

请通过 GitHub Issue 提交，并在标题注明 `[SECURITY]`。若问题不宜公开，
请在 Issue 中只描述现象、暂缓贴出利用细节，维护者会转为私密讨论。

请在报告中包含：

1. 影响的包名与具体文件路径
2. 复现步骤（含所用的启动器与参数）
3. 预期行为 vs 实际行为
4. 你的系统版本与 PortableApps.com Launcher 版本

## 已知的安全设计约束

- 便携化的核心手法是把 `APPDATA` / `LOCALAPPDATA` 重定向到
  `%PAL:DataDir%`。若某包被改为重定向 `USERPROFILE`，
  Electron 类应用有崩溃风险——这是稳定性问题，不是漏洞，
  但会列为审计风险项（见 `_shared/tools/audit_production.py`）。
- 退出时 PAL 会还原注册表并把移动出去的目录搬回 `Data/`。
  强制杀进程可能留下 junction 残留，工具链已包含清理逻辑。
