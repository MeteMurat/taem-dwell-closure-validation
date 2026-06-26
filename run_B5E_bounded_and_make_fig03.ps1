# B5E Fig. 4 normalized residual workflow
# Run this from: C:\Users\PC\Desktop\EntryGuidance-master

Set-Location "C:\Users\PC\Desktop\EntryGuidance-master"

Write-Host "=== B5E smoke test: first 2 cases ==="
python .\phase2_B5E_mis0_corner_orchestrator_bounded.py `
  --spec .\phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json `
  --limit 2 `
  --generated-maxiter 5000 `
  --timeout-sec 600 `
  --progress-interval-sec 30

Write-Host "=== B5E full bounded diagnostic campaign ==="
python .\phase2_B5E_mis0_corner_orchestrator_bounded.py `
  --spec .\phase2_B5E_mis0_corner_spec_bounded_STRICT_TAEM.json `
  --generated-maxiter 30000 `
  --timeout-sec 600 `
  --progress-interval-sec 30

Write-Host "=== Generate normalized Fig. 4 ==="
python .\make_fig03_B5E_normalized_residual_from_runs.py `
  --input ".\store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\phase2_B5E_by_run.csv" `
  --outdir ".\figs" `
  --outname "fig03_B5E_terminal_error_diagnostic_professional" `
  --eps_h 3000 `
  --eps_v 100 `
  --eps_s 20000

Write-Host "=== DONE ==="
Write-Host "Expected figure:"
Write-Host ".\figs\fig03_B5E_terminal_error_diagnostic_professional.pdf"
