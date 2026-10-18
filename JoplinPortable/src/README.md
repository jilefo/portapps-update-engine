# src/ —— 启动器与安装器源码说明

本目录遵循双轨标准的 `src/` 约定，用于存放**自研**的启动器/安装器源码。

## 当前状态

JoplinPortable 使用 **PortableApps.com Launcher**（官方 NSIS 启动器），
其源码不在本仓库，而在公共工具链：

```
../_shared/toolchain/PortableApps.comLauncher/
├── App/AppInfo/          启动器配置模板
├── App/NSIS/             makensis.exe（编译器）
└── Other/Source/         启动器 NSIS 源码（Segments/、*.nsh、*.nsi）
```

构建时由 `scripts/build-portable.py` 调用 `../_shared/build_launcher.py`，
把本项目的 `appinfo.ini` 与 `Launcher/*.ini` 注入后编译出 `JoplinPortable.exe`。

## 本项目自定义逻辑

便携化定制逻辑写在：

```
portableapps/App/AppInfo/Launcher/Custom.nsh
```

用于处理各应用特有的目录联接建立与拆除逻辑。

## 若改为自研启动器

将新启动器源码放入本目录，并在 `scripts/build-portable.py` 中
替换编译入口即可；`portableapps/` 的配置格式保持不变。
