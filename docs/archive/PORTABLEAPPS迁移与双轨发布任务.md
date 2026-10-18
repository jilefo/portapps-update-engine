> 📦 **迁移说明**：本文由 `<旧工作区>/PORTABLEAPPS_MIGRATION_AND_DUAL_TRACK_RELEASE_TASK.md` 迁入本仓库（2026-10-18）。
> 文中路径已按迁移后的新位置更新；脚本类路径现指向本仓库 `<旧工作区>/scripts\`（2026-10-18 已迁入本仓库 _shared/tools/ 并去除绝对路径硬编码）。

# 便携软件项目统一迁移、独立项目化、双轨开源发布与自动更新流水线任务

## 1. 任务目标

将以下 39 个便携软件项目全部迁移并统一整理到 `<仓库根>/`。

每个项目必须作为独立项目存放，拥有独立目录、独立文档、独立版本信息、独立更新维护能力，并**严格遵循“GitHub 开源与 PortableApps 双轨发布标准”**。目标是一份源码开源到 GitHub，一份成品发布到 GitHub Releases（及 PortableApps.com）。

**排除特例**：`FoxitPDFPortable`、`SublimeTextPortable`、`WPSOfficePortable` 这三个项目不需要自动更新脚本，也不参与自动打包发布。但必须保持独立目录结构、完整开源文档和双轨标准基础框架。

## 2. 项目清单

1. AiPyProPortable
2. BaiduNetdiskPortable
3. CherryStudioPortable
4. CodeArtsAgentPortable
5. CodeArtsPortable
6. CodeBuddyCNPortable
7. ComatePortable
8. CursorPortable
9. eDiaryPortable
10. FeishuPortable
11. FSCapturePortable
12. JoplinPortable
13. JoyCodePortable
14. LobsterAIPortable
15. MiaoshouPortable
16. MiniMaxCodePortable
17. OfficeAcePortable
18. QoderCNIDEPortable
19. QoderCNPortable
20. QQNTPortable
21. QQPortable
22. QuarkCloudDrivePortable
23. ReNamerPortable
24. SoloMDPortable
25. TIMPortable
26. TodayCNPortable
27. TraeCNPortable
28. TyporaPortable
29. WeixinPortable
30. WeMeetPortable
31. WinClawPortable
32. WorkBuddyPortable
33. WXWorkPortable
34. ZenBrowserPortable
35. ZoomPortable
36. FoxitPDFPortable（不自动更新/不自动发布）
37. SublimeTextPortable（不自动更新/不自动发布）
38. WPSOfficePortable（不自动更新/不自动发布）
39. KukuAIPortable

## 3. 双轨发布标准架构 (核心)

不要将 GitHub 仓库根目录直接做成 PortableApps 最终包。必须采用**源码与产物分离**的双轨架构。每个独立项目必须强制使用以下目录结构：

```text
<项目名>Portable/
├── .editorconfig
├── .gitattributes
├── .gitignore
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml
│   │   ├── feature_request.yml
│   │   └── config.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── CODEOWNERS
│   ├── dependabot.yml
│   └── workflows/
│       ├── ci.yml
│       ├── release.yml
│       └── portableapps.yml
├── LICENSE
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── CHANGELOG.md
├── SUPPORT.md
├── THIRD_PARTY_NOTICES.md
├── docs/
│   ├── PORTABLE.md
│   ├── BUILD.md
│   └── RELEASE.md
├── portableapps/                 [PortableApps 源文件目录]
│   ├── App/
│   │   ├── AppInfo/
│   │   │   ├── appinfo.ini
│   │   │   ├── launcher.ini
│   │   │   ├── installer.ini
│   │   │   ├── appicon.ico
│   │   │   ├── appicon_16.png
│   │   │   ├── appicon_32.png
│   │   │   └── appicon_128.png
│   │   └── <AppName>/            [原程序占位或下载脚本]
│   ├── help.html
│   └── Other/
│       ├── Help/Images/
│       └── Source/
├── scripts/
│   ├── build-portable.ps1
│   └── package-paf.ps1
├── src/                          [启动器源码，如有]
├── tests/
└── dist/                         [构建输出，需加入 .gitignore]
    ├── <项目名>Portable/
    ├── <项目名>Portable_X.X.paf.exe
    ├── SHA256SUMS
    └── sbom.spdx.json