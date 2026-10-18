# 便携模式说明（PORTABLE.md）

## 数据写入位置

所有用户数据写入便携包根目录的 `Data/` 下：

- `Data\settings\baidu\` —— 外壳扩展按用户投放位与组件配置（`%APPDATA%\baidu` Junction）
- `Data\settings\baidunetdisk\` —— CEF userData（缓存/IndexedDB/Local Storage，`%APPDATA%\baidunetdisk` Junction）
- `Data\settings\BaiduYunGuanjia\` —— localdata.dat/AppData/logs（`%APPDATA%\BaiduYunGuanjia` Junction）
- `Data\settings\BaiduYunKernel\` —— 内核数据（Junction）
- `Data\settings\PLogs\` —— PASS 性能日志（`%APPDATA%\PLogs` Junction）
- `Data\settings\users\` —— 根 users 目录（localdata.dat/ProxySetting.ini，DirectoriesMove 到 exe 旁）
- `Data\settings\BaiduRoot\`、`settings\BrowserEngine\`、`settings\BrowserEngineCrash\`、`settings\AutoUpdate\` —— App 树六件运行期配置（FilesMove）
- `Data\settings\AutoUpdateDownload\` —— 更新清单缓存（DirectoriesMove 到 `AutoUpdate\Download`）
- `Data\settings\Temp\` —— TEMP/TMP 重定向

## 注册表

启动器不写入持久注册表项。HKCU\Software\Baidu 走 RegistryKeys 备份恢复（便携 baidu.reg）；Run 值 BaiduYunGuanjia、HKLM 服务/外壳扩展 CLSID、Appx 服务包由动态验证逐项扫描，宿主基线零注册。

## 备份与迁移

整个 `BaiduNetdiskPortable/` 目录可直接复制到其他机器或盘符；备份只需复制 `Data/` 目录。

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
