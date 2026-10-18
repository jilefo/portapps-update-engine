# Weixin Portable

微信便携版 —— 聊天记录/接收文件全量落盘 Data，宿主零残留

本仓库遵循《开源与 PortableApps 双轨发布标准》组织：源码、PortableApps 配置
与构建脚本在仓库内，最终便携包由 `scripts/build-portable.py` 构建到 `dist/`。

## 下载与使用

构建产物位于 `dist/WeixinPortable/`，双击 `WeixinPortable.exe` 即可运行，无需安装。
所有用户数据写入 `Data/` 目录，删除 `Data/` 即恢复初始状态。

## 目录结构

```
WeixinPortable/
├── portableapps/      PortableApps.com Format 3.9 源文件
│   ├── App/AppInfo/   appinfo.ini、启动器配置、图标
│   ├── App/Weixin/     原程序文件
│   └── Other/         帮助与源码说明
├── scripts/           构建脚本
├── docs/              PORTABLE.md / BUILD.md / RELEASE.md
├── tests/             结构与配置校验
└── dist/              构建输出（已加入 .gitignore）
```

## 许可证

本仓库的打包配置与构建脚本以 MIT 发布（见 LICENSE）。
原软件 Weixin 的权利归 Tencent 所有，请遵守其 EULA（见 THIRD_PARTY_NOTICES.md）。
