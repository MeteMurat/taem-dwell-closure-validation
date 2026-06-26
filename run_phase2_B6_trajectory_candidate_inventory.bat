@echo off
setlocal

cd /d "%~dp0"

chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo B6 Trajectory Candidate Inventory
echo This creates trajectory_candidate_inventory.csv.
echo ============================================================

python phase2_B6_trajectory_figures.py --outdir store\data_saved\phase2_B6_trajectory_figures_inventory

echo.
echo Candidate inventory:
echo store\data_saved\phase2_B6_trajectory_figures_inventory\trajectory_candidate_inventory.csv
echo ============================================================

pause
endlocal
