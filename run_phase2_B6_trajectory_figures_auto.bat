@echo off
setlocal

cd /d "%~dp0"

chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo B6 Trajectory Figures Package
echo Auto-detect representative trajectory CSVs
echo Post-processing only: no simulation, no guidance modification
echo ============================================================

python phase2_B6_trajectory_figures.py

echo.
echo ============================================================
echo B6 trajectory figures finished.
echo Output folder:
echo store\data_saved\phase2_B6_trajectory_figures
echo ============================================================

pause
endlocal
