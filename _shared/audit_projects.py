#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Audit 39 portable projects against the dual-track release standard."""
import json
import os
import sys

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

NO_AUTO = {"FoxitPDFPortable", "SublimeTextPortable", "WPSOfficePortable"}

BASE_REQUIRED = [
    ".editorconfig", ".gitattributes", ".gitignore",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/workflows/ci.yml",
    "LICENSE", "README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
    "SECURITY.md", "CHANGELOG.md", "SUPPORT.md", "THIRD_PARTY_NOTICES.md",
    "docs/PORTABLE.md", "docs/BUILD.md", "docs/RELEASE.md",
    "portableapps/help.html",
    "portableapps/App/AppInfo/appinfo.ini",
    "portableapps/App/AppInfo/installer.ini",
    "portableapps/App/AppInfo/appicon.ico",
    "portableapps/App/AppInfo/appicon_16.png",
    "portableapps/App/AppInfo/appicon_32.png",
    "portableapps/App/AppInfo/appicon_128.png",
    "portableapps/Other/Source",
    "portableapps/Other/Help",
    "scripts/build-portable.ps1",
    "tests",
]
AUTO_REQUIRED = [
    ".github/workflows/release.yml",
    ".github/workflows/portableapps.yml",
    "scripts/package-paf.ps1",
]
# launcher.ini may live at App/AppInfo/launcher.ini or App/AppInfo/Launcher/<AppID>.ini
LAUNCHER_ALT = "portableapps/App/AppInfo/Launcher/{}.ini"


def dir_size(p):
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def has_launcher(root, name):
    cands = [
        os.path.join(root, "portableapps", "App", "AppInfo", "launcher.ini"),
        os.path.join(root, "portableapps", "App", "AppInfo", "Launcher", name + ".ini"),
    ]
    return any(os.path.isfile(c) for c in cands)


def main():
    rows = []
    for name in PROJECTS:
        root = os.path.join(SRC, name)
        if not os.path.isdir(root):
            rows.append({"name": name, "exists": False, "missing": ["<DIR MISSING>"]})
            continue
        missing = []
        req = list(BASE_REQUIRED) + ([] if name in NO_AUTO else list(AUTO_REQUIRED))
        for rel in req:
            if not os.path.exists(os.path.join(root, rel.replace("/", os.sep))):
                missing.append(rel)
        if not has_launcher(root, name):
            missing.append("portableapps/App/AppInfo/launcher.ini")
        if not os.path.isdir(os.path.join(root, "portableapps", "App", "App", "x")):
            # check there is an App/<AppName>/ payload dir
            appdir = os.path.join(root, "portableapps", "App")
            subs = [d for d in os.listdir(appdir)
                    if os.path.isdir(os.path.join(appdir, d)) and d != "AppInfo"] \
                if os.path.isdir(appdir) else []
            if not subs:
                missing.append("portableapps/App/<AppName>/")
        if not os.path.isdir(os.path.join(root, "src")):
            missing.append("src/")
        if not os.path.isdir(os.path.join(root, "dist")):
            missing.append("dist/")
        size = dir_size(root)
        rows.append({
            "name": name, "exists": True, "missing": missing,
            "size_mb": round(size / 1048576, 1), "no_auto": name in NO_AUTO,
        })

    out = {"root": SRC, "projects": rows,
           "total": len(rows),
           "missing_dirs": [r["name"] for r in rows if not r["exists"]]}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()