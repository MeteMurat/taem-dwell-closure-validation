@echo off
setlocal EnableExtensions

REM ============================================================
REM B5E Fig.4 normalized residual workflow
REM Run this .bat from the EntryGuidance-master folder.
REM It does NOT require PowerShell script execution permission.
REM ============================================================

cd /d "%~dp0"

echo.
echo === Current folder ===
cd
echo.

echo === Checking required files ===
if not exist "phase2_B5E_mis0_corner_orchestrator_bounded.py" (
  echo [ERROR] Missing phase2_B5E_mis0_corner_orchestrator_bounded.py
  pause
  exit /b 1
)
if not exist "phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json" (
  echo [ERROR] Missing phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json
  pause
  exit /b 1
)
if not exist "make_fig03_B5E_normalized_residual_from_runs.py" (
  echo [ERROR] Missing make_fig03_B5E_normalized_residual_from_runs.py
  pause
  exit /b 1
)

echo.
echo === B5E smoke test: first 2 cases ===
python "phase2_B5E_mis0_corner_orchestrator_bounded.py" ^
  --spec "phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json" ^
  --limit 2 ^
  --generated-maxiter 5000 ^
  --timeout-sec 600 ^
  --progress-interval-sec 30

if errorlevel 1 (
  echo.
  echo [ERROR] Smoke test failed. Check logs under:
  echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\logs
  pause
  exit /b 1
)

echo.
echo === B5E full bounded diagnostic campaign ===
python "phase2_B5E_mis0_corner_orchestrator_bounded.py" ^
  --spec "phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json" ^
  --generated-maxiter 30000 ^
  --timeout-sec 600 ^
  --progress-interval-sec 30

if errorlevel 1 (
  echo.
  echo [ERROR] Full B5E campaign failed. Check logs under:
  echo store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\logs
  pause
  exit /b 1
)

echo.
echo === Generate normalized Fig. 4 ===
python "make_fig03_B5E_normalized_residual_from_runs.py" ^
  --input "store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\phase2_B5E_by_run.csv" ^
  --outdir "figs" ^
  --outname "fig03_B5E_terminal_error_diagnostic_professional" ^
  --eps_h 3000 ^
  --eps_v 100 ^
  --eps_s 20000

if errorlevel 1 (
  echo.
  echo [ERROR] Figure generation failed.
  echo Check:
  echo figs\b5e_normalized_terminal_residuals_missing_cases.csv
  pause
  exit /b 1
)

echo.
echo === DONE ===
echo Expected outputs:
echo figs\fig03_B5E_terminal_error_diagnostic_professional.pdf
echo figs\fig03_B5E_terminal_error_diagnostic_professional.png
echo figs\b5e_normalized_terminal_residuals.csv
echo.
pause
endlocal
