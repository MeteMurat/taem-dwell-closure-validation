@echo off
setlocal

cd /d C:\Users\PC\Desktop\EntryGuidance-master

echo ============================================================
echo Phase 2 - B5E mis0 corner rescue soft-first refinement
echo Exact-single sequential campaign, C00 baseline removed
echo ============================================================

echo First run a 1-case smoke test manually if not already done:
echo python .\phase2_B5E_mis0_corner_orchestrator.py --spec .\phase2_B5E_mis0_corner_spec_rescue.json --limit 1 --timeout-sec 600
echo.

python .\phase2_B5E_mis0_corner_orchestrator.py --spec .\phase2_B5E_mis0_corner_spec_rescue.json --timeout-sec 600

echo.
echo ============================================================
echo B5E rescue finished.
echo Main report:
echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_rescue_soft_first\phase2_B5E_by_run.csv
echo.
echo Best candidates:
echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_rescue_soft_first\phase2_B5E_best_candidates.csv
echo ============================================================

pause
endlocal
