# KukuAIPortable Portable

KukuAIPortable Portable 的便携化打包版本。

本仓库遵循《开源与 PortableApps 双轨发布标准》组织：源码、PortableApps 配置
与构建脚本在仓库内，最终便携包由 `scripts/build-portable.py` 构建到 `dist/`。

## 下载与使用

构建产物位于 `dist/KukuAIPortable/`，双击 `KukuAIPortable.exe` 即可运行，无需安装。
所有用户数据写入 `Data/` 目录，删除 `Data/` 即恢复初始状态。

## 目录结构

```
KukuAIPortable/
├── portableapps/      PortableApps.com Format 3.9 源文件
│   ├── App/AppInfo/   appinfo.ini、启动器配置、图标
│   ├── App/<App>/     原程序文件
│   └── Other/         帮助与源码说明
├── scripts/           构建脚本（build-portable / package-paf / toolchain 定位）
├── docs/              PORTABLE.md / BUILD.md / RELEASE.md
├── tests/             结构与配置校验
├── src/               启动器与安装器相关源码/说明
└── dist/              构建输出（已加入 .gitignore）
```

## 双轨发布

| 轨道 | 目标 | 产物 |
| --- | --- | --- |
| GitHub 开源 | 开发者与贡献者 | 源码、`portableapps/` 配置、构建脚本 |
| PortableApps 成品 | 最终用户 | `KukuAIPortable_X.X.paf.exe`、`SHA256SUMS`、`sbom.spdx.json` |

- 本项目已接入自动更新流水线（`_shared/update_engine.py`），版本检测与发布策略见 `_shared/configs/KukuAIPortable.yaml`。


## 构建

```bash
python scripts/build-portable.py
```

详见 [docs/BUILD.md](docs/BUILD.md)与 [docs/RELEASE.md](docs/RELEASE.md)。

## 便携模式

数据落盘位置、注册表行为、备份与升级方式见 [docs/PORTABLE.md](docs/PORTABLE.md)。

## 许可证

本仓库的打包配置与构建脚本以 MIT 发布（见 LICENSE）。
原软件 KukuAIPortable Portable 的权利归其发布者所有，请遵守其 EULA（见 THIRD_PARTY_NOTICES.md）。

当前打包版本：**1.0**
