@echo off
setlocal
cd /d C:\Users\PC\Desktop\EntryGuidance-master

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 > nul

echo ============================================================
echo Phase 2 - B5F mis0 reachability/pathspec audit SMOKE - UTF8 FIX
echo One long-propagation case only, MAXITER from spec
echo ============================================================

python phase2_B5F_mis0_reachability_orchestrator.py --spec phase2_B5F_mis0_reachability_spec.json --limit 1 --progress-interval-sec 60

echo.
echo Report:
echo store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit\phase2_B5F_by_run.csv
echo ============================================================
pause
endlocal
