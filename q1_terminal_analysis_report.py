#!/usr/bin/env python3
"""
Q1-oriented terminal-analysis reporter for multi-vehicle entry guidance runs.

Inputs:
- summary_by_vehicle.csv
- taem_compare_by_vehicle.csv
- taem_compare_by_run.csv
- optional raw simulator CSV with taem_* columns

Outputs:
- q1_vehicle_metrics.csv
- q1_failure_modes.csv
- q1_run_summary.csv
- q1_report.md

This script is meant to support a Q1-style paper narrative by converting raw
post-processing outputs into publication-ready analysis tables and a compact
markdown report.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import math
import numpy as np
import pandas as pd


def safe_float(x, default=np.nan):
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


TAEM_DEFAULTS = {
    "h_tol": 1500.0,
    "v_tol": 120.0,
    "sgo_tol": 15000.0,
    "psi_tol_deg": 8.0,
}


def classify_failure_mode(row: pd.Series, h_tol: float, v_tol: float, sgo_tol: float, psi_tol_rad: float) -> str:
    if bool(row.get("taem_reached", False)):
        return "TAEM latch success"

    h_min = abs(safe_float(row.get("taem_h_err_minabs", np.nan)))
    v_min = abs(safe_float(row.get("taem_v_err_minabs", np.nan)))
    s_min = abs(safe_float(row.get("taem_s_go_err_minabs", np.nan)))
    p_min = abs(safe_float(row.get("taem_psi_err_minabs", np.nan)))
    s_last = abs(safe_float(row.get("taem_s_go_err_last", np.nan)))
    h_last = abs(safe_float(row.get("taem_h_err_last", np.nan)))
    v_last = abs(safe_float(row.get("taem_v_err_last", np.nan)))
    p_last = abs(safe_float(row.get("taem_psi_err_last", np.nan)))

    within_h = math.isfinite(h_min) and h_min <= h_tol
    within_v = math.isfinite(v_min) and v_min <= v_tol
    within_s = math.isfinite(s_min) and s_min <= sgo_tol
    within_p = math.isfinite(p_min) and p_min <= psi_tol_rad

    count_min_hits = sum([within_h, within_v, within_s, within_p])

    if count_min_hits == 4:
        return "Near-success / no dwell"
    if count_min_hits >= 3:
        return "Multi-channel near-hit"

    # terminal closure vs mismatch style heuristics
    if math.isfinite(s_last) and s_last <= 5.0 * sgo_tol:
        if math.isfinite(h_last) and h_last <= 5.0 * h_tol and math.isfinite(v_last) and v_last <= 5.0 * v_tol:
            return "Late terminal closure"
        return "Range-close / state-mismatch"

    if within_h and within_v and (not within_s):
        return "Altitude-velocity matched / range open"
    if within_s and (not within_h or not within_v):
        return "Range matched / state mismatch"

    return "Range rebound or late divergence"



def build_vehicle_metrics(summary_df: pd.DataFrame, vehicle_df: pd.DataFrame,
                         h_tol: float, v_tol: float, sgo_tol: float, psi_tol_rad: float) -> pd.DataFrame:
    s = summary_df.copy()
    v = vehicle_df.copy()

    if "mis_id" in s.columns and "vehicle_id" in v.columns:
        merged = s.merge(v, left_on="mis_id", right_on="vehicle_id", how="outer", suffixes=("_summary", "_taem"))
    else:
        merged = pd.concat([s, v], axis=1)

    rows = []
    for _, row in merged.iterrows():
        vehicle_id = row.get("mis_id", row.get("vehicle_id", np.nan))
        h_min = abs(safe_float(row.get("taem_h_err_minabs", np.nan)))
        v_min = abs(safe_float(row.get("taem_v_err_minabs", np.nan)))
        s_min = abs(safe_float(row.get("taem_s_go_err_minabs", np.nan)))
        p_min = abs(safe_float(row.get("taem_psi_err_minabs", np.nan)))

        # IMPORTANT: this is a lower-bound proximity indicator because the
        # minimum errors may occur at different timestamps.
        lb_score = np.nan
        if all(math.isfinite(x) for x in [h_min, v_min, s_min, p_min]):
            lb_score = max(h_min / h_tol, v_min / v_tol, s_min / sgo_tol, p_min / psi_tol_rad)

        end_score = np.nan
        h_last = abs(safe_float(row.get("taem_h_err_last", row.get("taem_h_err_end", np.nan))))
        v_last = abs(safe_float(row.get("taem_v_err_last", row.get("taem_v_err_end", np.nan))))
        s_last_err = abs(safe_float(row.get("taem_s_go_err_last", row.get("taem_s_go_err_end", np.nan))))
        p_last = abs(safe_float(row.get("taem_psi_err_last", np.nan)))
        if all(math.isfinite(x) for x in [h_last, v_last, s_last_err, p_last]):
            end_score = max(h_last / h_tol, v_last / v_tol, s_last_err / sgo_tol, p_last / psi_tol_rad)

        rows.append({
            "vehicle_id": vehicle_id,
            "taem_reached": bool(row.get("taem_reached", False)),
            "taem_reached_any": bool(row.get("taem_reached_any", False)),
            "t_end": safe_float(row.get("t_end", np.nan)),
            "s_go_last_m": safe_float(row.get("s_go_last", np.nan)),
            "lon_end_deg": safe_float(row.get("lon_end_deg", np.nan)),
            "lat_end_deg": safe_float(row.get("lat_end_deg", np.nan)),
            "h_err_minabs_m": h_min,
            "v_err_minabs_mps": v_min,
            "s_go_err_minabs_m": s_min,
            "psi_err_minabs_rad": p_min,
            "taem_lb_score": lb_score,
            "taem_end_score": end_score,
            "q_max": safe_float(row.get("q_max", np.nan)),
            "dwell_max_s": safe_float(row.get("taem_dwell_max_s", np.nan)),
            "end_reason": row.get("end_reason_last", row.get("end_reason", "")),
            "guide_phase_last": row.get("guide_phase_last", ""),
        })

    out = pd.DataFrame(rows).sort_values(["taem_reached", "taem_lb_score", "s_go_last_m"], ascending=[False, True, True])
    out.reset_index(drop=True, inplace=True)
    return out



def build_failure_modes(vehicle_metrics: pd.DataFrame, vehicle_df: pd.DataFrame,
                        h_tol: float, v_tol: float, sgo_tol: float, psi_tol_rad: float) -> pd.DataFrame:
    lookup = vehicle_df.copy().set_index("vehicle_id", drop=False) if "vehicle_id" in vehicle_df.columns else vehicle_df.copy()
    rows = []
    for _, row in vehicle_metrics.iterrows():
        vid = row["vehicle_id"]
        src = lookup.loc[vid] if vid in lookup.index else row
        mode = classify_failure_mode(src, h_tol, v_tol, sgo_tol, psi_tol_rad)
        rows.append({
            "vehicle_id": vid,
            "failure_mode": mode,
            "taem_lb_score": row.get("taem_lb_score", np.nan),
            "s_go_last_m": row.get("s_go_last_m", np.nan),
            "end_reason": row.get("end_reason", ""),
            "guide_phase_last": row.get("guide_phase_last", ""),
        })
    return pd.DataFrame(rows)



def format_vehicle_line(row: pd.Series) -> str:
    def f(x, digits=3):
        x = safe_float(x, np.nan)
        return "NA" if not math.isfinite(x) else f"{x:.{digits}f}"

    return (
        f"- Vehicle {int(row['vehicle_id'])}: reached={bool(row['taem_reached'])}, "
        f"lower-bound score={f(row['taem_lb_score'])}, "
        f"final s_go={f(row['s_go_last_m'], 1)} m, "
        f"min |h_err|={f(row['h_err_minabs_m'], 2)} m, "
        f"min |v_err|={f(row['v_err_minabs_mps'], 3)} m/s, "
        f"min |s_go_err|={f(row['s_go_err_minabs_m'], 2)} m, "
        f"min |psi_err|={f(row['psi_err_minabs_rad'], 6)} rad"
    )



def write_markdown_report(outdir: Path, run_df: pd.DataFrame, vehicle_metrics: pd.DataFrame, failure_df: pd.DataFrame,
                          h_tol: float, v_tol: float, sgo_tol: float, psi_tol_deg: float):
    run = run_df.iloc[0] if len(run_df) else pd.Series(dtype=object)
    best_lb = vehicle_metrics.sort_values("taem_lb_score", ascending=True).iloc[0] if len(vehicle_metrics) else pd.Series(dtype=object)
    best_final = vehicle_metrics.sort_values("s_go_last_m", ascending=True).iloc[0] if len(vehicle_metrics) else pd.Series(dtype=object)

    lines = []
    lines.append("# Q1-Oriented Terminal Analysis Report")
    lines.append("")
    lines.append("## Run summary")
    lines.append("")
    if len(run_df):
        lines.append(f"- Run ID: `{run.get('run_id', '')}`")
        lines.append(f"- Vehicles: {int(run.get('n_vehicles', 0))}")
        lines.append(f"- TAEM reached rate: {safe_float(run.get('reached_rate', np.nan), np.nan):.3f}")
        lines.append(f"- Any-reached rate: {safe_float(run.get('reached_any_rate', np.nan), np.nan):.3f}")
        lines.append(f"- Average dwell: {safe_float(run.get('avg_dwell_s', np.nan), np.nan):.3f} s")
    lines.append(f"- Evaluation tolerances: h={h_tol:.1f} m, v={v_tol:.1f} m/s, s_go={sgo_tol:.1f} m, psi={psi_tol_deg:.2f} deg")
    lines.append("")
    lines.append("## Vehicle-wise metrics")
    lines.append("")
    for _, row in vehicle_metrics.iterrows():
        lines.append(format_vehicle_line(row))
    lines.append("")
    if len(vehicle_metrics):
        lines.append("## Key interpretation")
        lines.append("")
        lines.append(
            f"- Best TAEM-proximity candidate (lower-bound score): vehicle {int(best_lb['vehicle_id'])}."
        )
        lines.append(
            f"- Best final geographic/range closure candidate: vehicle {int(best_final['vehicle_id'])}."
        )
        lines.append(
            "- Note: the lower-bound score uses per-channel minimum absolute errors, so it is a conservative proximity indicator rather than proof of simultaneous in-box satisfaction."
        )
        lines.append("")
    lines.append("## Failure-mode classification")
    lines.append("")
    for _, row in failure_df.iterrows():
        lines.append(
            f"- Vehicle {int(row['vehicle_id'])}: {row['failure_mode']} (final s_go={safe_float(row['s_go_last_m'], np.nan):.1f} m)"
        )
    lines.append("")
    lines.append("## Suggested manuscript usage")
    lines.append("")
    lines.append("- Use `q1_vehicle_metrics.csv` as the basis for a vehicle-wise terminal proximity table.")
    lines.append("- Use `q1_failure_modes.csv` as the basis for a failure-mode discussion subsection.")
    lines.append("- Report both event success (`taem_reached`) and continuous proximity (`taem_lb_score`) to avoid collapsing near-success and true latch into the same class.")

    (outdir / "q1_report.md").write_text("\n".join(lines), encoding="utf-8")



def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True, help="Path to summary_by_vehicle.csv")
    p.add_argument("--vehicle", required=True, help="Path to taem_compare_by_vehicle.csv")
    p.add_argument("--run", required=True, help="Path to taem_compare_by_run.csv")
    p.add_argument("--outdir", required=True, help="Output directory")
    p.add_argument("--h_tol", type=float, default=TAEM_DEFAULTS["h_tol"])
    p.add_argument("--v_tol", type=float, default=TAEM_DEFAULTS["v_tol"])
    p.add_argument("--sgo_tol", type=float, default=TAEM_DEFAULTS["sgo_tol"])
    p.add_argument("--psi_tol_deg", type=float, default=TAEM_DEFAULTS["psi_tol_deg"])
    return p.parse_args()



def main():
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    summary_df = pd.read_csv(args.summary)
    vehicle_df = pd.read_csv(args.vehicle)
    run_df = pd.read_csv(args.run)

    psi_tol_rad = np.deg2rad(args.psi_tol_deg)

    vehicle_metrics = build_vehicle_metrics(summary_df, vehicle_df, args.h_tol, args.v_tol, args.sgo_tol, psi_tol_rad)
    failure_df = build_failure_modes(vehicle_metrics, vehicle_df, args.h_tol, args.v_tol, args.sgo_tol, psi_tol_rad)
    run_out = run_df.copy()
    run_out["h_tol_m"] = args.h_tol
    run_out["v_tol_mps"] = args.v_tol
    run_out["sgo_tol_m"] = args.sgo_tol
    run_out["psi_tol_deg"] = args.psi_tol_deg

    vehicle_metrics.to_csv(outdir / "q1_vehicle_metrics.csv", index=False)
    failure_df.to_csv(outdir / "q1_failure_modes.csv", index=False)
    run_out.to_csv(outdir / "q1_run_summary.csv", index=False)
    write_markdown_report(outdir, run_out, vehicle_metrics, failure_df, args.h_tol, args.v_tol, args.sgo_tol, args.psi_tol_deg)

    print("[OK] Wrote:")
    for name in ["q1_vehicle_metrics.csv", "q1_failure_modes.csv", "q1_run_summary.csv", "q1_report.md"]:
        print(f"  - {outdir / name}")


if __name__ == "__main__":
    main()
