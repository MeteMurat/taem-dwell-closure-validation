@echo off
setlocal

cd /d C:\Users\PC\Desktop\EntryGuidance-master

chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo Phase 2 - B6 bounded universality evidence pack
echo Post-processing only: no simulation, no guidance modification
echo ============================================================

python phase2_B6_bounded_universality_report.py --config phase2_B6_campaign_summary_config.json

echo.
echo ============================================================
echo B6 finished.
echo Output folder:
echo store\data_saved\phase2_B6_bounded_universality_evidence_pack
echo.
echo Key files:
echo - phase2_B6_campaign_summary.csv
echo - phase2_B6_campaign_summary.md
echo - phase2_B6_bounded_universality_claim.txt
echo - phase2_B6_failure_boundary_notes.txt
echo - phase2_B6_manuscript_ready_block.md
echo ============================================================

pause
endlocal
