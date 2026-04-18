@echo off
REM 打包新版 PyQt6 app（app/main.py）。
REM 输出目录: dist\污染计数器v1.2.0\

py -m PyInstaller --noconfirm --clean "污染计数器v1.2.spec"

echo.
echo ============================================
echo  打包完成。输出位置：
echo    dist\污染计数器v1.2.0\污染计数器v1.2.0.exe
echo ============================================
pause
