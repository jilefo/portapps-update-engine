# `_shared/scripts/` —— 通用构建与测试脚本（39 包共用一份）

这些脚本**曾经每个包复制一份**（共 218 个文件）。2026-10-18 收敛为一份
参数化通用版：包名不再写死，由 `_pkg.py` 自动推导。

## 用法

三种方式任选（优先级从高到低）：

```bash
# 1. 显式传包名（最明确）
python _shared/scripts/test_structure.py CursorPortable

# 2. 在包目录下运行（自动识别当前目录名）
cd CursorPortable
python ../_shared/scripts/build-portable.py

# 3. 环境变量
PAF_PKG=CursorPortable python _shared/scripts/gen-sbom.py
```

PowerShell 版同理：

```powershell
_shared\scripts\build-portable.ps1
_shared\scripts\package-paf.ps1 -Pkg CursorPortable
```

## 脚本清单

| 脚本 | 作用 |
|---|---|
| `_pkg.py` | 包名/包根目录定位（被其他脚本 import，也可单独跑看推导结果） |
| `build-portable.py` | 构建 dist：清理 → 复制 `portableapps/` → 编译启动器 → 结构校验 |
| `build-portable.ps1` | 上面那个的薄包装（主逻辑在 Python） |
| `package-paf.py` | 生成 dist 压缩包与 `SHA256SUMS`（`--checksum-only` 只算校验和） |
| `package-paf.ps1` | 上者 + 尝试调用 PortableApps.com Installer 生成 `.paf.exe` |
| `gen-sbom.py` | 生成 SPDX SBOM |
| `toolchain.py` | 工具链转发器（转发到 `_shared/toolchain.py`） |
| `test_structure.py` | PortableApps.com Format 3.9 结构校验 |

## 收敛背景（别再复制回包里）

实测重复度：

| 文件 | 份数 | 重复情况 |
|---|---|---|
| `toolchain.py` | 39 | hash **全同** |
| `package-paf.py` | 36 | hash **全同** |
| `package-paf.ps1` | 36 | hash **全同** |
| `build-portable.ps1` | 39 | hash **全同** |
| `build-portable.py` | 39 | 同模板，差异只有 docstring 包名 + `PKG = "..."` |
| `gen-sbom.py` | 39 | 同上 |
| `test_structure.py` | 39 | 同上 |

改一个模板要改 39 处，改漏一处就埋雷。现在只改一份。

原各包副本已归档到 `GreenSoftMake/Backups/脚手架脚本归档/<包名>/`，需要时可回查。

## 校验规则的两个已知白名单

`test_structure.py` 判「dist 根目录多出文件」时允许：

- `version.json` —— 更新引擎写入的版本元数据
  （`current_version` / `previous_version` / `released_at` / `run_id` / `channel`），
  运行期有追踪价值，不是垃圾。
- 任何 `*.Portable.exe` —— **多入口包**的分体启动器，
  例如 WPSOfficePortable 除主入口外还有
  Writer / Spreadsheets / Presentation / wpsPDF 四个。

这两条都是被误报过才补的：version.json 曾让 CursorPortable 报 FAIL，
WPS 的多入口曾让整个包报 FAIL。
