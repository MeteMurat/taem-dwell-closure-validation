PHASE 2 / B5B-E — VALIDATED LOCAL ENVELOPE SYNTHESIS

Purpose:
Post-process the B5B conservative Monte Carlo pilot to identify whether any narrower local velocity/height envelope is supported by the existing sample.

This script does not run simulations. It reads:
  store\data_saved\phase2_B5B_mc_conservative_u3_report\phase2_B5B_mc_by_vehicle_all.csv

Outputs:
  store\data_saved\phase2_B5B_validated_envelope_report\b5b_validated_envelope_summary.txt
  store\data_saved\phase2_B5B_validated_envelope_report\b5b_validated_envelope_candidates.csv
  store\data_saved\phase2_B5B_validated_envelope_report\b5b_validated_envelope_failure_rows.csv
  store\data_saved\phase2_B5B_validated_envelope_report\b5b_validated_envelope_for_manuscript.txt

Interpretation:
A selected envelope is not a U4 universality proof. It is only a sample-supported local envelope for follow-up MC testing.
