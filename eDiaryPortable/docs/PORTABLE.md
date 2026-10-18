# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\settings\Config.ini` —— 主配置（写 exe 旁，FilesMove 收纳；首启由 `App\DefaultData` 种子净化复制）
- `Data\diary\` —— 日记本数据（`.edf`，DirectoriesMove 到 `App\eDiary\Data`；含从平铺版迁移的用户日记）
- `Data\settings\ediary.reg` —— 注册表键 `HKCU\Software\DayDream Software\eDiary`（含 AccessLog 最近文件，PAL RegistryKeys 启动导入/退出回存，宿主原键自动备份恢复）

## 注册表

启动器不写入持久注册表项。注册表 `HKCU\Software\DayDream Software\eDiary` 随 `Data\settings\ediary.reg` 迁移；宿主同键启动前备份、退出后恢复。

## 备份与迁移

整个 `eDiaryPortable/` 目录可直接复制到其他机器或盘符；备份只需复制 `Data/` 目录。

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
