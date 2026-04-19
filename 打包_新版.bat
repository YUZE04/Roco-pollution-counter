@echo off
REM 打包脚本 - 显示详细信息

echo ============================================
echo 污染计数器 v1.2.3 打包开始
echo ============================================
echo.

setlocal enabledelayedexpansion

REM 检查 PyInstaller
py -m PyInstaller --version
if errorlevel 1 (
    echo 错误: PyInstaller 不可用
    pause
    exit /b 1
)

echo.
echo 开始打包...
echo.

REM 运行打包
py -m PyInstaller --noconfirm --clean "污染计数器v1.2.spec"

if errorlevel 1 (
    echo.
    echo ============================================
    echo 打包失败（错误代码: %errorlevel%）
    echo ============================================
    pause
    exit /b 1
) else (
    echo.
    echo ============================================
    echo 打包成功
    echo ============================================
    echo.
    echo 输出位置: dist\污染计数器v1.2.3\污染计数器v1.2.3.exe
    echo.
    pause
)
