# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\settings\Tencent\WXWork\` —— 主配置/账号（`%APPDATA%\Tencent\WXWork` Junction）
- `Data\settings\Tencent\WeMail\` —— 企业邮箱组件数据（Junction）
- `Data\documents\WXWork\` —— 聊天文件/接收文件（`Documents\WXWork` Junction）
- `Data\settings\ProgramData\Tencent\WXWork\` —— 共享配置（`ProgramData\Tencent\WXWork` Junction）
- `Data\settings\wxwork.reg` —— `HKCU\Software\Tencent\WXWork`

## 注册表

启动器不写入持久注册表项。`HKCU\Software\Tencent\WXWork` 走 RegistryKeys 备份恢复；WXWorkUpgrader 更新服务组件已剔除，便携环境不会安装任何服务。

## 备份与迁移

整个 `WXWorkPortable/` 目录可直接复制到其他机器或盘符；备份只需复制 `Data/` 目录。

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
