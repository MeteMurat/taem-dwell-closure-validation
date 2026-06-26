@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo B6 trajectory figures - professional FAST v3
echo No broad recursive trajectory scan unless explicitly requested
echo ============================================================

python .\phase2_B6_trajectory_figures.py

pause
endlocal
