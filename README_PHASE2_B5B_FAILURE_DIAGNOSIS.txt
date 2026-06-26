PHASE 2 / B5B-F MONTE CARLO FAILURE DIAGNOSIS
================================================

Purpose
-------
Diagnose why the B5B conservative U3 Monte Carlo pilot was classified as fragile.
This package does not run new simulations. It only post-processes B5B outputs.

Default input files
-------------------
store\data_saved\phase2_B5B_mc_conservative_u3_report\phase2_B5B_mc_by_vehicle_all.csv
store\data_saved\phase2_B5B_mc_conservative_u3_report\phase2_B5B_mc_by_case_all.csv

Default output directory
------------------------
store\data_saved\phase2_B5B_failure_diagnosis_report

How to run
----------
cd C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B5B_failure_diagnosis.py

PowerShell equivalent
---------------------
cd C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
python .\phase2_B5B_failure_diagnosis.py

Main outputs
------------
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_failure_diagnosis_summary.txt
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_failure_rows.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_case_failure_summary.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_marginal_by_velocity_bin.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_marginal_by_height_bin.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_marginal_by_vehicle.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_failure_mode_counts.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_velocity_upper_threshold_candidates.csv
store\data_saved\phase2_B5B_failure_diagnosis_report\b5b_failure_diagnosis_for_manuscript.txt

Interpretation
--------------
The script identifies whether the B5B fragility is dominated by close-pass /
range-closure escape, and proposes whether the next step should be a narrower
validated local envelope or a range-closure recovery update before broader Monte
Carlo / U4 universality claims.
