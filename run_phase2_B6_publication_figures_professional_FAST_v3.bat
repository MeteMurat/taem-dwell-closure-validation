@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo B6 publication figures - professional FAST v3
echo Post-processing only: no simulation, no guidance modification
echo ============================================================

python .\phase2_B6_make_publication_figures.py

pause
endlocal
