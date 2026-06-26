PHASE 2 / B5A-R POSITIVE-VELOCITY BOUNDARY REFINEMENT

Purpose:
Locate the positive initial velocity robustness boundary observed in B5A before broad Monte Carlo.

Default matrix:
- heading spread: [-2, 0, +2] deg
- height_delta_m: [-500, 0, +500]
- velocity_delta_mps: [+10, +20, +30, +40, +50]
- total runs: 15 cases x 3 vehicles = 45 exact-single role-distinct runs

Run:
cd C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python phase2_B5AR_positive_velocity_refinement.py

Outputs:
store\data_saved\phase2_B5AR_positive_velocity_report\phase2_B5AR_summary.txt
store\data_saved\phase2_B5AR_positive_velocity_report\phase2_B5AR_summary.json
store\data_saved\phase2_B5AR_positive_velocity_report\phase2_B5A_by_case.csv
store\data_saved\phase2_B5AR_positive_velocity_report\phase2_B5A_by_vehicle_all.csv
store\data_saved\phase2_B5AR_positive_velocity_combined_all.csv

Interpretation:
- B5AR_PASS_ALL_POSITIVE_V_GRID: positive-velocity boundary is above +50 m/s in this grid.
- B5AR_PARTIAL_PASS_POSITIVE_V_GRID: boundary lies inside +10..+50 m/s.
- B5AR_FAIL_POSITIVE_V_GRID: positive velocity is fragile even at +10 m/s.
