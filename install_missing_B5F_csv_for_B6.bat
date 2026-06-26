@echo off
setlocal

cd /d "%~dp0"

set DEST=store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit
set SRC=phase2_B5F_by_run.csv

if not exist "%SRC%" (
    echo [ERR] %SRC% not found next to this BAT file.
    echo Put phase2_B5F_by_run.csv in the EntryGuidance-master root folder and run again.
    pause
    exit /b 1
)

mkdir "%DEST%" 2>nul
copy /Y "%SRC%" "%DEST%\phase2_B5F_by_run.csv"

echo [OK] Copied:
echo   %SRC%
echo to:
echo   %DEST%\phase2_B5F_by_run.csv
echo.
echo Now rerun:
echo   python phase2_B6_bounded_universality_report.py --config phase2_B6_campaign_summary_config.json
echo.
pause
endlocal
