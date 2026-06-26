@echo off
setlocal

cd /d C:\Users\PC\Desktop\EntryGuidance-master

echo ============================================================
echo Phase 2 - B5E mis0 corner bounded diagnostic
echo Exact-single sequential campaign with generated MAXITER bound
echo ============================================================

python phase2_B5E_mis0_corner_orchestrator_bounded.py --spec phase2_B5E_mis0_corner_spec_bounded.json --generated-maxiter 30000 --timeout-sec 600 --progress-interval-sec 30

echo.
echo ============================================================
echo B5E bounded diagnostic finished.
echo Main report:
echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\phase2_B5E_by_run.csv
echo.
echo Best candidates:
echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\phase2_B5E_best_candidates.csv
echo ============================================================

pause
endlocal
