# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\settings\Tencent\TIM\` —— 主用户数据（`%APPDATA%\Tencent\TIM` Junction）
- `Data\settings\Tencent\{QQ,TXSSO,Logs,Tencentdl}\` —— 组件数据
- `Data\documents\Tencent Files\` —— 聊天记录/接收文件（与 QQ/QQNT 互斥）
- `Data\settings\ProgramData\Tencent\qimei\` —— 设备指纹
- `Data\settings\*.reg` —— HKCU Tencent 六键

## 注册表

启动器不写入持久注册表项。HKCU Tencent 六键（TIM/QQ2009/QQ/bugReport/Report/TodayDo）走 RegistryKeys 备份恢复；与 QQPortable/QQNTPortable 互斥（共享 `Documents\Tencent Files` junction），不可同时运行。

## 备份与迁移

整个 `TIMPortable/` 目录可直接复制到其他机器或盘符；备份只需复制 `Data/` 目录。

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
