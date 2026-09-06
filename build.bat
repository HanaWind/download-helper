@echo off
REM ============================================================
REM  Hana Download Helper 打包脚本（Windows）
REM  依赖：当前 venv 为 Python 3.11，并已 pip install pyinstaller
REM  用法：双击或在 venv 激活后执行 build.bat
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv，请先创建 Python 3.11 虚拟环境。
    pause
    exit /b 1
)

echo [1/2] 安装/更新 PyInstaller...
call .venv\Scripts\python.exe -m pip install -U pyinstaller

echo [2/2] 开始打包（onedir：小 exe + 同目录 dll）...
call .venv\Scripts\python.exe -m PyInstaller HanaDownloadHelper.spec --noconfirm --clean

echo.
if exist "dist\HanaDownloadHelper\HanaDownloadHelper.exe" (
    echo [完成] 可执行文件位于：dist\HanaDownloadHelper\HanaDownloadHelper.exe
    echo 请将整个 dist\HanaDownloadHelper 文件夹一起分发（exe 与 dll 需同目录）。
) else (
    echo [失败] 未发现产物，请查看上方报错。
)
pause
endlocal
