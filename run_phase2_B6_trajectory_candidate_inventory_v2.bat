@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo B6 Trajectory Figures Package v2 - inventory only
echo Post-processing only: no simulation, no guidance modification
echo ============================================================
python .\phase2_B6_trajectory_figures.py --inventory-only
if errorlevel 1 (
  echo.
  echo [ERROR] Inventory command failed.
)
echo.
echo Output folder:
echo store\data_saved\phase2_B6_trajectory_figures_v2
pause
