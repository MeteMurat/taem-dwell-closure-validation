PHASE 2 / B3A — Heading-Spread Sensitivity
===========================================

Purpose
-------
B2R produced the first valid role-distinct exact-single multi-vehicle transfer:
mis0=-2 deg, mis1=0 deg, mis2=+2 deg, all PASS_STRICT. B3A tests whether
this role-distinct TAEM success is retained under a bounded family of heading
spreads.

Default spreads
---------------
[-1, 0, +1] deg
[-2, 0, +2] deg
[-3, 0, +3] deg
[-4, 0, +4] deg

Files
-----
multiset_phase2_B3A_heading_spread_specs.py
phase2_B3A_heading_spread_orchestrator.py
run_phase2_B3A_HEADING_SPREAD.bat

Run
---
cd C:\Users\PC\Desktop\EntryGuidance-master
run_phase2_B3A_HEADING_SPREAD.bat

Manual run
----------
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python phase2_B3A_heading_spread_orchestrator.py

Custom spread list
------------------
python phase2_B3A_heading_spread_orchestrator.py --spreads 1 2 3 4 5

Main outputs
------------
store\data_saved\phase2_B3A_heading_spread_combined_all.csv
store\data_saved\phase2_B3A_heading_spread_report\phase2_B3A_summary.txt
store\data_saved\phase2_B3A_heading_spread_report\phase2_B3A_summary.json
store\data_saved\phase2_B3A_heading_spread_report\phase2_B3A_by_spread.csv
store\data_saved\phase2_B3A_heading_spread_report\phase2_B3A_by_vehicle_all.csv

Decision labels
---------------
B3A_PASS_ALL_SPREADS:
  All tested spreads produced 3/3 PASS_STRICT and role_distinct_ok=True.

B3A_PARTIAL_PASS:
  At least one spread passed, but not the full tested family.

B3A_FAIL_ALL_SPREADS:
  No tested spread achieved 3/3 role-distinct PASS_STRICT.
