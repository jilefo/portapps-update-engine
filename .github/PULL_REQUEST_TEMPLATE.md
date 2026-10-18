## 改动类型

- [ ] 新增便携包
- [ ] 修复启动异常
- [ ] 修复数据落地 / 重定向
- [ ] 文档更新
- [ ] 工具链改动

## 涉及的包

<!-- 列出受影响的包名，例如 CursorPortable、WPSOfficePortable -->

## 自检清单（提交前逐项确认）

- [ ] 已用脚手架生成，目录结构符合 `docs/02-架构与目录规范.md`
- [ ] `appinfo.ini` 含 `[Format]Type` / `[Details]Name` / `[Control]Start`
- [ ] Launcher ini 的 `[Environment]` 已把 `APPDATA`、`LOCALAPPDATA`
      指向 `%PAL:DataDir%`
- [ ] Launcher ini **含中文路径时保持 UTF-16LE**（不要"顺手"转 UTF-8）
- [ ] `Custom.nsh` 为 UTF-8 **且不带 BOM**
- [ ] 未提交任何第三方二进制 / `Data/` / `*.paf.exe`
- [ ] 本机跑过 `python _shared/tools/audit_repo.py` 全通过

## 验证证据

<!-- 贴出冒烟输出，例如：
     [CursorPortable] t+1.4s 应用进程 cursor.exe 出现
     [CursorPortable] Data 新写入 4; 框 0 个
     [CursorPortable] => PASS
-->

## 备注 / 遗留风险
