# Phase 2 B6 — Bounded Universality Evidence Pack

This package is post-processing only. It does not run simulation and does not edit guidance or multiset files.

## Files

- `phase2_B6_bounded_universality_report.py`
- `phase2_B6_campaign_summary_config.json`
- `run_phase2_B6_bounded_universality_report.bat`

## Run

Copy all three files into:

```text
C:\Users\PC\Desktop\EntryGuidance-master
```

Then run:

```powershell
cd C:\Users\PC\Desktop\EntryGuidance-master
.\run_phase2_B6_bounded_universality_report.bat
```

## Expected inputs

The script searches for:

```text
store\data_saved\phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic\phase2_B5E_by_run.csv
store\data_saved\phase2_B5F_mis0_long_propagation_pathspec_audit\phase2_B5F_by_run.csv
```

B5D is included as manual stats in the config:

```text
case_pass_rate = 49/50
vehicle_pass_rate = 149/150
```

## Main interpretation

Use B5D as the positive bounded local U3 universality evidence.
Use B5E/B5F as failure-boundary diagnostics for the mis0-left corner.

Recommended claim:

```text
Bounded local U3 universality is supported inside the tight validated envelope.
Global or broad U4 universality is not claimed.
```
