PHASE 2 / B5A — DETERMINISTIC DISPERSION GRID

Purpose
-------
This package keeps the universality claim alive by moving from B3A/B3C local
sensitivity to a deterministic U3 robustness grid. It does not claim full
universality. It tests whether the validated role-distinct exact-single protocol
survives common initial height and velocity perturbations at the B2R heading
spread [-2, 0, +2] deg.

Default grid
------------
height_delta_m      = [-500, 0, +500]
velocity_delta_mps  = [-50, 0, +50]
heading_spread_deg  = 2
vehicles            = mis0, mis1, mis2
Total exact-single runs = 9 cases x 3 vehicles = 27 runs.

Run
---
cd C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B5A_dispersion_grid_orchestrator.py

PowerShell environment equivalent:
$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"
python .\phase2_B5A_dispersion_grid_orchestrator.py

Main outputs
------------
store\data_saved\phase2_B5A_dispersion_grid_report\phase2_B5A_summary.txt
store\data_saved\phase2_B5A_dispersion_grid_report\phase2_B5A_summary.json
store\data_saved\phase2_B5A_dispersion_grid_report\phase2_B5A_by_case.csv
store\data_saved\phase2_B5A_dispersion_grid_report\phase2_B5A_by_vehicle_all.csv
store\data_saved\phase2_B5A_dispersion_grid_combined_all.csv

Interpretation
--------------
B5A_PASS_ALL_GRID:
  The tested deterministic height/velocity grid retains 3/3 role-distinct TAEM
  success in every case. This supports a local U3 robustness claim and justifies
  the next step: Monte Carlo.

B5A_PARTIAL_PASS:
  Some deterministic perturbation cases pass and some fail. This identifies the
  deterministic robustness boundary; do not proceed to broad universality without
  analyzing failure modes.

B5A_FAIL_ALL_GRID:
  The role-distinct transfer is not robust to this deterministic grid.

Caution
-------
B5A is still not U4 universality. It is a deterministic U3 pre-Monte-Carlo step.
Full universality still needs broader dispersion dimensions and statistical
reporting, e.g. Monte Carlo with confidence intervals.
