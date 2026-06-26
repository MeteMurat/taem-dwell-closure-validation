# -*- coding: utf-8 -*-
"""
Phase 2 / B5B-E — Validated Local Envelope Synthesis

Reads B5B conservative Monte Carlo outputs and extracts conservative local
velocity/height envelopes from the existing MC sample. This is a post-process
analysis only; it does not run new simulations.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


def wilson(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z*z/n
    cen = (p + z*z/(2*n)) / den
    half = z * math.sqrt((p*(1-p) + z*z/(4*n)) / n) / den
    return (max(0.0, cen - half), min(1.0, cen + half))


def is_pass_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.upper().str.contains("PASS_STRICT|PASS_ROLE_DISTINCT|SUCCESS", regex=True)


def pick_col(df: pd.DataFrame, candidates: Iterable[str], required: bool = True) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        raise KeyError(f"None of the candidate columns found: {list(candidates)}")
    return None


def summarize_mask(vdf: pd.DataFrame, mask: pd.Series, case_col: str, vehicle_col: str, decision_col: str, close_col: str | None) -> Dict:
    sub = vdf[mask].copy()
    n_vehicle = len(sub)
    vehicle_pass = int(is_pass_series(sub[decision_col]).sum()) if n_vehicle else 0
    v_lo, v_hi = wilson(vehicle_pass, n_vehicle)

    if n_vehicle:
        case_pass_flags = sub.groupby(case_col)[decision_col].apply(lambda x: bool(is_pass_series(x).all()))
        n_case = len(case_pass_flags)
        case_pass = int(case_pass_flags.sum())
    else:
        n_case = 0
        case_pass = 0
    c_lo, c_hi = wilson(case_pass, n_case)

    if close_col and close_col in sub.columns and n_vehicle:
        close_count = int(sub[close_col].astype(str).str.lower().isin(["true", "1", "yes"]).sum())
    else:
        close_count = None

    return {
        "n_cases": n_case,
        "case_pass": case_pass,
        "case_pass_rate": (case_pass / n_case) if n_case else float("nan"),
        "case_pass_ci95_low": c_lo,
        "case_pass_ci95_high": c_hi,
        "n_vehicle_rows": n_vehicle,
        "vehicle_pass": vehicle_pass,
        "vehicle_pass_rate": (vehicle_pass / n_vehicle) if n_vehicle else float("nan"),
        "vehicle_pass_ci95_low": v_lo,
        "vehicle_pass_ci95_high": v_hi,
        "close_escape_count": close_count,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehicle-csv", default=r"store\data_saved\phase2_B5B_mc_conservative_u3_report\phase2_B5B_mc_by_vehicle_all.csv")
    ap.add_argument("--outdir", default=r"store\data_saved\phase2_B5B_validated_envelope_report")
    ap.add_argument("--min-cases", type=int, default=5)
    args = ap.parse_args()

    vehicle_csv = Path(args.vehicle_csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not vehicle_csv.exists():
        raise FileNotFoundError(f"vehicle CSV not found: {vehicle_csv}")

    df = pd.read_csv(vehicle_csv)
    case_col = pick_col(df, ["mc_case_id", "case_id", "case", "run_id"])
    h_col = pick_col(df, ["height_delta_m", "h_delta_m", "height_delta"])
    v_col = pick_col(df, ["velocity_delta_mps", "v_delta_mps", "velocity_delta"])
    vehicle_col = pick_col(df, ["mis_id", "vehicle_id", "vehicle"])
    decision_col = pick_col(df, ["decision", "b1_vehicle_decision", "vehicle_decision"])
    close_col = pick_col(df, ["last_close_pass_escape", "close_pass_escape", "any_close_pass_escape"], required=False)
    label_col = pick_col(df, ["label", "failure_label", "_failure_class"], required=False)

    df[h_col] = pd.to_numeric(df[h_col], errors="coerce")
    df[v_col] = pd.to_numeric(df[v_col], errors="coerce")

    # Candidate envelopes. These are not claims; they are sample-supported envelopes.
    candidate_ranges = [
        ("V_ALL_CONSERVATIVE", -50.0, 10.0),
        ("V_NEG50_TO_0", -50.0, 0.0),
        ("V_NEG40_TO_PLUS10", -40.0, 10.0),
        ("V_NEG30_TO_PLUS10", -30.0, 10.0),
        ("V_NEG20_TO_PLUS10", -20.0, 10.0),
        ("V_NEG10_TO_PLUS10", -10.0, 10.0),
        ("V_NEG20_TO_0", -20.0, 0.0),
        ("V_NEG10_TO_0", -10.0, 0.0),
        ("V_0_TO_PLUS10", 0.0, 10.0),
    ]
    # Optional central-height sub-envelope in case failures are height-dependent.
    height_ranges = [
        ("H_ALL", None, None),
        ("H_ABS_LE_250", -250.0, 250.0),
        ("H_POSITIVE", 0.0, 500.0),
        ("H_NEGATIVE", -500.0, 0.0),
    ]

    rows: List[Dict] = []
    for vname, vmin, vmax in candidate_ranges:
        vmask = (df[v_col] >= vmin) & (df[v_col] <= vmax)
        for hname, hmin, hmax in height_ranges:
            if hmin is None:
                mask = vmask
            else:
                mask = vmask & (df[h_col] >= hmin) & (df[h_col] <= hmax)
            rec = summarize_mask(df, mask, case_col, vehicle_col, decision_col, close_col)
            rec.update({
                "envelope_id": f"{vname}__{hname}",
                "v_min": vmin,
                "v_max": vmax,
                "h_min": hmin,
                "h_max": hmax,
            })
            rows.append(rec)

    env = pd.DataFrame(rows)
    env = env.sort_values(["case_pass_rate", "vehicle_pass_rate", "n_cases"], ascending=[False, False, False])
    env.to_csv(outdir / "b5b_validated_envelope_candidates.csv", index=False)

    # Failure rows and compact mode counts.
    fail_df = df[~is_pass_series(df[decision_col])].copy()
    fail_df.to_csv(outdir / "b5b_validated_envelope_failure_rows.csv", index=False)

    if label_col:
        failure_counts = df[label_col].astype(str).value_counts(dropna=False).reset_index()
        failure_counts.columns = ["label", "n"]
    else:
        failure_counts = pd.DataFrame()
    failure_counts.to_csv(outdir / "b5b_validated_envelope_failure_mode_counts.csv", index=False)

    # Choose a conservative sample-supported local envelope, not as proof, but for next MC.
    eligible = env[(env["n_cases"] >= args.min_cases) & (env["case_pass_rate"] >= 0.80)].copy()
    if not eligible.empty:
        chosen = eligible.sort_values(["case_pass_ci95_low", "case_pass_rate", "n_cases"], ascending=[False, False, False]).iloc[0].to_dict()
        recommendation = "NARROW_LOCAL_ENVELOPE_AVAILABLE"
    else:
        chosen = None
        recommendation = "NO_STRONG_LOCAL_ENVELOPE_FROM_B5B_SAMPLE"

    lines: List[str] = []
    lines.append("PHASE 2 / B5B-E — VALIDATED LOCAL ENVELOPE SYNTHESIS")
    lines.append("=" * 72)
    lines.append(f"vehicle_csv: {vehicle_csv}")
    lines.append(f"rows: {len(df)}")
    lines.append(f"case_col={case_col} h_col={h_col} v_col={v_col} vehicle_col={vehicle_col}")
    lines.append("")
    lines.append("[TOP ENVELOPE CANDIDATES]")
    show_cols = ["envelope_id", "n_cases", "case_pass", "case_pass_rate", "case_pass_ci95_low", "case_pass_ci95_high", "n_vehicle_rows", "vehicle_pass", "vehicle_pass_rate", "close_escape_count"]
    lines.append(env[show_cols].head(12).to_string(index=False))
    lines.append("")
    lines.append("[RECOMMENDATION]")
    lines.append(f"recommendation: {recommendation}")
    if chosen:
        lines.append("chosen_candidate:")
        for k in ["envelope_id", "v_min", "v_max", "h_min", "h_max", "n_cases", "case_pass", "case_pass_rate", "case_pass_ci95_low", "case_pass_ci95_high", "n_vehicle_rows", "vehicle_pass", "vehicle_pass_rate", "close_escape_count"]:
            lines.append(f"  {k}: {chosen.get(k)}")
    else:
        lines.append("No candidate with n_cases>=min_cases and case_pass_rate>=0.80 was found.")
        lines.append("Use this as evidence that range-closure recovery is needed before additional U3/U4 Monte Carlo claims.")
    lines.append("")
    lines.append("[MANUSCRIPT-SAFE INTERPRETATION]")
    lines.append("- B5B conservative MC is close-pass/range-closure dominated and does not support U4 universality.")
    lines.append("- Any follow-up stochastic claim must either use a narrower validated local envelope or introduce range-closure recovery before broader dispersions.")
    lines.append("- If a narrow envelope is selected, report it explicitly as local-envelope support, not universality.")
    lines.append("")
    lines.append("[OUTPUTS]")
    for fn in ["b5b_validated_envelope_candidates.csv", "b5b_validated_envelope_failure_rows.csv", "b5b_validated_envelope_failure_mode_counts.csv", "b5b_validated_envelope_summary.json"]:
        lines.append(f"  - {outdir / fn}")

    summary = {
        "vehicle_csv": str(vehicle_csv),
        "n_rows": int(len(df)),
        "recommendation": recommendation,
        "chosen_candidate": chosen,
        "top_candidates": env.head(12).to_dict(orient="records"),
    }
    (outdir / "b5b_validated_envelope_summary.txt").write_text("\n".join(lines), encoding="utf-8")
    (outdir / "b5b_validated_envelope_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "b5b_validated_envelope_for_manuscript.txt").write_text("\n".join([
        "B5B conservative Monte Carlo revealed stochastic fragility dominated by close-pass/range-closure events.",
        "The evidence does not support a U4 universality claim.",
        "The next defensible step is either a narrower local-envelope Monte Carlo or a range-closure recovery update before broader dispersion testing.",
    ]), encoding="utf-8")

    print("\n".join(lines))
    print(f"\n[OK] wrote: {outdir / 'b5b_validated_envelope_summary.txt'}")


if __name__ == "__main__":
    main()
