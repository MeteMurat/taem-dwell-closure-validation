@echo off
setlocal

cd /d C:\Users\PC\Desktop\EntryGuidance-master

echo ============================================================
echo Phase 2 - B5E bounded smoke test
echo One case only, generated MAXITER=5000
echo ============================================================

python phase2_B5E_mis0_corner_orchestrator_bounded.py --spec phase2_B5E_mis0_corner_spec_bounded.json --limit 1 --generated-maxiter 5000 --timeout-sec 300 --progress-interval-sec 30

pause
endlocal
