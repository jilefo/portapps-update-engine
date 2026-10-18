# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\documents\xwechat_files\` —— 聊天主数据（消息数据库/图片/文件，`Documents\xwechat_files` Junction 收纳）
- `Data\settings\Tencent\xwechat\` —— 配置/账号状态（`%APPDATA%\Tencent\xwechat` Junction）
- `Data\settings\weixin.reg` —— `HKCU\Software\Tencent\Weixin`（PAL RegistryKeys 启动导入/退出回存，宿主原键自动备份恢复）

## 注册表

启动器不写入持久注册表项。`HKCU\Software\Tencent\Weixin` 走 RegistryKeys 备份恢复；Run 值 Weixin 若被应用写入且指向本包，退出时自动删除（NP_RunCleanup 守卫）。

## 备份与迁移

整个 `WeixinPortable/` 目录可直接复制到其他机器或盘符；备份只需复制 `Data/` 目录。

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
