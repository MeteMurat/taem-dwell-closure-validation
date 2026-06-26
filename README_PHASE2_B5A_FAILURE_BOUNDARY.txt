PHASE 2 / B5A-F FAILURE-BOUNDARY DIAGNOSIS

Diagnoses why B5A deterministic dispersion grid is only PARTIAL_PASS before Monte Carlo.

Input:
store\data_saved\phase2_B5A_dispersion_grid_report\phase2_B5A_by_vehicle_all.csv

Run:
cd C:\Users\PC\Desktop\EntryGuidance-master
python .\phase2_B5A_failure_boundary_diagnosis.py

Main output:
store\data_saved\phase2_B5A_failure_boundary_report\b5a_failure_boundary_summary.txt

Use:
If +50 m/s is confirmed as the fragile direction, run B5A-R positive-velocity boundary refinement before broad Monte Carlo.
