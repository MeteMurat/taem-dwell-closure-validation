PHASE 2 / B2 — EXACT-SINGLE SEQUENTIAL ORCHESTRATION
====================================================

Purpose
-------
B1E proved that the reliable path is exact-single orchestration, not the
simultaneous MultiMissileSim adapter path. B2 therefore runs mis0, mis1, and
mis2 sequentially through the exact V8.2 single runner, adds mis_id to each CSV,
combines the trajectories, and applies the existing TAEM event checker per
vehicle.

This is a classification step, not a tuning step.

Files
-----
1) multiset_phase2_B2_exact_single_role_specs.py
   - Copy-to-multiset source for B2.
   - Uses the frozen V8.2 success CSV to recover common init/target/end state.
   - Assigns recovered role-specific PathSpecs:
     mis0: fixed-left / anchor role
     mis1: validated V8.2 B1E pass role
     mis2: merged-winner case2 role

2) phase2_B2_exact_single_orchestrator.py
   - Runs exact single runner sequentially for mis0/mis1/mis2.
   - Produces one per-vehicle scaffold CSV and one combined CSV.
   - Runs phase2_B1_mis1_transfer_check.py separately for each mis_id.
   - Writes phase2_B2_by_vehicle.csv and phase2_B2_summary.txt/json.

3) run_phase2_B2_EXACT_SINGLE_ORCHESTRATOR.bat
   - Windows one-click runner with UTF-8 environment.

Required existing project files
-------------------------------
- single_mis1_main_v8_2_final_success_flags.py
- guidance/multiMissileGuideInstance_mis1_state_first_v8_2_final_success_flags.py
- phase2_B1_mis1_transfer_check.py
- store/data_saved/V8_2_BASELINE_FREEZE/mis1_state_first_v8_2_final_success_flags.csv

How to run
----------
PowerShell:

cd C:\Users\PC\Desktop\EntryGuidance-master
.\run_phase2_B2_EXACT_SINGLE_ORCHESTRATOR.bat

or manually:

chcp 65001
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
python .\phase2_B2_exact_single_orchestrator.py

Main outputs
------------
- store/data_saved/phase2_B2_exact_single_combined.csv
- store/data_saved/phase2_B2_exact_single_report/phase2_B2_by_vehicle.csv
- store/data_saved/phase2_B2_exact_single_report/phase2_B2_summary.txt
- store/data_saved/phase2_B2_exact_single_report/phase2_B2_summary.json
- store/data_saved/phase2_B2_exact_single_report/mis0/phase2_B1_decision.txt
- store/data_saved/phase2_B2_exact_single_report/mis1/phase2_B1_decision.txt
- store/data_saved/phase2_B2_exact_single_report/mis2/phase2_B1_decision.txt

Expected interpretation
-----------------------
- mis1 should remain PASS_STRICT; this is the B1E control case.
- mis0/mis2 should be classified before any tuning.
- If 2/3 or 3/3 pass, proceed to B3 campaign packaging.
- If only mis1 passes, inspect failure labels and recover role-specific PathSpecs
  before tuning.
