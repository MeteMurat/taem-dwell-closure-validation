PHASE 2 / B5C-F — LOCAL-ENVELOPE FAILURE DIAGNOSIS

Purpose:
Diagnose residual failures in the independent local-envelope Monte Carlo validation (B5C).
This script does not run new simulations. It reads B5C by-vehicle and by-case reports.

Default inputs:
  store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_vehicle_all.csv
  store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_case_all.csv

Run:
  cd C:\Users\PC\Desktop\EntryGuidance-master
  chcp 65001
  set PYTHONUTF8=1
  set PYTHONIOENCODING=utf-8
  python .\phase2_B5C_failure_diagnosis.py

Main output:
  store\data_saved\phase2_B5C_failure_diagnosis_report\b5c_failure_diagnosis_summary.txt

Interpretation:
B5C is not a broad U4 universality test. It is an independent validation of a narrow U3-local envelope.
If residual failures are close-pass/range-closure dominated, the next technical step should be range-closure recovery before broad Monte Carlo.
