# 发布说明（RELEASE.md）

## 步骤

1. 运行 `python scripts/build-portable.py` 生成 `dist/KukuAIPortable/`。
2. 运行 `python tests/test_structure.py` 校验 PortableApps.com Format 3.9。
3. 动态落盘验证：启动 → 写入测试数据 → 关闭 → 确认数据全部在 `Data/`。
4. 打包：`python scripts/package-paf.py`（生成压缩包与 `SHA256SUMS`）。
5. 打 tag 发布；发布资产包含 `dist/KukuAIPortable/` 压缩包、`SHA256SUMS` 与 `sbom.spdx.json`。

## 自动化发布

打`v*` tag 触发 `.github/workflows/release.yml`，自动构建、上传产物、
生成 `SHA256SUMS` 与 SBOM 到 GitHub Releases。

维护侧更新检测：

```bash
python ../_shared/update_engine.py detect  --project KukuAIPortable
python ../_shared/update_engine.py report  --project KukuAIPortable
```

## 发布检查清单

- [ ] `appinfo.ini` 所有必填字段完整，`PackageVersion` 已更新
- [ ] `launcher.ini` 的 `ProgramExecutable` 指向存在的可执行文件
- [ ] 图标文件齐全且尺寸合规
- [ ] 所有用户数据写入 `Data/`，`App/` 保持干净
- [ ] 从含空格路径、不同盘符均可运行
- [ ] 全新安装正常，覆盖升级不丢失设置
- [ ] 直接运行启动器正常，不依赖 PortableApps.com 平台
- [ ] `THIRD_PARTY_NOTICES.md` 已同步原程序版本与哈希
