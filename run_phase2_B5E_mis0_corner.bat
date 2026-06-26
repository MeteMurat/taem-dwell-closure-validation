@echo off
setlocal

cd /d C:\Users\PC\Desktop\EntryGuidance-master

echo ============================================================
echo Phase 2 - B5E mis0 corner robustness refinement
echo Exact-single sequential campaign
echo ============================================================

python phase2_B5E_mis0_corner_orchestrator.py --spec phase2_B5E_mis0_corner_spec.json

echo.
echo ============================================================
echo B5E finished.
echo Main report:
echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement\phase2_B5E_by_run.csv
echo.
echo Best candidates:
echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement\phase2_B5E_best_candidates.csv
echo ============================================================

pause
endlocal