# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\settings\QQ\` —— QQNT 主用户数据（Chromium 式 Partitions/Local Storage/Network/Cache/log，`%APPDATA%\QQ` Junction）
- `Data\settings\Tencent\QQNT\`、`settings\Tencent\QQ\` —— 组件配置（Junction）
- `Data\documents\Tencent Files\nt_qq\` —— 聊天文件/接收文件（`Documents\Tencent Files` 整目录 Junction；与 QQ/TIM 互斥）
- `Data\settings\ProgramData\Tencent\qimei\` —— 设备指纹（Junction）
- `Data\settings\ProgramData\xfolder\` —— checkpoint.dat（Junction）
- `Data\settings\qqnt.reg` 等 —— HKCU Tencent 三键

## 注册表

启动器不写入持久注册表项。`HKCU\Software\Tencent\{QQNT,QQProtect,QQ}` 走 RegistryKeys 备份恢复；安装器写入的 Run 值 `QQNT`（/background 自启）由 NP_RunCleanup 守卫：仅当指向本包路径才删除。与 QQPortable/TIMPortable 互斥（共享 `Documents\Tencent Files` junction），不可同时运行。

## 备份与迁移

整个 `QQNTPortable/` 目录可直接复制到其他机器或盘符；备份只需复制 `Data/` 目录。

## 升级

使用项目更新引擎（`scripts/update_engine.py`）升级：`Data/` 目录完全隔离，
更新过程不触碰用户数据；支持回滚（保留最近 3 个版本）。

## 多用户

设计为单用户便携包；多用户共用请各自复制一份完整目录。

## 路径兼容性

支持含空格路径与不同盘符；启动器在运行期动态建立目录联接（Junction），
不硬编码任何绝对路径。

## 卸载与恢复初始状态

删除整个目录即完成卸载，宿主系统零残留。删除 `Data/` 目录即恢复初始状态。
