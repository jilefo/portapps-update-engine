# -*- coding: utf-8 -*-
"""disable_updater.py —— 便携包内置更新器禁用处置工具

按方案第 6 节优先级执行：
  1. 启动参数禁用（追加到 launcher.ini ProgramParameters）
  2. 配置文件禁用（argv.json 写入 disable-updates 等）
  3. 组件物理处置（重命名而非删除，保留恢复路径）
  4. 环境变量禁用（launcher.ini [Environment]）

处置证据（前后文件状态）归档 evidence\\<项目>\\<runid>\\update-disable-updater\\。
所有写操作 dry_run 默认 True，须 --execute 落地。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[0]   # ...\PortableApps\_shared
sys.path.insert(0, str(ROOT))                # 定位 _paths（路径唯一解析处）
import _paths                                # noqa: E402
CONFIGS = ROOT / "configs"
EVIDENCE = ROOT / "evidence"

log = logging.getLogger("disable_updater")

# 需处置的更新器组件特征（相对程序目录，重命名为 .disabled-by-engine）
UPDATER_COMPONENTS = [
    "Update.exe", "updater.exe", "Updater.exe",
    "inno_updater.exe",  # Inno Setup 系安装器附带的自动更新组件（Cursor 实证）
    "resources/app-update.yml", "resources/app-updater.yml",
    "app-update.yml", "Squirrel.exe", "squirrel.exe",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def result(exit_code: int, msg: str, **kw) -> dict:
    out = {"exit_code": exit_code, "msg": msg, "timestamp": now_iso()}
    out.update(kw)
    log.log(logging.INFO if exit_code == 0 else logging.WARNING, "%s", msg)
    return out


def find_launcher_ini(pkg: Path) -> Path | None:
    lad = pkg / "App" / "AppInfo" / "Launcher"
    if not lad.is_dir():
        return None
    for f in sorted(lad.glob("*.ini")):
        return f
    return None


def scan_components(app_dir: Path) -> list[Path]:
    """在程序目录中查找更新器组件（不递归过深，限定三层）"""
    hits: list[Path] = []
    for rel in UPDATER_COMPONENTS:
        for hit in app_dir.rglob(Path(rel).name):
            try:
                hit.relative_to(app_dir)
            except ValueError:
                continue
            if len(hit.relative_to(app_dir).parts) <= 4:
                hits.append(hit)
    return sorted(set(hits))


def dispose_components(components: list[Path], execute: bool) -> list[dict]:
    """组件重命名为 <原名>.disabled-by-engine（改名而非删除，保留恢复路径）"""
    actions = []
    for c in components:
        dst = c.with_name(c.name + ".disabled-by-engine")
        rec = {"component": str(c), "renamed_to": str(dst)}
        if dst.exists():
            rec["action"] = "already_disabled"
        elif execute:
            os.rename(c, dst)
            rec["action"] = "renamed"
        else:
            rec["action"] = "dry_run"
        actions.append(rec)
    return actions


def patch_launcher_args(ini: Path, add_args: list[str],
                        execute: bool) -> dict:
    """启动参数禁用：ProgramParameters 追加禁用参数（去重）"""
    txt = ini.read_text(encoding="utf-8-sig")
    m = re.search(r"(?m)^(ProgramParameters\s*=\s*)(.*)$", txt)
    if not m:
        return {"action": "skipped", "reason": "ini 无 ProgramParameters 行"}
    cur = m.group(2).strip()
    to_add = [a for a in add_args if a not in cur]
    if not to_add:
        return {"action": "already_present", "current": cur}
    new_line = m.group(1) + (cur + " " if cur else "") + " ".join(to_add)
    if execute:
        txt = txt[:m.start()] + new_line + txt[m.end():]
        ini.write_text(txt, encoding="utf-8")
    return {"action": "patched" if execute else "dry_run",
            "added": to_add, "ini": str(ini)}


def patch_argv_json(app_dir: Path, execute: bool) -> dict:
    """配置文件禁用：VS Code 系 argv.json 写入 disable-updates"""
    hits = list(app_dir.rglob("argv.json"))
    hits = [h for h in hits
            if len(h.relative_to(app_dir).parts) <= 4]
    if not hits:
        return {"action": "skipped", "reason": "无 argv.json"}
    recs = []
    for h in hits:
        try:
            data = json.loads(h.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            recs.append({"file": str(h), "action": "error", "err": str(e)})
            continue
        if data.get("disable-updates") is True:
            recs.append({"file": str(h), "action": "already_present"})
            continue
        data["disable-updates"] = True
        if execute:
            h.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        recs.append({"file": str(h),
                     "action": "patched" if execute else "dry_run"})
    return {"action": "done", "files": recs}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ap = argparse.ArgumentParser(description="便携包内置更新器禁用处置")
    ap.add_argument("project", help="项目名（Configs\\<项目>.yaml）")
    ap.add_argument("--execute", action="store_true",
                    help="实际处置（默认 dry-run 预检）")
    ap.add_argument("--args", nargs="*", default=[],
                    help="追加的启动禁用参数，如 --disable-updates")
    ap.add_argument("--no-components", action="store_true",
                    help="跳过组件物理处置")
    ap.add_argument("--no-argv", action="store_true",
                    help="跳过 argv.json 处置")
    ap.add_argument("--dir", help="覆盖目标 App 目录（默认 <产品目录>\\App；"
                                  "用于处置 Staging 中的候选版本）")
    args = ap.parse_args()

    cfg = yaml.safe_load(
        (CONFIGS / f"{args.project}.yaml").read_text(encoding="utf-8-sig"))
    # dir 旧写作 <Pkg>\dist\<Pkg>；迁移后产品在 <产品根>\<Pkg>。
    # 取最后一段包名经 _paths.product_dir() 解析，两种布局全兼容。
    rel = str(cfg["dir"]).replace("/", "\\").strip("\\")
    pkg = _paths.product_dir(rel.rsplit("\\", 1)[-1])
    app_dir = Path(args.dir) if args.dir else pkg / "App"
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    ev = EVIDENCE / args.project / run_id / "update-disable-updater"
    ev.mkdir(parents=True, exist_ok=True)

    ud = cfg.get("updater_disable") or {}
    add_args = args.args or ud.get("args", [])

    components = scan_components(app_dir)
    report = {"project": args.project, "dry_run": not args.execute,
              "executed_at": now_iso(),
              "components_found": [str(c) for c in components],
              "actions": {}}

    # 优先级 1：启动参数
    if add_args:
        ini = find_launcher_ini(pkg)
        if ini:
            report["actions"]["launcher_args"] = patch_launcher_args(
                ini, add_args, args.execute)
        else:
            report["actions"]["launcher_args"] = {
                "action": "skipped", "reason": "未找到 launcher ini"}
    # 优先级 2：配置文件
    if not args.no_argv:
        report["actions"]["argv_json"] = patch_argv_json(app_dir,
                                                         args.execute)
    # 优先级 3：组件物理处置（改名非删除）
    if not args.no_components:
        report["actions"]["components"] = dispose_components(
            components, args.execute)

    (ev / "disable_updater.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    n_comp = len(report.get("actions", {}).get("components", []))
    return _finish(report, ev, n_comp)


def _finish(report: dict, ev: Path, n_comp: int) -> int:
    r = result(0, f"{'处置完成' if not report['dry_run'] else 'dry-run 预检'}"
                  f"：发现更新器组件 {n_comp} 个，证据 {ev}",
               evidence=str(ev), actions=report["actions"],
               dry_run=report["dry_run"])
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
