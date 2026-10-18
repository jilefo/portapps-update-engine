@echo off
rem ==========================================================================
rem  _卸载.bat -- 清理腾讯会议便携版在宿主系统留下的痕迹
rem ==========================================================================
rem  便携包本身不需要卸载（直接删目录即可），本脚本只做一件事：
rem  清理 WeMeet 通过 SHGetFolderPath 绕过后仍写入宿主 AppData 的部分。
rem
rem  背景（实测结论）：
rem    launcher.ini 的 [Environment] 有效，Data\settings\Temp\Tencent
rem    会被创建；但 WeMeet 的子进程会重新初始化 Shell，CEF 缓存仍写
rem    %APPDATA%\Tencent\Marvis。Custom.nsh 已把这些路径记到
rem    Data\settings\leak_paths.txt，本脚本据此清理。
rem
rem  用法：右键 -> 以管理员身份运行
rem ==========================================================================
setlocal EnableExtensions EnableDelayedExpansion
chcp 936 >nul

set "PKG_DIR=%~dp0"
set "LEAK_FILE=%PKG_DIR%Data\settings\leak_paths.txt"

echo ==============================================================
echo  腾讯会议便携版 - 宿主痕迹清理
echo ==============================================================
echo.

rem --- 1. 先结束残留进程，否则文件被占用删不掉 ---
echo [1/4] 结束残留进程...
for %%P in (WeMeetApp WeMeetCrashHandler WMExternal XnnExternal WeMeetPortable) do (
    taskkill /F /IM %%P.exe >nul 2>&1
    if not errorlevel 1 echo       已结束 %%P.exe
)
echo.

rem --- 2. 清理运行时锁，否则下次启动会弹「上次异常退出」---
echo [2/4] 清理运行时锁...
del /F /Q "%PKG_DIR%Data\PortableApps.comLauncherRuntimeData-WeMeetPortable.ini" >nul 2>&1
echo       完成
echo.

rem --- 3. 清理宿主泄漏目录 ---
echo [3/4] 清理宿主 AppData 残留...
if exist "%LEAK_FILE%" (
    for /f "usebackq tokens=*" %%L in ("%LEAK_FILE%") do (
        set "T=%%L"
        set "T=!T:%%APPDATA%%=%APPDATA%!"
        set "T=!T:%%LOCALAPPDATA%%=%LOCALAPPDATA%!"
        if exist "!T!" (
            rd /S /Q "!T!" >nul 2>&1
            if not exist "!T!" (
                echo       已清理 !T!
            ) else (
                echo       [被占用] !T!
            )
        )
    )
) else (
    echo       未找到 leak_paths.txt，按默认路径尝试
    for %%D in (
        "%APPDATA%\Tencent\WeMeet"
        "%APPDATA%\Tencent\Marvis"
        "%APPDATA%\Tencent\BeaconConfig"
        "%APPDATA%\Tencent\DtConfig"
        "%LOCALAPPDATA%\Tencent"
    ) do (
        if exist "%%~D" (
            rd /S /Q "%%~D" >nul 2>&1
            if not exist "%%~D" (echo       已清理 %%~D) else (echo       [被占用] %%~D)
        )
    )
)
echo.

rem --- 4. 清理注册表 ---
echo [4/4] 清理注册表...
for %%K in (
    "HKCU\Software\Tencent\WeMeet"
    "HKLM\SOFTWARE\Tencent\WeMeet"
    "HKLM\SOFTWARE\WOW6432Node\Tencent\WeMeet"
) do (
    reg delete %%K /f >nul 2>&1
    if not exist %%K echo       已清理 %%K
)
echo       完成
echo.

echo ==============================================================
echo  完成。便携包目录可直接删除，不会残留任何东西。
echo ==============================================================
pause
endlocal