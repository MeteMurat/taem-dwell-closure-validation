@echo off
setlocal
cd /d C:\Users\PC\Desktop\EntryGuidance-master

echo ============================================================
echo Phase 2 - B5F mis0 reachability/pathspec audit FULL
echo 4 exact-single diagnostic cases, no broad sweep
echo ============================================================

python phase2_B5F_mis0_reachability_orchestrator.py --spec phase2_B5F_mis0_reachability_spec.json --progress-interval-sec 60

echo.
echo Main report:
echo store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit\phase2_B5F_by_run.csv
echo.
echo Best candidates:
echo store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit\phase2_B5F_best_candidates.csv
echo ============================================================
pause
endlocal
