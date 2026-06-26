@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo B6 Trajectory Figures Package v2 - auto mode
echo Post-processing only: no simulation, no guidance modification
echo ============================================================
python .\phase2_B6_trajectory_figures.py
if errorlevel 1 (
  echo.
  echo [ERROR] Auto figure generation failed.
)
echo.
echo Output folder:
echo store\data_saved\phase2_B6_trajectory_figures_v2
pause
