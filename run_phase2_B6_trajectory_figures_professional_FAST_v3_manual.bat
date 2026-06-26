@echo off
setlocal
cd /d "%~dp0"
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Edit this path only if the auto known B5D success CSV cannot be found.
set SUCCESS_CSV=store\data_saved\phase2_B5D_tight_local_envelope_validation\case_reports\b5c000_hp173p144_vm1p127\phase2_B5A_hp173p144m_vm1p12688mps_sp2deg_combined.csv

echo ============================================================
echo B6 trajectory figures - professional FAST v3 MANUAL
echo Post-processing only: no simulation, no guidance modification
echo ============================================================

python .\phase2_B6_trajectory_figures.py --success-csv "%SUCCESS_CSV%"

pause
endlocal
