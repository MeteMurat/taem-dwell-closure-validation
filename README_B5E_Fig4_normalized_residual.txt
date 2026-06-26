B5E FIGURE 4 NORMALIZED RESIDUAL — DOWNLOAD PACK
=================================================

Purpose
-------
This pack generates the corrected manuscript Figure 4:

  fig03_B5E_terminal_error_diagnostic_professional.pdf

The corrected figure uses normalized residuals:

  |e_h| / epsilon_h
  |e_v| / epsilon_v
  |e_s| / epsilon_s

with the strict manuscript TAEM tolerances:

  epsilon_h = 3000 m
  epsilon_v = 100 m/s
  epsilon_s = 20000 m

Files
-----
1) phase2_B5E_mis0_corner_orchestrator_bounded.py
   Runs the bounded B5E diagnostic campaign and generates run CSV files.

2) phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json
   Patched spec file with strict manuscript TAEM tolerances:
   h_tol_m = 3000, v_tol_mps = 100, s_go_tol_m = 20000.

3) make_fig03_B5E_normalized_residual_from_runs.py
   Reads phase2_B5E_by_run.csv and the referenced run CSVs, extracts terminal errors,
   normalizes them, and creates the corrected Fig. 4 PDF/PNG.

4) run_B5E_bounded_and_make_fig03.ps1
   One-command PowerShell runner.

How to use
----------
Copy all files in this folder into:

  C:\Users\PC\Desktop\EntryGuidance-master

Then run PowerShell:

  cd C:\Users\PC\Desktop\EntryGuidance-master
  .\run_B5E_bounded_and_make_fig03.ps1

Expected outputs
----------------
After successful execution, these files should exist:

  figs\fig03_B5E_terminal_error_diagnostic_professional.pdf
  figs\fig03_B5E_terminal_error_diagnostic_professional.png
  figs\b5e_normalized_terminal_residuals.csv
  figs\b5e_normalized_terminal_residuals_missing_cases.csv

LaTeX include line
------------------
Keep this line unchanged:

  \includegraphics[width=0.88\linewidth]{fig03_B5E_terminal_error_diagnostic_professional.pdf}

Use this caption:

  \captionof{figure}{B5E normalized terminal-residual diagnostic for unresolved corner-case candidates. Each component is normalized by the corresponding strict TAEM tolerance, so values above unity indicate violation of the strict closure box. The figure is used only to diagnose the unresolved boundary behavior and is not counted as positive robustness evidence.}

Important
---------
If the script reports "No usable terminal-error rows", it means the B5E run CSV files were not created.
In that case, inspect:

  store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\logs

and verify that the campaign generated files under:

  store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\runs
