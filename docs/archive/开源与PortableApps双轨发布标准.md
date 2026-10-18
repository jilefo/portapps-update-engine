> 📦 **迁移说明**：本文由 `<旧工作区>/开源与PortableApps双轨发布标准.md` 迁入本仓库（2026-10-18）。
> 文中路径已按迁移后的新位置更新；脚本类路径现指向本仓库 `<旧工作区>/scripts\`（2026-10-18 已迁入本仓库 _shared/tools/ 并去除绝对路径硬编码）。

# 开源与 PortableApps 双轨发布标准

本文整合开源项目标准、GitHub 开源要求、PortableApps.com 发布规范，以及双轨发布流程。适用于便携软件项目，目标是一份源码开源到 GitHub，一份成品发布到 PortableApps.com 和 GitHub Releases。

---

## 第一部分：开源项目标准文件清单

严格按 OSI 开源定义，法律上唯一必须的是 LICENSE。其余是仓库卫生与 GitHub 社区标准。若按 GitHub Community Profile、OpenSSF Scorecard 和便携软件发布实践，基础骨架包括：

.editorconfig
.gitattributes
.github
.gitignore
LICENSE
README.md

其中 .github 只是目录，内部还要补文件。

### 根目录建议补

CONTRIBUTING.md
贡献指南、开发环境、测试、PR 流程、DCO/CLA。

CODE_OF_CONDUCT.md
行为准则，通常用 Contributor Covenant。

SECURITY.md
漏洞披露流程、支持版本、联系方式。

CHANGELOG.md
遵循 Keep a Changelog。

SUPPORT.md
用户去哪里提问、issue 范围。

AUTHORS.md 或 CONTRIBUTORS.md
作者与贡献者。

GOVERNANCE.md 或 MAINTAINERS.md
治理与维护者名单。

INSTALL.md 或 USAGE.md 或 docs/
安装、使用、便携模式说明。

ROADMAP.md
路线图，可选但推荐。

THIRD_PARTY_NOTICES.md 或 NOTICE
第三方依赖许可证；Apache-2.0 项目尤其需要 NOTICE。

CITATION.cff
若希望被学术引用。

TRADEMARK.md
有商标或品牌保护时。

DCO 或 CLA 文件
若要求贡献者签署。

.reuse/dep5 或 REUSE.toml
若采用 REUSE 许可证合规。

构建与依赖锁文件
如 Makefile、build.sh、package.json、Cargo.toml、go.mod、*.lock，取决于技术栈。

### .github 下建议补

.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/ISSUE_TEMPLATE/config.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/CODEOWNERS
.github/workflows/ci.yml
.github/workflows/release.yml
.github/workflows/codeql.yml
.github/workflows/scorecard.yml
.github/dependabot.yml 或 renovate.json
.github/FUNDING.yml
.github/release.yml
.github/labeler.yml

SECURITY.md、CONTRIBUTING.md、SUPPORT.md 可放根目录，也可放这里。

### 便携软件项目特有

docs/PORTABLE.md
说明配置、数据、缓存写哪里，是否写注册表，如何备份、迁移、升级。

打包脚本
如 scripts/package-portable.sh 或 .ps1，生成 zip、7z、tar.gz。

发布资产
SHA256SUMS、*.sig 或 *.asc，GPG、minisign 或 Sigstore 签名。

SBOM
sbom.spdx.json 或 bom.json，以及第三方许可证清单。

可重现构建说明
固定依赖、锁文件、构建矩阵、平台兼容表。

若发布到 PortableApps.com，还需要其专用结构，如 App/AppInfo/AppInfo.ini、启动器、help.html、Data/ 等。

### 最小补齐优先级

1. CONTRIBUTING.md
2. CODE_OF_CONDUCT.md
3. SECURITY.md
4. CHANGELOG.md
5. SUPPORT.md
6. .github/ISSUE_TEMPLATE/*
7. .github/PULL_REQUEST_TEMPLATE.md
8. .github/CODEOWNERS
9. .github/workflows/ci.yml
10. .github/workflows/release.yml
11. .github/dependabot.yml
12. THIRD_PARTY_NOTICES.md
13. 便携发布：校验和、签名、SBOM、docs/PORTABLE.md

---

## 第二部分：发布到 PortableApps.com 的要求

要发布到 PortableApps.com，仓库需要从开源项目标准切换到 PortableApps.com Format 3.9 规范。现有文件是基础，但 PortableApps.com 有自己一套目录、配置和发布要求。

### 核心目录结构

PortableApps.com Format 强制要求所有文件必须按以下结构组织，最终打包成 .paf.exe 格式。

YourAppPortable/
├── YourAppPortable.exe          主启动器，必需
├── help.html                    主帮助文件，必需
├── App/                         程序核心文件
│   ├── AppInfo/                 应用配置信息
│   │   ├── appinfo.ini          核心，应用元数据
│   │   ├── launcher.ini         核心，启动器行为配置
│   │   ├── installer.ini        安装器配置，可选
│   │   ├── appicon.ico          主图标，必需
│   │   ├── appicon_16.png       16x16 图标，必需
│   │   ├── appicon_32.png       32x32 图标，必需
│   │   ├── appicon_128.png      128x128 图标，推荐
│   │   └── EULA.txt             许可协议，如适用
│   └── YourApp/                 你的程序二进制文件
├── Data/                        必需，所有用户数据与配置
│   └── settings/                程序生成的配置应存放于此
├── DefaultData/                 可选，默认数据模板
└── Other/                       可选，其他文件
    ├── Help/                    help.html 引用的图片等
    │   └── Images/
    └── Source/                  启动器与安装器源码及许可证

关键点：
Data 目录是灵魂。所有用户设置、配置文件都必须写入 Data。程序本身不能依赖 App 目录写入。这样备份工具才能正确工作，删除 Data 即可恢复初始状态。
根目录只能有启动器和 help.html。不要在主目录下放置其他文件。

### 核心配置文件

这两个 INI 文件是 PortableApps.com 格式的核心，决定应用如何被平台识别和运行。

1. App/AppInfo/appinfo.ini
这是应用的身份证，告诉 PortableApps.com 平台这个应用是什么。

[Format]
Type=PortableApps.comFormat
Version=3.9

[Details]
Name=YourApp Portable
AppID=YourAppPortable
Publisher=Your Name & PortableApps.com
Homepage=https://your-app-homepage
Category=Utilities
Description=YourApp Portable is a brief description.
Language=English

[License]
Shareable=true
OpenSource=true
Freeware=true
CommercialUse=true

[Version]
PackageVersion=1.0.0.1
DisplayVersion=1.0

[Control]
Start=YourAppPortable.exe

2. App/AppInfo/launcher.ini
它告诉 PortableApps.com Launcher 如何让应用便携化，比如重定向注册表、处理路径等。这个文件通常通过 PortableApps.com Development Toolkit 或 Launcher Generator 生成，手动编写较复杂。

### 图标要求

图标必须严格按照规定命名和格式放置在 App/AppInfo/ 目录下。
必需文件：appicon.ico、appicon_16.png、appicon_32.png。
推荐文件：appicon_128.png，高分辨率。
appicon.ico 格式：必须包含 6 种尺寸与色深组合：16px、32px、48px 的 256 色版本，以及 16px、32px、48px 的 True Color + Alpha 版本。

### 必需的开发工具

强烈建议使用官方工具来生成和验证上述结构，避免手动配置出错。
PortableApps.com Development Toolkit：用于生成项目结构、编辑 appinfo.ini 等。
PortableApps.com Launcher：用于生成启动器可执行文件，并读取 launcher.ini 实现便携化。
PortableApps.com Installer：最终将你的目录打包成 .paf.exe 安装文件。

### 发布前检查清单

在提交发布前，请逐一核对以下 PortableApps.com 官方发布检查项：
格式合规：目录结构是否符合 PortableApps.com Format 3.9 规范。
路径兼容：能否从包含空格的路径下运行？能否在不同盘符，如 C: 和 D:，下正常运行？
数据隔离：所有用户数据是否都正确存储在 Data 目录下？App 目录是否保持只读或干净？
全新安装与升级：在空目录安装后能否正常运行？覆盖安装旧版本后，用户设置是否保留？
直接运行：不通过 PortableApps.com 平台，直接双击 YourAppPortable.exe 能否正常启动？

### 发布流程概要

1. 开发与测试：使用工具制作便携版，并在论坛的 Beta Testing 板块发布测试版，收集反馈。
2. 提交发布：将打包好的 .paf.exe 文件及相关信息提交给 PortableApps.com 的发布团队。他们会对应用进行最终审查、病毒扫描，并创建应用页面。
3. 注意事项：如果你不是原软件的开发者，需要确保你的打包行为符合原软件的许可证。同时，PortableApps.com 目前对新应用的收录流程可能比较缓慢，建议先在社区论坛积极互动。

简单来说，核心工作是：用官方工具，按 App、Data、Other 结构重组软件，补全 appinfo.ini 和 launcher.ini，准备好合规的图标，然后通过官方安装器打包成 .paf.exe。

---

## 第三部分：同时开源到 GitHub

可以同时做，但关键是：不要把 GitHub 仓库根目录直接做成 PortableApps 最终包。
PortableApps.com Format 要求最终包根目录只有启动器和 help.html，而 GitHub 开源仓库根目录需要 README.md、LICENSE、CONTRIBUTING.md、.github/ 等。两者硬合会互相冲突。

推荐模式是：GitHub 仓库保存源码、PortableApps 配置、构建脚本；CI 或本地脚本生成 dist/ 下的 PortableApps 最终包。

### 推荐仓库结构

你的仓库/
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
│       ├── portableapps.yml
│       ├── codeql.yml
│       └── scorecard.yml
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
├── portableapps/                 PortableApps.com 源文件
│   ├── App/
│   │   ├── AppInfo/
│   │   │   ├── appinfo.ini
│   │   │   ├── launcher.ini
│   │   │   ├── installer.ini
│   │   │   ├── appicon.ico
│   │   │   ├── appicon_16.png
│   │   │   ├── appicon_32.png
│   │   │   └── appicon_128.png
│   │   └── YourApp/              原程序占位或下载脚本，不建议提交大二进制
│   ├── help.html
│   └── Other/
│       ├── Help/
│       │   └── Images/
│       └── Source/
├── scripts/
│   ├── build-portable.sh
│   ├── build-portable.ps1
│   └── package-paf.sh
├── src/                          启动器与安装器源码，如有
├── tests/
└── dist/                         构建输出，.gitignore 忽略

最终构建输出类似：

dist/
├── YourAppPortable/
│   ├── YourAppPortable.exe
│   ├── help.html
│   ├── App/
│   ├── Data/
│   └── Other/
├── YourAppPortable_1.0.paf.exe
├── SHA256SUMS
├── SHA256SUMS.sig
└── sbom.spdx.json

### 你现在已有的文件

你已有：
.editorconfig
.gitattributes
.github
.gitignore
LICENSE
README.md

这些只是基础。开源到 GitHub 并发布 PortableApps.com，还缺很多。

### GitHub 开源还必须补

根目录建议补：
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
CHANGELOG.md
SUPPORT.md
THIRD_PARTY_NOTICES.md
docs/PORTABLE.md
docs/BUILD.md
docs/RELEASE.md

.github/ 下建议补：
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/ISSUE_TEMPLATE/config.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/CODEOWNERS
.github/dependabot.yml
.github/workflows/ci.yml
.github/workflows/release.yml
.github/workflows/portableapps.yml
.github/workflows/codeql.yml
.github/workflows/scorecard.yml

README.md 至少应包含：
项目介绍
下载地址：GitHub Releases 和 PortableApps.com 页面
安装与使用
便携模式说明
构建方法
许可证
贡献方式
安全披露方式

### PortableApps.com 还必须补

放在 portableapps/ 子目录中：
portableapps/App/AppInfo/appinfo.ini
portableapps/App/AppInfo/launcher.ini
portableapps/App/AppInfo/installer.ini
portableapps/App/AppInfo/appicon.ico
portableapps/App/AppInfo/appicon_16.png
portableapps/App/AppInfo/appicon_32.png
portableapps/App/AppInfo/appicon_128.png
portableapps/help.html
portableapps/Other/Help/Images/
portableapps/Other/Source/

还需要：
scripts/build-portable.sh
scripts/build-portable.ps1
scripts/package-paf.sh
docs/PORTABLE.md

docs/PORTABLE.md 要说明：
数据写入 Data/
是否写注册表
如何备份、迁移、升级
是否支持多用户
是否支持空格路径和不同盘符
如何卸载和恢复初始状态

### .gitignore 建议加入

dist/
build/
*.paf.exe
portableapps/Data/
portableapps/DefaultData/
*.log

不要把用户数据、构建产物、最终 .paf.exe 提交到 Git 仓库。它们应该放在 GitHub Releases。

### GitHub Actions 建议

至少三个工作流：

ci.yml
功能：语法检查、INI 校验、图标尺寸检查、测试、构建 PortableApps 目录。

portableapps.yml
功能：下载原软件、校验哈希、生成 PortableApps 结构、调用 Launcher 与 Installer、生成 .paf.exe。

release.yml
功能：打 tag 后自动创建 GitHub Release，上传：
YourAppPortable_1.0.paf.exe
SHA256SUMS
SHA256SUMS.sig
sbom.spdx.json

### 发布到 GitHub 和 PortableApps.com 的关系

GitHub 负责：
开源源码
记录问题
接受 PR
发布 Release
存 .paf.exe、校验和、签名、SBOM

PortableApps.com 负责：
官方应用页面
最终 .paf.exe 收录
平台内更新
社区测试反馈

通常流程：
1. 在 GitHub 建仓库，补齐开源文件。
2. 在 portableapps/ 中维护 PortableApps 源文件。
3. 用脚本或 CI 构建 dist/YourAppPortable/。
4. 用 PortableApps.com Installer 生成 .paf.exe。
5. 在 PortableApps.com 论坛 Beta Testing 发测试版。
6. 收集反馈后提交正式发布。
7. 同时在 GitHub Releases 上传 .paf.exe、校验和、签名、SBOM。

### 合规重点

LICENSE 必须是 OSI 认可许可证，且与原软件许可证兼容。
如果你不是原软件作者，必须遵守原软件 EULA、许可证和商标政策。
appinfo.ini 中 [License] 必须如实填写。
第三方依赖要写进 THIRD_PARTY_NOTICES.md。
如果原项目是 Apache-2.0，通常还要保留 NOTICE。
发布 .paf.exe 时建议提供 SHA256SUMS 和 GPG 或 minisign 签名。

### 最小补齐优先级

1. CONTRIBUTING.md
2. CODE_OF_CONDUCT.md
3. SECURITY.md
4. CHANGELOG.md
5. SUPPORT.md
6. .github/ISSUE_TEMPLATE/*
7. .github/PULL_REQUEST_TEMPLATE.md
8. .github/CODEOWNERS
9. .github/workflows/ci.yml
10. .github/workflows/release.yml
11. portableapps/App/AppInfo/appinfo.ini
12. portableapps/App/AppInfo/launcher.ini
13. 合规图标文件
14. scripts/build-portable.*
15. docs/PORTABLE.md
16. THIRD_PARTY_NOTICES.md
17. SHA256SUMS、签名、SBOM

---

## 第四部分：双轨发布标准

本文定义一套完整的双轨发布方案，同时满足两个目标：
轨道一：GitHub 开源仓库，面向开发者、贡献者，包含完整源码、构建脚本、社区健康文件。
轨道二：PortableApps.com 与 GitHub Releases 成品发布，面向最终用户，分发 PortableApps.com Format 3.9 规范的 .paf.exe 安装包。

两条轨道共享同一仓库，但构建产物与源码分离，避免格式冲突。

### 核心设计原则

为什么不能把仓库根目录直接做成 PortableApps 包：
PortableApps.com Format 3.9 要求最终分发包根目录只能包含：
AppNamePortable.exe，主启动器
help.html，主帮助文件
不得有其他文件。

而 GitHub 开源仓库根目录必须包含：
README.md
LICENSE
CONTRIBUTING.md
.github/
构建配置与源码目录

两者硬合会违反 PortableApps.com Format 规范，导致无法通过官方验证。

推荐架构：源码与产物分离。
GitHub 仓库保存源码、配置、脚本。
CI 构建流水线生成 dist/YourAppPortable/。
PortableApps.com Installer 生成 YourAppPortable_X.X.paf.exe。
GitHub Releases 上传 .paf.exe、校验和、SBOM。
PortableApps.com 官方收录可选。

### GitHub 仓库完整结构

你的仓库/
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
│   ├── FUNDING.yml
│   └── workflows/
│       ├── ci.yml
│       ├── release.yml
│       ├── portableapps.yml
│       ├── codeql.yml
│       └── scorecard.yml
├── LICENSE
├── README.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── CHANGELOG.md
├── SUPPORT.md
├── THIRD_PARTY_NOTICES.md
├── CITATION.cff                    可选，如需学术引用
├── docs/
│   ├── PORTABLE.md
│   ├── BUILD.md
│   └── RELEASE.md
├── portableapps/                   PortableApps.com 源文件
│   ├── App/
│   │   ├── AppInfo/
│   │   │   ├── appinfo.ini
│   │   │   ├── launcher.ini
│   │   │   ├── installer.ini
│   │   │   ├── appicon.ico
│   │   │   ├── appicon_16.png
│   │   │   ├── appicon_32.png
│   │   │   └── appicon_128.png
│   │   └── YourApp/                原程序占位或下载脚本
│   ├── help.html
│   ├── DefaultData/                可选
│   └── Other/
│       ├── Help/
│       │   └── Images/
│       └── Source/
├── scripts/
│   ├── build-portable.sh
│   ├── build-portable.ps1
│   └── package-paf.sh
├── src/                            启动器与安装器源码，如有
├── tests/
└── dist/                           构建输出，.gitignore 忽略
    ├── YourAppPortable/
    ├── YourAppPortable_X.X.paf.exe
    ├── SHA256SUMS
    ├── SHA256SUMS.sig
    └── sbom.spdx.json

### GitHub 开源必需文件清单

根目录社区健康文件：
README.md：项目介绍、安装、使用、构建、许可证，必需。
LICENSE：开源许可证全文，必需。
CONTRIBUTING.md：贡献指南、分支策略、PR 流程，强烈推荐。
CODE_OF_CONDUCT.md：社区行为准则，推荐。
SECURITY.md：漏洞披露流程、联系方式，推荐。
CHANGELOG.md：版本变更记录，Keep a Changelog 格式，推荐。
SUPPORT.md：用户支持渠道说明，可选。
THIRD_PARTY_NOTICES.md：第三方依赖许可证，推荐。
CITATION.cff：学术引用信息，可选。

.github/ 目录必需内容：
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/ISSUE_TEMPLATE/config.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/CODEOWNERS
.github/dependabot.yml
.github/workflows/ci.yml
.github/workflows/release.yml
.github/workflows/portableapps.yml
.github/workflows/codeql.yml
.github/workflows/scorecard.yml

.gitignore 建议内容：
dist/
build/
*.paf.exe
portableapps/Data/
portableapps/DefaultData/
portableapps/App/AppInfo/Launcher/*.ini.bak
*.log
*.tmp
*.bak
.vscode/
.idea/

不要将用户数据、构建产物、最终 .paf.exe 提交到 Git 仓库。它们应通过 GitHub Releases 分发。

### PortableApps.com 必需文件与配置

目录结构规范：
AppNamePortable/
├── AppNamePortable.exe          主启动器
├── help.html                    主帮助文件
├── App/
│   ├── AppInfo/
│   │   ├── appinfo.ini
│   │   ├── launcher.ini
│   │   ├── installer.ini
│   │   ├── appicon.ico
│   │   ├── appicon_16.png
│   │   ├── appicon_32.png
│   │   └── appicon_128.png
│   └── YourApp/                 程序二进制
├── Data/                        用户数据
└── Other/
    ├── Help/
    │   └── Images/
    └── Source/

关键约束：
根目录：只能有 AppNamePortable.exe 和 help.html，不得有其他文件。
App/：包含所有二进制文件和程序本身，通常置于 App/AppName/ 下。
Data/：包含所有用户数据，设置、配置等，不得包含任何应用程序二进制文件。
Other/：包含 help.html 引用的图片、源码、许可证等。

appinfo.ini 完整模板：
[Format]
Type=PortableApps.comFormat
Version=3.9

[Details]
Name=YourApp Portable
AppID=YourAppPortable
Publisher=Your Name & PortableApps.com
Homepage=https://your-app-homepage
Category=Utilities
Description=YourApp Portable is a brief description of your application.
Language=English
Trademarks=
InstallType=

[License]
Shareable=true
OpenSource=true
Freeware=true
CommercialUse=true
EULAVersion=1

[Version]
PackageVersion=1.0.0.1
DisplayVersion=1.0

[Control]
Start=YourAppPortable.exe
ExtractIcon=App\YourApp\YourApp.exe
Icons=1

[SpecialPaths]
Plugins=NONE

[Dependencies]
UsesJava=false
UsesDotNetVersion=

各字段说明：
[Format]：Type 固定为 PortableApps.comFormat，Version 为格式版本，当前 3.9。
[Details]：
Name：在 PortableApps.com 平台菜单中显示的名称。
AppID：全局唯一 ID，只含字母、数字、点、短横线、加号、下划线。官方发布用 AppNamePortable；第三方打包用 AppNamePortable-username。
Category：必须为以下之一：Accessibility、Development、Education、Games、Graphics & Pictures、Internet、Music & Video、Office、Security、Utilities。
[License]：如实填写 Shareable、OpenSource、Freeware、CommercialUse。
[Version]：PackageVersion 为四段式版本号，DisplayVersion 为显示版本。
[Control]：Start 指定启动器文件名，ExtractIcon 指定提取图标的程序路径。

launcher.ini 核心配置：
[Launch]
ProgramExecutable=YourApp\YourApp.exe
WorkingDirectory=%PAL:AppDir%\YourApp
CommandLineArguments=
NoSpacesInPath=false

关键参数：
ProgramExecutable，必选：指定要启动的程序，相对于 App/ 目录。例如程序在 App\YourApp\YourApp.exe，则填写 YourApp\YourApp.exe。
WorkingDirectory：设置工作目录，某些程序需要。
NoSpacesInPath：若程序不支持带空格的路径，设为 true。

便携化重定向：launcher.ini 还可配置注册表重定向、文件重定向，确保所有数据写入 Data/ 目录。建议使用 PortableApps.com Launcher Generator 生成，手动编写较复杂。

图标规范：
文件：appicon.ico，必需，必须包含 6 种尺寸与色深组合：16px、32px、48px 的 256 色版本，以及 16px、32px、48px 的 True Color + Alpha 版本。
appicon_16.png，必需，16×16 像素。
appicon_32.png，必需，32×32 像素。
appicon_128.png，推荐，128×128 像素，高分辨率显示。

### GitHub Actions 构建流水线

ci.yml，持续集成：
功能：语法检查、INI 校验、图标尺寸检查、测试、构建 PortableApps 目录。
验证目录结构符合 PortableApps.com Format 3.9。
检查根目录只有启动器和 help.html。

portableapps.yml，构建 PortableApps 包：
功能：下载原软件、校验哈希、生成 PortableApps 结构、调用 Launcher 与 Installer、生成 .paf.exe。
将 portableapps/ 内容复制到 dist/YourAppPortable/。
下载原程序二进制到 App/YourApp/。
运行 Launcher 生成启动器。
调用 PortableApps.com Installer 生成 .paf.exe。
上传 artifact。

release.yml，发布到 GitHub Releases：
功能：打 tag 后自动创建 GitHub Release，上传：
YourAppPortable_X.X.paf.exe
SHA256SUMS
SHA256SUMS.sig
sbom.spdx.json
生成校验和，签名，生成 SBOM。

### 发布流程：两份标准，一个流水线

轨道一：GitHub 开源发布
目标受众：开发者、贡献者、希望自行构建的用户。
发布内容：源码，src/、scripts/、portableapps/ 配置；社区健康文件；构建文档 docs/BUILD.md；许可证。
流程：
1. 在 GitHub 创建仓库，补齐所有社区健康文件。
2. 配置 .github/workflows/ci.yml，确保每次 PR 自动验证。
3. 在 README.md 中说明项目用途、构建方法、贡献方式。
4. 使用 Issue 模板和 PR 模板规范化社区互动。

轨道二：PortableApps.com 与 GitHub Releases 成品发布
目标受众：最终用户，便携软件使用者。
发布内容：YourAppPortable_X.X.paf.exe；SHA256SUMS；SHA256SUMS.sig，GPG 或 minisign 签名；sbom.spdx.json，软件物料清单。
流程：
1. 本地或 CI 中构建 dist/YourAppPortable/ 目录。
2. 使用 PortableApps.com Installer 生成 .paf.exe。
3. 生成校验和与签名。
4. 在 GitHub Releases 中创建新 Release，上传所有产物。
5. 可选：在 PortableApps.com 论坛 Beta Testing 板块发布测试版。
6. 可选：提交正式发布给 PortableApps.com 收录。

完整发布检查清单：
GitHub 开源轨道：
README.md 包含项目介绍、构建方法、许可证
LICENSE 存在且为 OSI 认可许可证
CONTRIBUTING.md 说明贡献流程
CODE_OF_CONDUCT.md 存在
SECURITY.md 说明漏洞披露流程
.github/ISSUE_TEMPLATE/ 存在
.github/PULL_REQUEST_TEMPLATE.md 存在
.github/CODEOWNERS 存在
.github/workflows/ci.yml 可运行
.gitignore 排除构建产物

PortableApps 成品轨道：
目录结构符合 PortableApps.com Format 3.9
根目录只有 AppNamePortable.exe 和 help.html
appinfo.ini 所有必填字段完整
launcher.ini 中 ProgramExecutable 正确
图标文件齐全且格式正确
所有用户数据写入 Data/ 目录
从不同盘符运行正常
从含空格路径运行正常
全新安装正常
覆盖升级不丢失设置
直接运行启动器正常，不依赖平台

### 合规注意事项

许可证兼容性：
LICENSE 必须是 OSI 认可的许可证，且与原软件许可证兼容。
如果你不是原软件作者，必须遵守原软件 EULA、许可证和商标政策。
appinfo.ini 中 [License] 必须如实填写。
第三方依赖要写进 THIRD_PARTY_NOTICES.md。
如果原项目是 Apache-2.0，通常还要保留 NOTICE 文件。

PortableApps.com 收录注意事项：
如果你不是原软件的开发者，打包行为必须符合原软件许可证。
PortableApps.com 对新应用的收录流程可能较慢，建议先在社区论坛积极互动。
建议先在 PortableApps.com 论坛的 Beta Testing 板块发布测试版，收集反馈后再提交正式发布。
如果原软件是商业软件，需确认其许可证是否允许重新分发。

签名与校验：
发布 .paf.exe 时建议提供 SHA256SUMS 和 GPG 或 minisign 签名。
在 GitHub Releases 中，用户可以通过校验和验证下载文件的完整性。
SBOM 有助于用户了解软件的依赖组成。

### 最小补齐优先级

如果你现在只有 .editorconfig、.gitattributes、.github、.gitignore、LICENSE、README.md，按以下优先级补齐：
1. CONTRIBUTING.md
2. CODE_OF_CONDUCT.md
3. SECURITY.md
4. CHANGELOG.md
5. SUPPORT.md
6. .github/ISSUE_TEMPLATE/bug_report.yml
7. .github/ISSUE_TEMPLATE/feature_request.yml
8. .github/ISSUE_TEMPLATE/config.yml
9. .github/PULL_REQUEST_TEMPLATE.md
10. .github/CODEOWNERS
11. .github/dependabot.yml
12. .github/workflows/ci.yml
13. .github/workflows/release.yml
14. portableapps/App/AppInfo/appinfo.ini
15. portableapps/App/AppInfo/launcher.ini
16. 合规图标文件，appicon.ico、appicon_16.png、appicon_32.png、appicon_128.png
17. scripts/build-portable.sh 与 scripts/build-portable.ps1
18. docs/PORTABLE.md
19. docs/BUILD.md
20. THIRD_PARTY_NOTICES.md
21. 发布时的 SHA256SUMS、签名、SBOM

### 总结

维度对比：
GitHub 开源轨道：
目标：源码开放、社区协作
根目录：README、LICENSE、.github 等
核心文件：CONTRIBUTING、CODE_OF_CONDUCT、SECURITY
数据位置：源码中的 src/
发布产物：源码 tag 与 Release Notes
分发渠道：GitHub Releases
验证方式：CI 测试

PortableApps 成品轨道：
目标：终端用户分发
根目录：只有启动器和 help.html
核心文件：appinfo.ini、launcher.ini
数据位置：Data/ 目录
发布产物：.paf.exe、SHA256SUMS、SBOM
分发渠道：PortableApps.com 与 GitHub Releases
验证方式：发布检查清单

两条轨道在同一仓库中通过源码与产物分离实现共存。portableapps/ 目录保存 PortableApps 配置，CI 构建 dist/ 产物，GitHub Releases 同时承载源码 tag 和 .paf.exe 成品。