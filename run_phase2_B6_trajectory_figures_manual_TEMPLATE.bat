@echo off
setlocal

cd /d "%~dp0"

chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo B6 Trajectory Figures Package - manual CSV mode
echo Edit SUCCESS_CSV and FAILURE_CSV below before running.
echo ============================================================

REM Edit these paths if auto-detection is not sufficient.
set SUCCESS_CSV=store\data_saved\PUT_SUCCESS_TRAJECTORY_CSV_HERE.csv
set FAILURE_CSV=store\data_saved\PUT_FAILURE_TRAJECTORY_CSV_HERE.csv

python phase2_B6_trajectory_figures.py --success-csv "%SUCCESS_CSV%" --failure-csv "%FAILURE_CSV%" --no-recursive-search

echo.
echo ============================================================
echo B6 trajectory figures finished.
echo Output folder:
echo store\data_saved\phase2_B6_trajectory_figures
echo ============================================================

pause
endlocal
