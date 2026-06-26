PHASE 2 / B5C — INDEPENDENT LOCAL-ENVELOPE MONTE CARLO VALIDATION

Purpose
-------
B5B conservative Monte Carlo showed close-pass/range-closure fragility, and B5B-E
identified a narrow candidate local envelope from that sample:
  h_delta_m   = [0, +500]
  v_delta_mps = [-20, +10]
  heading spread = [-2, 0, +2] deg

B5C validates that candidate with a new random seed and fresh exact-single
role-distinct runs. This is a local U3 validation test, not a U4 universality claim.

Default campaign
----------------
N = 30 Monte Carlo cases, seed = 101
Each case runs mis0, mis1, mis2 via the exact-single B5A/B5AR orchestration.
Total = 30 × 3 = 90 exact-single runs.

Run
---
cd C:\Users\PC\Desktop\EntryGuidance-master
chcp 65001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
python .\phase2_B5C_local_envelope_validation.py --n 30 --seed 101

Or:
.\run_phase2_B5C_LOCAL_ENVELOPE.bat

Main outputs
------------
store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_summary.txt
store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_summary.json
store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_vehicle_all.csv
store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_case_all.csv
store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_case_summary.csv
store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_vehicle_role_summary.csv

Decision interpretation
-----------------------
B5C_LOCAL_ENVELOPE_VALIDATED_PASS_ALL:
  Strong local U3 support inside the tested local envelope.

B5C_LOCAL_ENVELOPE_SUPPORTED:
  Local U3 support, but not all cases passed.

B5C_LOCAL_ENVELOPE_PARTIAL_SUPPORT:
  Some support, but still fragile.

B5C_LOCAL_ENVELOPE_FRAGILE:
  The envelope extracted in B5B-E was sample-specific or insufficiently robust.
  Range-closure recovery is recommended before further universality claims.
