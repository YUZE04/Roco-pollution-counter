@echo off
REM 打包新版 PyQt6 app（app/main.py）。
REM 输出目录: dist\污染计数器v1.2.2\

py -m PyInstaller --noconfirm --clean "污染计数器v1.2.spec"

echo.
echo ============================================
echo  打包完成。输出位置：
echo    dist\污染计数器v1.2.2\污染计数器v1.2.2.exe
echo ============================================
pause
