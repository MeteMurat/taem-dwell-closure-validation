# -*- coding: utf-8 -*-
"""
Phase 2 / B4 final campaign synthesis for EntryGuidance TAEM campaign.

Purpose:
- Does NOT run new simulations.
- Collects the validated Phase-2 checkpoints into publication-ready tables and notes.
- Explicitly separates valid evidence from invalid/inconclusive technical trials.

Typical usage from project root:
    python .\phase2_B4_campaign_synthesis.py

Outputs under:
    store\data_saved\phase2_B4_final_campaign_synthesis
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ROOT = Path.cwd()
OUTDIR = ROOT / "store" / "data_saved" / "phase2_B4_final_campaign_synthesis"
OUTDIR.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return path.read_text(errors="replace")


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def first_existing(candidates: List[str]) -> Optional[Path]:
    for c in candidates:
        p = ROOT / c
        if p.exists():
            return p
    return None


def regex_find(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return m.group(1).strip() if m else default


def count_exists(paths: List[str]) -> int:
    return sum(1 for p in paths if (ROOT / p).exists())


# -------------------------------------------------------------------------
# Source discovery
# -------------------------------------------------------------------------
SOURCES = {
    "B1E": {
        "summary_txt": first_existing([
            "store/data_saved/PHASE2_B1E_PASS_FREEZE/phase2_B1_decision.txt",
            "store/data_saved/phase2_B1E_exact_single_report/phase2_B1_decision.txt",
        ]),
        "summary_json": first_existing([
            "store/data_saved/PHASE2_B1E_PASS_FREEZE/phase2_B1_decision.json",
            "store/data_saved/phase2_B1E_exact_single_report/phase2_B1_decision.json",
        ]),
        "primary_csv": first_existing([
            "store/data_saved/PHASE2_B1E_PASS_FREEZE/phase2_B1E_exact_single_scaffold_mis1.csv",
            "store/data_saved/phase2_B1E_exact_single_scaffold_mis1.csv",
        ]),
    },
    "B2": {
        "summary_txt": first_existing([
            "store/data_saved/PHASE2_B2_EXACT_SINGLE_PASS_FREEZE/phase2_B2_summary.txt",
            "store/data_saved/phase2_B2_exact_single_report/phase2_B2_summary.txt",
        ]),
        "numeric_audit": first_existing([
            "store/data_saved/phase2_B2_integrity_audit/b2_integrity_audit.txt",
            "store/data_saved/phase2_B2_numeric_diff_audit/b2_numeric_diff_audit.txt",
        ]),
        "primary_csv": first_existing([
            "store/data_saved/PHASE2_B2_EXACT_SINGLE_PASS_FREEZE/phase2_B2_exact_single_combined.csv",
            "store/data_saved/phase2_B2_exact_single_combined.csv",
        ]),
    },
    "B2R": {
        "summary_txt": first_existing([
            "store/data_saved/PHASE2_B2R_ROLE_DISTINCT_PASS_FREEZE/phase2_B2R_summary.txt",
            "store/data_saved/phase2_B2R_role_distinct_report/phase2_B2R_summary.txt",
        ]),
        "summary_json": first_existing([
            "store/data_saved/PHASE2_B2R_ROLE_DISTINCT_PASS_FREEZE/phase2_B2R_summary.json",
            "store/data_saved/phase2_B2R_role_distinct_report/phase2_B2R_summary.json",
        ]),
        "primary_csv": first_existing([
            "store/data_saved/PHASE2_B2R_ROLE_DISTINCT_PASS_FREEZE/phase2_B2R_role_distinct_combined.csv",
            "store/data_saved/phase2_B2R_role_distinct_combined.csv",
        ]),
    },
    "B3A": {
        "summary_txt": first_existing([
            "store/data_saved/PHASE2_B3A_HEADING_SPREAD_PASS_FREEZE/phase2_B3A_summary.txt",
            "store/data_saved/phase2_B3A_heading_spread_report/phase2_B3A_summary.txt",
        ]),
        "summary_json": first_existing([
            "store/data_saved/PHASE2_B3A_HEADING_SPREAD_PASS_FREEZE/phase2_B3A_summary.json",
            "store/data_saved/phase2_B3A_heading_spread_report/phase2_B3A_summary.json",
        ]),
        "primary_csv": first_existing([
            "store/data_saved/PHASE2_B3A_HEADING_SPREAD_PASS_FREEZE/phase2_B3A_heading_spread_combined_all.csv",
            "store/data_saved/phase2_B3A_heading_spread_combined_all.csv",
        ]),
    },
    "B3B": {
        "invalid_readme": first_existing([
            "store/data_saved/PHASE2_B3B_DWELL_V1_INVALID_FREEZE/README_B3B_DWELL_V1_INVALID.txt",
        ]),
        "post_summary": first_existing([
            "store/data_saved/PHASE2_B3B_DWELL_V1_INVALID_FREEZE/phase2_B3B_post_dwell_summary.txt",
            "store/data_saved/phase2_B3B_post_dwell_report/phase2_B3B_post_dwell_summary.txt",
        ]),
        "run_summary": first_existing([
            "store/data_saved/PHASE2_B3B_DWELL_V1_INVALID_FREEZE/phase2_B3B_run_summary.txt",
            "store/data_saved/phase2_B3B_run_dwell_report/phase2_B3B_run_summary.txt",
        ]),
    },
    "B3C": {
        "summary_txt": first_existing([
            "store/data_saved/PHASE2_B3C_TOLERANCE_PARTIAL_PASS_FREEZE/phase2_B3C_tolerance_summary.txt",
            "store/data_saved/phase2_B3C_tolerance_report/phase2_B3C_tolerance_summary.txt",
        ]),
        "summary_json": first_existing([
            "store/data_saved/PHASE2_B3C_TOLERANCE_PARTIAL_PASS_FREEZE/phase2_B3C_tolerance_summary.json",
            "store/data_saved/phase2_B3C_tolerance_report/phase2_B3C_tolerance_summary.json",
        ]),
        "by_case": first_existing([
            "store/data_saved/PHASE2_B3C_TOLERANCE_PARTIAL_PASS_FREEZE/phase2_B3C_tolerance_by_case.csv",
            "store/data_saved/phase2_B3C_tolerance_report/phase2_B3C_tolerance_by_case.csv",
        ]),
    },
}


# -------------------------------------------------------------------------
# Extract known metrics, with robust fallbacks
# -------------------------------------------------------------------------
b1_txt = read_text(SOURCES["B1E"]["summary_txt"]) if SOURCES["B1E"]["summary_txt"] else ""
b1_json = read_json(SOURCES["B1E"]["summary_json"]) if SOURCES["B1E"]["summary_json"] else {}

b2_txt = read_text(SOURCES["B2"]["summary_txt"]) if SOURCES["B2"]["summary_txt"] else ""
b2_audit_txt = read_text(SOURCES["B2"]["numeric_audit"]) if SOURCES["B2"]["numeric_audit"] else ""

b2r_txt = read_text(SOURCES["B2R"]["summary_txt"]) if SOURCES["B2R"]["summary_txt"] else ""
b2r_json = read_json(SOURCES["B2R"]["summary_json"]) if SOURCES["B2R"]["summary_json"] else {}

b3a_txt = read_text(SOURCES["B3A"]["summary_txt"]) if SOURCES["B3A"]["summary_txt"] else ""
b3a_json = read_json(SOURCES["B3A"]["summary_json"]) if SOURCES["B3A"]["summary_json"] else {}

b3b_readme = read_text(SOURCES["B3B"]["invalid_readme"]) if SOURCES["B3B"]["invalid_readme"] else ""
b3b_post_txt = read_text(SOURCES["B3B"]["post_summary"]) if SOURCES["B3B"]["post_summary"] else ""
b3b_run_txt = read_text(SOURCES["B3B"]["run_summary"]) if SOURCES["B3B"]["run_summary"] else ""

b3c_txt = read_text(SOURCES["B3C"]["summary_txt"]) if SOURCES["B3C"]["summary_txt"] else ""
b3c_json = read_json(SOURCES["B3C"]["summary_json"]) if SOURCES["B3C"]["summary_json"] else {}


# -------------------------------------------------------------------------
# Master decision table
# -------------------------------------------------------------------------
master_rows = [
    {
        "phase_id": "B1E",
        "campaign_title": "Exact-single scaffold preservation of V8.2 mis1 baseline",
        "evidence_type": "simulation + checker",
        "decision": regex_find(b1_txt, r"Decision\s*:\s*([^\n]+)", "PASS_STRICT" if "PASS_STRICT" in b1_txt else "UNKNOWN"),
        "validity_status": "VALID",
        "n_vehicles": 1,
        "strict_pass_count": 1 if "PASS_STRICT" in b1_txt else "",
        "role_distinct_ok": "not_applicable",
        "key_metric": "taem_dwell_s=3.0; close_pass_escape=False; end_reason=taem_dwell_reached" if b1_txt else "source_missing_or_unparsed",
        "scientific_use": "Use as baseline preservation/control evidence.",
        "primary_source": str(SOURCES["B1E"]["summary_txt"]) if SOURCES["B1E"]["summary_txt"] else "missing",
    },
    {
        "phase_id": "B2",
        "campaign_title": "Initial exact-single sequential 3-id classification",
        "evidence_type": "simulation + integrity audit",
        "decision": "INFRASTRUCTURE_PASS_REPLICATED_BASELINE",
        "validity_status": "VALID_AS_INFRASTRUCTURE_ONLY_NOT_ROLE_SPECIFIC",
        "n_vehicles": 3,
        "strict_pass_count": regex_find(b2_txt, r"n_strict_pass\s*:\s*(\d+)", "3" if "n_strict_pass" in b2_txt else ""),
        "role_distinct_ok": "False",
        "key_metric": "numeric diff audit showed dynamic columns identical across mis0/mis1/mis2" if "max_abs_diff=0" in b2_audit_txt else "role-specific distinction not established",
        "scientific_use": "Do not cite as role-specific multi-vehicle success; cite only as an orchestration smoke test if needed.",
        "primary_source": str(SOURCES["B2"]["numeric_audit"] or SOURCES["B2"]["summary_txt"] or "missing"),
    },
    {
        "phase_id": "B2R",
        "campaign_title": "Role-distinct exact-single sequential transfer",
        "evidence_type": "simulation + dynamic-difference audit",
        "decision": regex_find(b2r_txt, r"decision\s*:\s*([^\n]+)", "B2R_PASS_ROLE_DISTINCT" if "B2R_PASS_ROLE_DISTINCT" in b2r_txt else "UNKNOWN"),
        "validity_status": "VALID",
        "n_vehicles": int(regex_find(b2r_txt, r"n_vehicles\s*:\s*(\d+)", "3") or 3),
        "strict_pass_count": regex_find(b2r_txt, r"n_strict_pass\s*:\s*(\d+)", "3" if "3/3" in b2r_txt else ""),
        "role_distinct_ok": regex_find(b2r_txt, r"role_distinct_ok\s*:\s*([^\n]+)", "True" if "role_distinct_ok   : True" in b2r_txt else ""),
        "key_metric": "max_dynamic_diff≈741174.72; heading_delta=[-2,0,+2] deg; pass=3/3",
        "scientific_use": "First valid role-distinct exact-single multi-vehicle transfer evidence.",
        "primary_source": str(SOURCES["B2R"]["summary_txt"]) if SOURCES["B2R"]["summary_txt"] else "missing",
    },
    {
        "phase_id": "B3A",
        "campaign_title": "Heading-spread sensitivity",
        "evidence_type": "sensitivity campaign",
        "decision": regex_find(b3a_txt, r"overall_decision\s*:\s*([^\n]+)", "B3A_PASS_ALL_SPREADS" if "B3A_PASS_ALL_SPREADS" in b3a_txt else "UNKNOWN"),
        "validity_status": "VALID",
        "n_vehicles": 3,
        "strict_pass_count": "3/3 at each tested spread",
        "role_distinct_ok": "True",
        "key_metric": "spreads=[±1,±2,±3,±4] deg all pass; max_dynamic_diff grows from ≈345k to ≈1.49M",
        "scientific_use": "Supports bounded heading-dispersion robustness claim.",
        "primary_source": str(SOURCES["B3A"]["summary_txt"]) if SOURCES["B3A"]["summary_txt"] else "missing",
    },
    {
        "phase_id": "B3B",
        "campaign_title": "Dwell sensitivity",
        "evidence_type": "post-process + invalid run-v1 note",
        "decision": "DWELL3_CONFIRMED_DWELL4_5_NOT_VALIDLY_TESTED",
        "validity_status": "PARTIAL_VALIDITY_RUN_V1_INVALID",
        "n_vehicles": 3,
        "strict_pass_count": "3/3 for dwell_req=3 only",
        "role_distinct_ok": "True for nominal dwell=3 evidence",
        "key_metric": "post: dwell=3 pass, dwell=4/5 inconclusive; run-v1 override ineffective",
        "scientific_use": "Report nominal dwell=3 only; do not claim dwell=4/5 robustness from v1.",
        "primary_source": str(SOURCES["B3B"]["invalid_readme"] or SOURCES["B3B"]["post_summary"] or "missing"),
    },
    {
        "phase_id": "B3C",
        "campaign_title": "TAEM tolerance sensitivity",
        "evidence_type": "post-process tolerance sweep",
        "decision": regex_find(b3c_txt, r"overall_decision\s*:\s*([^\n]+)", "B3C_PARTIAL_PASS" if "B3C_PARTIAL_PASS" in b3c_txt else "UNKNOWN"),
        "validity_status": "VALID_PARTIAL_PASS",
        "n_vehicles": 3,
        "strict_pass_count": "8/16 case-tolerance rows pass role-distinct" if "pass_role_distinct" in b3c_txt else "",
        "role_distinct_ok": "True for passing tolerance rows",
        "key_metric": "h_tol=3000 m: all tested v/sgo combos pass; h_tol=2000 m: all fail",
        "scientific_use": "Establishes altitude-tolerance boundary at 3000 m vs 2000 m.",
        "primary_source": str(SOURCES["B3C"]["summary_txt"]) if SOURCES["B3C"]["summary_txt"] else "missing",
    },
]

master_df = pd.DataFrame(master_rows)
master_df.to_csv(OUTDIR / "phase2_master_decision_table.csv", index=False)


# -------------------------------------------------------------------------
# Campaign matrix / manifest
# -------------------------------------------------------------------------
manifest_rows = []
for phase, srcs in SOURCES.items():
    for k, p in srcs.items():
        manifest_rows.append({
            "phase_id": phase,
            "source_kind": k,
            "path": str(p) if p else "missing",
            "exists": bool(p and p.exists()),
            "size_bytes": int(p.stat().st_size) if p and p.exists() else None,
        })
manifest_df = pd.DataFrame(manifest_rows)
manifest_df.to_csv(OUTDIR / "phase2_freeze_manifest.csv", index=False)

campaign_matrix = pd.DataFrame([
    {
        "phase_id": r["phase_id"],
        "question_answered": {
            "B1E": "Does mis1 preserve the frozen V8.2 TAEM success under exact-single scaffold?",
            "B2": "Does the exact-single sequential infrastructure execute three ids?",
            "B2R": "Can role-distinct heading-separated vehicles retain 3/3 TAEM success?",
            "B3A": "Is role-distinct success robust to bounded heading spread?",
            "B3B": "Is success robust to stricter dwell duration?",
            "B3C": "Which TAEM tolerance dimensions define the success boundary?",
        }.get(r["phase_id"], ""),
        "decision": r["decision"],
        "validity_status": r["validity_status"],
        "recommended_use": r["scientific_use"],
        "key_metric": r["key_metric"],
    }
    for r in master_rows
])
campaign_matrix.to_csv(OUTDIR / "phase2_campaign_matrix.csv", index=False)


# -------------------------------------------------------------------------
# Text deliverables
# -------------------------------------------------------------------------
summary_lines = []
summary_lines.append("PHASE 2 / B4 FINAL CAMPAIGN SYNTHESIS")
summary_lines.append("=" * 72)
summary_lines.append(f"output_dir: {OUTDIR}")
summary_lines.append("")
summary_lines.append("Master decision summary:")
for r in master_rows:
    summary_lines.append(
        f"  {r['phase_id']:4s} | {r['decision']} | {r['validity_status']} | {r['key_metric']}"
    )
summary_lines.append("")
summary_lines.append("Recommended official interpretation:")
summary_lines.append("  - Treat B1E as the valid baseline-preservation checkpoint.")
summary_lines.append("  - Treat B2 as an infrastructure smoke test only, not as role-specific evidence.")
summary_lines.append("  - Treat B2R as the first valid role-distinct exact-single 3/3 TAEM transfer result.")
summary_lines.append("  - Treat B3A as bounded heading-spread robustness evidence.")
summary_lines.append("  - Treat B3B as nominal dwell=3 confirmation only; dwell=4/5 remain not validly tested in v1.")
summary_lines.append("  - Treat B3C as a partial-pass tolerance boundary: h_tol=3000 m passes, h_tol=2000 m fails.")
summary_lines.append("")
summary_lines.append("Generated files:")
for fname in [
    "phase2_master_decision_table.csv",
    "phase2_campaign_matrix.csv",
    "phase2_freeze_manifest.csv",
    "phase2_publication_summary.txt",
    "phase2_key_results_for_manuscript.txt",
    "phase2_limitations_notes.txt",
]:
    summary_lines.append(f"  - {OUTDIR / fname}")

(OUTDIR / "phase2_B4_summary.txt").write_text("\n".join(summary_lines), encoding="utf-8")

publication_summary = """PHASE 2 / PUBLICATION-READY SUMMARY
========================================================================

The Phase-2 campaign established a controlled transition from a single-vehicle V8.2 TAEM success case to a role-distinct exact-single sequential multi-vehicle protocol. The B1E checkpoint confirmed that the frozen V8.2 mis1 baseline remains reproducible under the exact-single scaffold, with clean-latched TAEM success and end_reason=taem_dwell_reached. The initial B2 run produced 3/3 PASS_STRICT but was subsequently reclassified as an infrastructure-only test because numeric-difference auditing showed that the three trajectories were replicated baseline scaffolds rather than role-distinct cases.

The first valid role-distinct result was obtained in B2R. Three heading-separated vehicle roles, using heading_delta = -2, 0, and +2 degrees, all achieved PASS_STRICT with role_distinct_ok=True. This establishes the first valid role-distinct exact-single 3/3 TAEM transfer result in the Phase-2 campaign.

The B3A heading-spread sensitivity campaign retained 3/3 role-distinct success for all tested spreads, namely ±1, ±2, ±3, and ±4 degrees. This supports a bounded heading-dispersion robustness claim for the exact-single sequential protocol.

The B3B dwell analysis should be reported conservatively. Existing B2R/B3A logs confirm nominal dwell_req=3, while dwell_req=4 and dwell_req=5 were inconclusive in post-processing because trajectories ended at the nominal dwell=3 latch. The subsequent B3B-run v1 was invalid for dwell=4/5 because by-vehicle inspection showed that higher dwell requirements were not actually enforced. Therefore, B3B should be used only to confirm nominal dwell=3, not to claim higher-dwell robustness.

The B3C tolerance sweep produced a partial-pass result. Role-distinct 3/3 success was retained for all tested velocity and range-to-go tolerance combinations when h_tol=3000 m. In contrast, all h_tol=2000 m combinations failed. This identifies altitude tolerance as the active robustness boundary within the tested tolerance matrix.
"""
(OUTDIR / "phase2_publication_summary.txt").write_text(publication_summary, encoding="utf-8")

key_results = """PHASE 2 / KEY RESULTS FOR MANUSCRIPT
========================================================================

1. Baseline preservation:
   B1E confirmed that the frozen V8.2 mis1 case is reproducible under exact-single orchestration, achieving PASS_STRICT with taem_success_latched=True and end_reason=taem_dwell_reached.

2. Role-distinct transfer:
   B2R achieved 3/3 PASS_STRICT with heading-separated roles (-2, 0, +2 degrees), role_distinct_ok=True, and max_dynamic_diff≈741174.72. This is the first valid role-distinct exact-single multi-vehicle transfer result.

3. Heading-spread robustness:
   B3A retained 3/3 role-distinct TAEM success across all tested spreads (±1, ±2, ±3, ±4 degrees). This supports a bounded heading-dispersion robustness statement.

4. Dwell limitation:
   Nominal dwell_req=3 is confirmed. Dwell_req=4 and dwell_req=5 were not validly tested in B3B-run v1 because the override did not take effect. No higher-dwell robustness claim should be made from v1.

5. Tolerance boundary:
   B3C showed that h_tol=3000 m preserves 3/3 role-distinct success for all tested v_tol and sgo_tol combinations, while h_tol=2000 m fails in all tested combinations. The active tolerance boundary is altitude tolerance.

Recommended manuscript claim:
   The exact-single sequential protocol preserves role-distinct 3/3 TAEM success under bounded heading-dispersion and moderate TAEM tolerance tightening, with an identified altitude-tolerance boundary between 2000 m and 3000 m.
"""
(OUTDIR / "phase2_key_results_for_manuscript.txt").write_text(key_results, encoding="utf-8")

limitations = """PHASE 2 / LIMITATIONS AND VALIDITY NOTES
========================================================================

1. Simultaneous MultiMissileSim adapter results are not the official evidence line.
   Earlier B1/B1R simultaneous-adapter attempts failed due to adapter/runtime mismatch and range/heading closure failure. The accepted Phase-2 evidence line is exact-single sequential orchestration.

2. B2 is not role-specific evidence.
   Although B2 produced 3/3 PASS_STRICT, numeric-difference auditing showed the trajectories were replicated baseline scaffolds. B2 should be retained only as an infrastructure/smoke-test checkpoint.

3. B3B-run v1 is invalid for dwell_req=4/5.
   By-vehicle inspection showed that dwell_req=4 and dwell_req=5 runs still terminated at taem_dwell_s=3.0 and taem_dwell_count=3.0. Therefore, higher dwell requirements were not actually enforced.

4. B3C is a partial pass, not an unrestricted tolerance robustness result.
   The tolerance sweep supports robustness at h_tol=3000 m, but not at h_tol=2000 m. The altitude tolerance boundary must be explicitly reported.

5. The phrase 'multi-vehicle' should be qualified.
   The current valid protocol is role-distinct exact-single sequential orchestration. It is suitable when no inter-vehicle dynamic coupling is modeled. Avoid implying simultaneous coupled multi-agent dynamics unless a separate coupled-simulation validation is performed.
"""
(OUTDIR / "phase2_limitations_notes.txt").write_text(limitations, encoding="utf-8")

# Optional markdown table for copy/paste
md_lines = []
md_lines.append("| Phase | Decision | Validity | Key result | Use in paper |")
md_lines.append("|---|---|---|---|---|")
for r in master_rows:
    md_lines.append(
        f"| {r['phase_id']} | {r['decision']} | {r['validity_status']} | {r['key_metric']} | {r['scientific_use']} |"
    )
(OUTDIR / "phase2_master_decision_table_markdown.txt").write_text("\n".join(md_lines), encoding="utf-8")

print("\n".join(summary_lines))
print("\n[OK] B4 synthesis completed.")
