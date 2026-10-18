# 发布说明（RELEASE.md）

1. 运行 `python scripts/build-portable.py` 生成 `dist/LobsterAIPortable/`。
2. 运行 `python tests/test_structure.py` 校验 PortableApps.com Format 3.9。
3. 动态落盘验证：启动 → 写入测试数据 → 关闭 → 确认数据全部在 `Data/`。
4. 打 tag 发布；发布资产包含整个 `dist/LobsterAIPortable/` 的压缩包与 SHA256SUMS。
