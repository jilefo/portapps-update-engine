# 构建说明（BUILD.md）

## 环境

- Windows 10/11 x64
- Python 3.10+（仅需标准库）
- PortableApps.com Launcher 工具链（位于 `../_shared/toolchain/`，
  或用环境变量 `PAF_TOOLCHAIN` 指定）

## 构建步骤

```bash
python scripts/build-portable.py
```

流程：清理 `dist/` → 复制 `portableapps/` 源 → 编译启动器 → 校验结构。

## 工具链解析

构建脚本通过 `scripts/toolchain.py` 定位公共工具链，优先级：

1. 环境变量 `PAF_TOOLCHAIN`
2. `../../_shared`（标准布局）
3. `../_shared`
4. `<项目>/toolchain`

找不到时报错并给出修复建议，**不会静默回退到旧路径**。

## PowerShell 包装

```powershell
.\scripts\build-portable.ps1
```

## 依赖锁定

原程序版本与哈希记录在 `THIRD_PARTY_NOTICES.md` 与
`../_shared/configs/CherryStudioPortable.yaml`。更换原程序版本必须同步更新这两处，
以及 `portableapps/App/AppInfo/appinfo.ini` 的 `PackageVersion`。
