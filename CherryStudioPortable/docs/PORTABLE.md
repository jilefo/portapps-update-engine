# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\\settings\\CherryStudio\\` —— 配置、会话、缓存、登录态

实现方式：启动器在运行期重定向 `ent.APPDATA`、`ent.LOCALAPPDATA`、`ent.TEMP`、`ent.TMP` 到 `Data\settings\`，
并在需要时建立目录联接（Junction），退出时自动拆除。

## 注册表

启动器不写入**持久**注册表项。运行期可能建立目录联接，退出时自动拆除，
宿主系统零残留。

## 备份与迁移

- 备份：仅需复制 `Data/` 目录。
- 迁移：整个 `CherryStudioPortable/` 目录可直接复制到其他机器或盘符。

## 升级

升级由构建产物替换完成：`Data/` 目录完全隔离，更新过程不触碰用户数据。
自动化更新（检测 → 下载 → 校验 → 冒烟 → 发布）由公共更新引擎驱动，
配置见 `_shared/configs/CherryStudioPortable.yaml`。

## 多用户

设计为单用户便携包；多用户共用请各自复制一份完整目录。

## 路径兼容性

- 支持含空格路径与不同盘符（含中文路径）。
- 启动器不硬编码任何绝对路径，全部使用 `%PAL:AppDir%` / `%PAL:DataDir%` 相对锚点。

## 卸载与恢复初始状态

- 完整卸载：删除整个 `CherryStudioPortable/` 目录，宿主系统零残留。
- 恢复初始状态：删除 `Data/` 目录即可。
