@echo off
chcp 65001 >nul
:: 腾讯会议便携版 - 更新入口
:: 双击运行，按提示操作即可。逻辑在 App\AppInfo\Tools\update.ps1。
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0App\AppInfo\Tools\update.ps1" %*
pause
