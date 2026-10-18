# -*- coding: utf-8 -*-
"""collect_meta.py —— 采集 39 个项目的 appinfo.ini 元数据，供脚手架生成使用

注意：部分项目的 appinfo.ini / launcher ini 为 UTF-16LE 带 BOM（0xFF 0xFE），
configparser 的 utf-8-sig 无法解码，故此处按 BOM 逐级回退探测编码。
"""
import configparser
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"<旧工作区>/"

PROJECTS = [
    "AiPyProPortable", "BaiduNetdiskPortable", "CherryStudioPortable",
    "CodeArtsAgentPortable", "CodeArtsPortable", "CodeBuddyCNPortable",
    "ComatePortable", "CursorPortable", "eDiaryPortable", "FeishuPortable",
    "FSCapturePortable", "JoplinPortable", "JoyCodePortable",
    "LobsterAIPortable", "MiaoshouPortable", "MiniMaxCodePortable",
    "OfficeAcePortable", "QoderCNIDEPortable", "QoderCNPortable",
    "QQNTPortable", "QQPortable", "QuarkCloudDrivePortable", "ReNamerPortable",
    "SoloMDPortable", "TIMPortable", "TodayCNPortable", "TraeCNPortable",
    "TyporaPortable", "WeixinPortable", "WeMeetPortable", "WinClawPortable",
    "WorkBuddyPortable", "WXWorkPortable", "ZenBrowserPortable", "ZoomPortable",
    "FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable",
    "KukuAIPortable",
]

ENCODINGS = ("utf-8-sig", "utf-16", "utf-8", "gb18030", "cp1252", "latin-1")


def read_text(path):
    """按 BOM 与常见编码逐级回退读取，返回 (文本, 编码名)。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1(replace)"


def parse_ini(path):
    """解析 ini，返回 (dict, 编码, 错误)。键形如 'Section.Key'。"""
    text, enc = read_text(path)
    out = {}
    try:
        cp = configparser.ConfigParser(strict=False, allow_no_value=True,
                                      delimiters=("=",), interpolation=None)
        cp.optionxform = str
        cp.read_string(text)
        for sec in cp.sections():
            for k, v in cp.items(sec):
                out[f"{sec}.{k}"] = v if v is not None else ""
    except configparser.Error as e:
        return out, enc, str(e)
    return out, enc, None


def main():
    out = {}
    for name in PROJECTS:
        root = os.path.join(SRC, name)
        rec = {"name": name}
        ai = os.path.join(root, "portableapps", "App", "AppInfo", "appinfo.ini")
        if os.path.isfile(ai):
            vals, enc, err = parse_ini(ai)
            rec.update(vals)
            rec["__appinfo_encoding__"] = enc
            if err:
                rec["__appinfo_parse_error__"] = err
        else:
            rec["__no_appinfo__"] = True

        for cand in (
            os.path.join(root, "portableapps", "App", "AppInfo", "launcher.ini"),
            os.path.join(root, "portableapps", "App", "AppInfo", "Launcher",
                         name + ".ini"),
        ):
            if os.path.isfile(cand):
                vals, enc, err = parse_ini(cand)
                for k, v in vals.items():
                    rec.setdefault("L:" + k, v)
                rec["__launcher_path__"] = os.path.relpath(cand, root).replace("\\", "/")
                rec["__launcher_encoding__"] = enc
                if err:
                    rec["__launcher_parse_error__"] = err
                break

        appd = os.path.join(root, "portableapps", "App")
        if os.path.isdir(appd):
            rec["__app_subdirs__"] = [
                d for d in sorted(os.listdir(appd))
                if os.path.isdir(os.path.join(appd, d)) and d != "AppInfo"
            ]
        pe = rec.get("L:Launch.ProgramExecutable", "")
        rec["__entry_exe__"] = pe
        rec["__app_subdir__"] = pe.split("\\")[0] if "\\" in pe else ""
        rec["__workdir__"] = rec.get("L:Launch.WorkingDirectory", "")
        rec["__args__"] = rec.get("L:Launch.CommandLineArguments", "")
        rec["__env__"] = {k[len("L:Environment."):]: v for k, v in rec.items()
                          if k.startswith("L:Environment.")}
        out[name] = rec

    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()