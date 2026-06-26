# Phase 2 B6 — Bounded Universality Evidence Pack

## Executive conclusion

The evidence supports bounded local U3 universality inside the tight validated envelope. The work should not claim global universality. B5D is the positive envelope evidence; B5E and B5F are failure-boundary diagnostics for the mis0-left corner.

## Campaign-level evidence table

| campaign_id | evidence_role | source_status | n_cases_or_runs | case_or_run_pass_rate | vehicle_pass_rate | timeout_rate | dominant_decision | dominant_failure_mode | recommended_use |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B5D_tight_local_U3_envelope | positive_envelope_evidence | manual_stats | 50 | 98.00% | 99.33% | 0.00% | B5C_LOCAL_ENVELOPE_SUPPORTED | single close-escape / strict-boundary row in tight local envelope | Use as the main bounded-universality evidence. |
| B5E_mis0_corner_bounded_diagnostic | boundary_diagnostic | csv_loaded | 30 | 0.00% | 0.00% | 0.00% | FAIL_TAEM_ERROR | FAIL_TAEM_ERROR: path-shaping and fade candidates did not produce strict TAEM success or meaningful candidate separation. | Use as failure-boundary evidence; do not use as positive universality evidence. |
| B5F_mis0_long_propagation_pathspec_audit | boundary_diagnostic | csv_loaded | 4 | 0.00% | 0.00% | 75.00% | TIMEOUT_NO_CSV | No strict TAEM pass. One case closes range without latch; other cases may timeout. PathSpec remains inactive or ineffective, and the run stays in steady_glide_phase. | Use to delimit the current certified envelope and motivate future terminal-capture refinement. |

## Detailed campaign interpretation

### B5D_tight_local_U3_envelope — Tight local U3 envelope validation

- Evidence role: `positive_envelope_evidence`
- Source status: `manual_stats`
- Pass rate: 98.00%
- Vehicle pass rate: 99.33%
- Timeout rate: 0.00%
- Dominant decision: `B5C_LOCAL_ENVELOPE_SUPPORTED`
- Decision counts: `PASS:49; FAIL/close_escape:1`
- Dominant last guidance phase: `taem_dwell_reached`
- PathSpec active in any row: `N/A`

Interpretation: Primary positive evidence. This campaign supports the bounded local U3 envelope: 49/50 case-level success and 149/150 vehicle-level success.

### B5E_mis0_corner_bounded_diagnostic — mis0 corner bounded diagnostic / path-shaping refinement attempt

- Evidence role: `boundary_diagnostic`
- Source status: `csv_loaded`
- Source path: `/mnt/data/phase2_B5E_by_run.csv`
- Pass rate: 0.00%
- Vehicle pass rate: 0.00%
- Timeout rate: 0.00%
- Dominant decision: `FAIL_TAEM_ERROR`
- Decision counts: `FAIL_TAEM_ERROR:30`
- Minimum final range-to-go: 9.039e+06 m

Interpretation: Boundary evidence. B5E shows that simple psi_bias/fade refinement is insufficient for certifying the mis0-left corner.

### B5F_mis0_long_propagation_pathspec_audit — mis0 long-propagation reachability and PathSpec activation audit

- Evidence role: `boundary_diagnostic`
- Source status: `csv_loaded`
- Source path: `/mnt/data/phase2_B5F_by_run.csv`
- Pass rate: 0.00%
- Vehicle pass rate: 0.00%
- Timeout rate: 75.00%
- Dominant decision: `TIMEOUT_NO_CSV`
- Decision counts: `TIMEOUT_NO_CSV:3; NO_PASS_BUT_RANGE_CLOSING:1`
- Minimum final range-to-go: 4.611e+06 m
- Maximum range-closure percentage: 58.518%
- Dominant last guidance phase: `steady_glide_phase`
- PathSpec active in any row: `False`

Interpretation: Reachability-boundary evidence. The best long-propagation case closes range but remains outside TAEM, indicating a terminal-capture / phase-transition boundary.
