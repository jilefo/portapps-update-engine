# TIMPortable —— 自动更新与发布流水线

本项目由 `PortableApps/_shared/` 下的公共工具链统一驱动，
自身不重复实现构建逻辑。

## 组件

| 文件 | 作用 |
| --- | --- |
| `_shared/toolchain.py` | 工具链定位（PAL 源码树、NSIS、更新引擎） |
| `_shared/build_launcher.py` | 编译 PortableApps.com Launcher 启动器 |
| `_shared/update_engine.py` | 八阶段更新流水线（detect→…→rollback） |
| `_shared/configs/TIMPortable.yaml` | 本项目更新配置（版本源、节奏、门禁策略） |
| `_shared/gen_update_configs.py` | 从各项目结构重新生成全部 yaml |

## 常用命令

```bash
# 工具链自检
python ../_shared/toolchain.py

# 构建便携包
python scripts/build-portable.py

# 结构校验
python tests/test_structure.py

# 更新状态报告
python ../_shared/update_engine.py report

# 版本检测（仅在 version_source 已实证时才联网）
python ../_shared/update_engine.py detect --project TIMPortable
```

## 更新流水线阶段

```
detect → download/ingest → extract → diff → test → stage → release（门禁） → rollback
```

强制约束：

- 破坏性操作默认 `dry_run=True`，需显式 `--execute` 才落地
- `Data/` 目录只读，任何阶段不写入/删除用户数据
- 状态文件原子写（临时文件 + `os.replace`）
- 仅最新版本接收更新；保留最近 3 个版本以支持回滚

## 版本源诚实原则

`configs/TIMPortable.yaml` 的 `version_source.type` 为 `manual` 时表示**尚无已实证的
在线版本源**——此时由人工下载安装包后用 `ingest` 子命令接管后续全流程，
不会虚构 URL 或版本号。已实证的源（如 `github_releases` / `api`）才会联网检测。
