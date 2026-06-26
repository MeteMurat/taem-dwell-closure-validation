@echo off
setlocal

cd /d "%~dp0"

chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo B6 Figure Polish Package v3
echo Post-processing only: no simulation, no guidance modification
echo ============================================================

python phase2_B6_figure_polish_package.py

echo.
echo ============================================================
echo B6 Figure Polish finished.
echo Output folder:
echo store\data_saved\phase2_B6_publication_figures_polished
echo ============================================================

pause
endlocal
