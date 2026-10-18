# Sublime Text Portable

Sublime Text 便携版（官方 portable zip 构建，Build 4200）

本仓库遵循《开源与 PortableApps 双轨发布标准》组织：源码、PortableApps 配置
与构建脚本在仓库内，最终便携包由 `scripts/build-portable.py` 构建到 `dist/`。

## 下载与使用

构建产物位于 `dist/SublimeTextPortable/`，双击 `SublimeTextPortable.exe` 即可运行，无需安装。
所有用户数据写入 `Data/` 目录，删除 `Data/` 即恢复初始状态。

## 目录结构

```
SublimeTextPortable/
├── portableapps/      PortableApps.com Format 3.9 源文件
│   ├── App/AppInfo/   appinfo.ini、启动器配置、图标
│   ├── App/SublimeText/     原程序文件
│   └── Other/         帮助与源码说明
├── scripts/           构建脚本
├── docs/              PORTABLE.md / BUILD.md / RELEASE.md
├── tests/             结构与配置校验
└── dist/              构建输出（已加入 .gitignore）
```

## 许可证

本仓库的打包配置与构建脚本以 MIT 发布（见 LICENSE）。
原软件 Sublime Text 的权利归 Sublime HQ Pty Ltd 所有，请遵守其 EULA（见 THIRD_PARTY_NOTICES.md）。
