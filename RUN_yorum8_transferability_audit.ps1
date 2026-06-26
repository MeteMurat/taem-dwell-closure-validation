$ErrorActionPreference = "Stop"

# RUN_yorum8_transferability_audit.ps1
# Put this file and audit_transferability_interface.py into:
# D:\acta-paper\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master

$Repo = "D:\acta-paper\savunma-makale-adımlar\savunma makale-2.adım\EntryGuidance-master"
Set-Location -LiteralPath $Repo

Write-Host "[1] Syntax check..." -ForegroundColor Cyan
python -m py_compile .\audit_transferability_interface.py

Write-Host "[2] Running Reviewer 8 transferability audit..." -ForegroundColor Cyan
python .\audit_transferability_interface.py `
  --csv-glob ".\store\data_saved\phase2_B5D_tight_local_envelope_validation\combined\*.csv" `
  --outdir ".\outputs\YORUM8_transferability_audit" `
  --idcol mis_id `
  --tol-h 3000 `
  --tol-v 100 `
  --tol-sgo 20000 `
  --n-dwell 3

Write-Host "[DONE] Send these files back:" -ForegroundColor Green
Write-Host ".\outputs\YORUM8_transferability_audit\transferability_interface_summary.json"
Write-Host ".\outputs\YORUM8_transferability_audit\transferability_vehicle_audit.csv"
Write-Host ".\outputs\YORUM8_transferability_audit\transferability_case_audit.csv"
Write-Host ".\outputs\YORUM8_transferability_audit\TABLE_transferability_interface_audit.tex"
Write-Host ".\outputs\YORUM8_transferability_audit\INSERT_TransferabilityInterfaceSection.tex"
