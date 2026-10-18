# 构建说明（BUILD.md）

## 环境

- Windows 10/11 x64，Python 3.10+
- PortableApps.com Launcher（本 monorepo 的 `Template Center/`）
- NSIS（随 PAL 附带）、exeico（图标提取）

## 构建步骤

```bash
python scripts/build-portable.py
```

流程：清理 `dist/` → 复制 `portableapps/` 源 → 编译启动器 → 校验结构。

## 依赖锁定

原程序安装包版本与 SHA256 固定记录在 `THIRD_PARTY_NOTICES.md`，
更换安装包必须同步更新该文件与 `portableapps/App/AppInfo/appinfo.ini`。
