@echo off
setlocal
cd /d "%~dp0"

REM ------------------------------------------------------------
REM Replace the two paths below before running this BAT.
REM Success CSV must come from a B5D/tight-local-envelope run.
REM Failure CSV should come from a real B5E or B5F trajectory CSV.
REM ------------------------------------------------------------

set SUCCESS_CSV=store\data_saved\phase2_B5D_tight_local_envelope_validation\REPLACE_WITH_SUCCESS.csv
set FAILURE_CSV=store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit\REPLACE_WITH_FAILURE.csv

echo ============================================================
echo B6 Trajectory Figures Package v2 - manual mode
echo Post-processing only: no simulation, no guidance modification
echo ============================================================
python .\phase2_B6_trajectory_figures.py --success-csv "%SUCCESS_CSV%" --failure-csv "%FAILURE_CSV%"
if errorlevel 1 (
  echo.
  echo [ERROR] Manual figure generation failed.
)
echo.
echo Output folder:
echo store\data_saved\phase2_B6_trajectory_figures_v2
pause
