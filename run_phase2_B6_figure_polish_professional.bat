@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ============================================================
echo B6 polished figures - professional labels
echo ============================================================
python .\phase2_B6_figure_polish_package.py
pause
endlocal
