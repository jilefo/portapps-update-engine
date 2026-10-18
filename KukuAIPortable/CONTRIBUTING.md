# 贡献指南

1. 任何修改请先在 issue 中说明意图。
2. 便携化逻辑改动必须附带动态落盘验证证据（`Data/` 目录新增清单 + 宿主零泄漏）。
3. 禁止提交 `dist/`、`portableapps/Data/` 等构建产物与用户数据。
4. 提交前运行 `python tests/test_structure.py` 确认结构合规。
5. 涉及原程序版本升级时，必须同步更新
   `portableapps/App/AppInfo/appinfo.ini` 的 `PackageVersion`
   与 `THIRD_PARTY_NOTICES.md` 中的版本与哈希。
