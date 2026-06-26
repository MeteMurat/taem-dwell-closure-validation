# Phase 2 / B1 runner: same-target multi-vehicle transfer check
# Run from: C:\Users\PC\Desktop\EntryGuidance-master

$ErrorActionPreference = "Stop"

Write-Host "[B1] Backing up current multiset.py ..."
if (Test-Path .\multiset.py) {
    Copy-Item .\multiset.py .\multiset_BACKUP_before_phase2_B1.py -Force
}

Write-Host "[B1] Installing Phase 2 B1 multiset ..."
Copy-Item .\multiset_phase2_B1_same_target_mis1_transfer.py .\multiset.py -Force

Write-Host "[B1] Running multi_main.py ..."
python .\multi_main.py

Write-Host "[B1] Running B1 decision checker ..."
python .\phase2_B1_mis1_transfer_check.py `
    --csv .\store\data_saved\phase2_B1_same_target_multi_mis1_transfer.csv `
    --outdir .\store\data_saved\phase2_B1_report `
    --target-mis-id 1 `
    --tol-h 3000 `
    --tol-v 150 `
    --tol-sgo 30000

Write-Host "[B1] Running plot bundle ..."
python .\plot_csv_report.py `
    --input .\store\data_saved\phase2_B1_same_target_multi_mis1_transfer.csv `
    --outdir .\store\data_saved\phase2_B1_report\plots `
    --downsample 10 `
    --idcol mis_id `
    --xcol global_t

Write-Host "[B1] Running TAEM compare ..."
python .\taem_compare_runs.py `
    --inputs .\store\data_saved\phase2_B1_same_target_multi_mis1_transfer.csv `
    --outdir .\store\data_saved\phase2_B1_report\compare `
    --idcol mis_id `
    --tol_h 3000 `
    --tol_v 150 `
    --tol_sgo 30000

Write-Host "[B1] Done. Open: .\store\data_saved\phase2_B1_report\phase2_B1_decision.txt"
