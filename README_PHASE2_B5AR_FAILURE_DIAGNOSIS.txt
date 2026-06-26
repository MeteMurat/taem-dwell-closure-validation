PHASE 2 / B5A-R FAILURE DIAGNOSIS

Purpose:
Diagnose the positive-velocity boundary refinement output before Monte Carlo.

Inputs:
- By default, searches:
  store\data_saved\phase2_B5AR_positive_velocity_report\*by_vehicle*.csv

Outputs:
- store\data_saved\phase2_B5AR_failure_diagnosis_report\b5ar_failure_diagnosis_summary.txt
- b5ar_case_summary.csv
- b5ar_marginal_by_velocity.csv
- b5ar_marginal_by_height.csv
- b5ar_marginal_by_vehicle.csv
- b5ar_failed_rows.csv

Run:
  cd C:\Users\PC\Desktop\EntryGuidance-master
  chcp 65001
  set PYTHONUTF8=1
  set PYTHONIOENCODING=utf-8
  python phase2_B5AR_failure_diagnosis.py

Interpretation:
- This is not a new simulation.
- It classifies which positive-velocity/height/vehicle sectors fail.
- Use it to decide whether B5B Monte Carlo should be conservative or focused on the +velocity boundary.
