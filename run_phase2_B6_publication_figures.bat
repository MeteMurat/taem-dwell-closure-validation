@echo off
setlocal

cd /d "%~dp0"

chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ============================================================
echo Phase 2 - B6 publication figures
echo Post-processing only: no simulation, no guidance modification
echo ============================================================

python phase2_B6_make_publication_figures.py

echo.
echo ============================================================
echo B6 figure generation finished.
echo Output folder:
echo store\data_saved\phase2_B6_publication_figures
echo.
echo Key outputs:
echo - fig01_phase2_success_rates.png/pdf
echo - fig02_failure_boundary_summary.png/pdf
echo - fig03_B5E_terminal_error_diagnostics.png/pdf
echo - fig04_B5F_range_closure_diagnostic.png/pdf
echo - fig05_representative_ground_track.png/pdf if trajectory CSV exists
echo - fig06_representative_3D_trajectory.html if trajectory CSV exists and Plotly is installed
echo - phase2_B6_figure_captions.txt
echo ============================================================

pause
endlocal
