# -*- coding: utf-8 -*-
"""
Phase 2 / B5B-F failure diagnosis for the conservative Monte Carlo pilot.

Purpose
-------
Post-process the B5B Monte Carlo pilot outputs and diagnose why the
conservative U3 pilot was classified as fragile. The script does not run any
simulation. It reads the existing B5B by-vehicle / by-case CSVs, then produces
failure-mode, marginal, bin-level, and manuscript-oriented summaries.

Default inputs
--------------
store/data_saved/phase2_B5B_mc_conservative_u3_report/phase2_B5B_mc_by_vehicle_all.csv
store/data_saved/phase2_B5B_mc_conservative_u3_report/phase2_B5B_mc_by_case_all.csv
store/data_saved/phase2_B5B_mc_conservative_u3_report/phase2_B5B_mc_case_summary.csv
store/data_saved/phase2_B5B_mc_conservative_u3_report/phase2_B5B_mc_by_vehicle_role_summary.csv

Default output directory
------------------------
store/data_saved/phase2_B5B_failure_diagnosis_report
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def _as_path(x: str | Path) -> Path:
    return Path(x).expanduser().resolve() if str(x) else Path("")


def _pick_col(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    # fuzzy fallback: require all tokens in column name
    for cand in candidates:
        toks = [t for t in re.split(r"[^a-zA-Z0-9]+", cand.lower()) if t]
        for c in df.columns:
            cl = c.lower()
            if all(t in cl for t in toks):
                return c
    return None


def _to_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.fillna(False)
    ss = s.astype(str).str.strip().str.lower()
    return ss.isin(["true", "1", "yes", "y", "pass", "passed"])


def _safe_num(s: pd.Series | None) -> pd.Series:
    if s is None:
        return pd.Series(dtype=float)
    if s.dtype == bool:
        return s.astype(float)
    return pd.to_numeric(s, errors="coerce")


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1 + z**2 / n
    center = (phat + z**2 / (2 * n)) / denom
    half = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * n)) / n) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _fmt_ci(k: int, n: int) -> str:
    lo, hi = _wilson_ci(k, n)
    return f"[{lo:.3f},{hi:.3f}]"


def _rate(k: int, n: int) -> float:
    return float(k) / float(n) if n else float("nan")


def _str_contains_any(row: pd.Series, cols: list[str | None], patterns: list[str]) -> bool:
    text_parts = []
    for c in cols:
        if c and c in row.index and pd.notna(row[c]):
            text_parts.append(str(row[c]).lower())
    text = " | ".join(text_parts)
    return any(p.lower() in text for p in patterns)


def _infer_pass(row: pd.Series, decision_col: str | None, label_col: str | None, end_reason_col: str | None) -> bool:
    vals = []
    for c in [decision_col, label_col, end_reason_col]:
        if c and c in row.index and pd.notna(row[c]):
            vals.append(str(row[c]).lower())
    text = " | ".join(vals)
    if "pass_strict" in text or "clean taem success" in text or "taem_dwell_reached" in text:
        # Do not allow a simultaneously explicit FAIL decision to be overridden.
        if decision_col and decision_col in row.index and "fail" in str(row[decision_col]).lower():
            return False
        return True
    return False


def _infer_close_escape(row: pd.Series, close_cols: list[str], label_col: str | None, end_reason_col: str | None) -> bool:
    for c in close_cols:
        if c in row.index:
            try:
                if bool(_to_bool_series(pd.Series([row[c]])).iloc[0]):
                    return True
            except Exception:
                pass
    return _str_contains_any(row, [label_col, end_reason_col], ["close-pass", "close_pass", "escape", "range-closure", "range closure"])


def _failure_class(row: pd.Series, passed: bool, close_escape: bool, cols: dict[str, str | None]) -> str:
    if passed:
        return "Clean TAEM success"

    label_col = cols.get("label")
    end_col = cols.get("end_reason")
    label = str(row[label_col]) if label_col and label_col in row.index and pd.notna(row[label_col]) else ""
    end_reason = str(row[end_col]) if end_col and end_col in row.index and pd.notna(row[end_col]) else ""
    text = f"{label} | {end_reason}".lower()

    if close_escape or "close" in text or "escape" in text:
        if "range" in text or "closure" in text:
            return "Close-pass escape / range-closure failure"
        return "Close-pass escape"

    sgo_min_col = cols.get("sgo_min_abs")
    sgo_final_col = cols.get("sgo_final_err")
    h_final_col = cols.get("h_final_err")
    v_final_col = cols.get("v_final_err")
    sgo_min = pd.to_numeric(row.get(sgo_min_col), errors="coerce") if sgo_min_col else np.nan
    sgo_final = pd.to_numeric(row.get(sgo_final_col), errors="coerce") if sgo_final_col else np.nan
    h_final = pd.to_numeric(row.get(h_final_col), errors="coerce") if h_final_col else np.nan
    v_final = pd.to_numeric(row.get(v_final_col), errors="coerce") if v_final_col else np.nan

    # Heuristic categories useful for TAEM debugging.
    if np.isfinite(sgo_min) and np.isfinite(sgo_final) and abs(sgo_min) < 30000 and abs(sgo_final) > 50000:
        return "Range rebound / late escape"
    if np.isfinite(sgo_final) and abs(sgo_final) > 50000:
        return "Range-closure failure"
    if np.isfinite(h_final) and abs(h_final) > 3000 and np.isfinite(v_final) and abs(v_final) <= 150:
        return "Altitude-boundary failure"
    if np.isfinite(v_final) and abs(v_final) > 150:
        return "Velocity/energy failure"
    return "Unclassified TAEM failure"


def _bin_velocity(v: float) -> str:
    if not np.isfinite(v):
        return "v=NA"
    if v <= -40:
        return "[-50,-40]"
    if v <= -30:
        return "(-40,-30]"
    if v <= -20:
        return "(-30,-20]"
    if v <= -10:
        return "(-20,-10]"
    if v <= 0:
        return "(-10,0]"
    if v <= 10:
        return "(0,+10]"
    if v <= 20:
        return "(+10,+20]"
    if v <= 30:
        return "(+20,+30]"
    if v <= 40:
        return "(+30,+40]"
    if v <= 50:
        return "(+40,+50]"
    return ">+50"


def _bin_height(h: float) -> str:
    if not np.isfinite(h):
        return "h=NA"
    if h <= -250:
        return "[-500,-250]"
    if h < 250:
        return "(-250,+250)"
    return "[+250,+500]"


def _summarize_group(df: pd.DataFrame, group_cols: list[str], pass_col: str = "_passed", close_col: str = "_close_escape") -> pd.DataFrame:
    rows = []
    if not group_cols:
        iterable = [("ALL", df)]
    else:
        iterable = df.groupby(group_cols, dropna=False)
    for key, g in iterable:
        n = int(len(g))
        k = int(g[pass_col].sum()) if n else 0
        c = int(g[close_col].sum()) if n else 0
        row: dict[str, Any] = {}
        if group_cols:
            if not isinstance(key, tuple):
                key = (key,)
            for gc, val in zip(group_cols, key):
                row[gc] = val
        else:
            row["group"] = key
        lo, hi = _wilson_ci(k, n)
        row.update({
            "n": n,
            "pass": k,
            "fail": n - k,
            "pass_rate": _rate(k, n),
            "pass_ci95_lo": lo,
            "pass_ci95_hi": hi,
            "close_escape": c,
            "close_escape_rate": _rate(c, n),
        })
        rows.append(row)
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# Main diagnosis logic
# -----------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    root = Path.cwd()
    vehicle_csv = Path(args.vehicle_csv)
    case_csv = Path(args.case_csv) if args.case_csv else None
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not vehicle_csv.exists():
        raise FileNotFoundError(f"vehicle CSV not found: {vehicle_csv}")

    df = pd.read_csv(vehicle_csv)
    if df.empty:
        raise RuntimeError(f"vehicle CSV is empty: {vehicle_csv}")

    # Column detection.
    col_case = _pick_col(df, ["case_id", "mc_case_id", "case", "run_id", "scenario_id"])
    col_h = _pick_col(df, ["height_delta_m", "h_delta_m", "delta_h_m", "height_perturb_m"])
    col_v = _pick_col(df, ["velocity_delta_mps", "v_delta_mps", "delta_v_mps", "velocity_perturb_mps"])
    col_vehicle = _pick_col(df, ["vehicle_id", "mis_id", "missile_id", "id"])
    col_role = _pick_col(df, ["phase2_role", "role", "Phase2Role"])
    col_decision = _pick_col(df, ["decision", "b1_vehicle_decision", "vehicle_decision"])
    col_label = _pick_col(df, ["label", "failure_label", "classification"])
    col_end = _pick_col(df, ["end_reason", "end_reason_last", "last_end_reason"])
    col_close_l = _pick_col(df, ["last_close_pass_escape", "close_pass_escape", "any_close_pass_escape"])
    col_sgo_min = _pick_col(df, ["taem_s_go_err_min_abs", "taem_sgo_err_min_abs", "sgo_min_abs"])
    col_sgo_final_err = _pick_col(df, ["taem_s_go_err_final", "taem_sgo_err_final"])
    col_h_final_err = _pick_col(df, ["taem_h_err_final", "h_err_final"])
    col_v_final_err = _pick_col(df, ["taem_v_err_final", "v_err_final"])
    col_sgo_min_state = _pick_col(df, ["s_go_min", "sgo_min"])
    col_sgo_final_state = _pick_col(df, ["s_go_final", "sgo_final"])
    col_dwell_s = _pick_col(df, ["taem_dwell_s_final_logged", "taem_dwell_s_max_logged", "taem_dwell_s"])
    col_dwell_count = _pick_col(df, ["taem_dwell_count_final_logged", "taem_dwell_count_max_logged", "taem_dwell_count"])

    cols = {
        "case": col_case,
        "h": col_h,
        "v": col_v,
        "vehicle": col_vehicle,
        "role": col_role,
        "decision": col_decision,
        "label": col_label,
        "end_reason": col_end,
        "close": col_close_l,
        "sgo_min_abs": col_sgo_min,
        "sgo_final_err": col_sgo_final_err,
        "h_final_err": col_h_final_err,
        "v_final_err": col_v_final_err,
        "sgo_min_state": col_sgo_min_state,
        "sgo_final_state": col_sgo_final_state,
        "dwell_s": col_dwell_s,
        "dwell_count": col_dwell_count,
    }

    close_cols = [c for c in [col_close_l] if c]
    df["_passed"] = df.apply(lambda r: _infer_pass(r, col_decision, col_label, col_end), axis=1)
    df["_close_escape"] = df.apply(lambda r: _infer_close_escape(r, close_cols, col_label, col_end), axis=1)
    df["_failure_class"] = df.apply(lambda r: _failure_class(r, bool(r["_passed"]), bool(r["_close_escape"]), cols), axis=1)

    if col_h:
        df["_height_delta_m"] = _safe_num(df[col_h])
        df["_height_bin"] = df["_height_delta_m"].apply(_bin_height)
    else:
        df["_height_delta_m"] = np.nan
        df["_height_bin"] = "h=NA"
    if col_v:
        df["_velocity_delta_mps"] = _safe_num(df[col_v])
        df["_velocity_bin"] = df["_velocity_delta_mps"].apply(_bin_velocity)
    else:
        df["_velocity_delta_mps"] = np.nan
        df["_velocity_bin"] = "v=NA"

    if col_vehicle:
        df["_vehicle_id"] = df[col_vehicle]
    else:
        df["_vehicle_id"] = "unknown"

    # Summaries.
    n_rows = int(len(df))
    n_pass = int(df["_passed"].sum())
    n_close = int(df["_close_escape"].sum())
    vehicle_rate = _rate(n_pass, n_rows)

    case_summary = None
    if col_case:
        case_summary = _summarize_group(df, [col_case])
        # Add h/v means for easier inspection.
        hv = df.groupby(col_case, dropna=False).agg(
            height_delta_m=("_height_delta_m", "mean"),
            velocity_delta_mps=("_velocity_delta_mps", "mean"),
            close_escape_any=("_close_escape", "max"),
        ).reset_index()
        case_summary = case_summary.merge(hv, on=col_case, how="left")
    else:
        case_summary = _summarize_group(df, [])

    by_velocity_bin = _summarize_group(df, ["_velocity_bin"])
    by_height_bin = _summarize_group(df, ["_height_bin"])
    by_hv_bin = _summarize_group(df, ["_height_bin", "_velocity_bin"])
    by_vehicle = _summarize_group(df, ["_vehicle_id"])
    if col_role:
        by_role = _summarize_group(df, [col_role])
    else:
        by_role = pd.DataFrame()
    failure_counts = df["_failure_class"].value_counts(dropna=False).rename_axis("failure_class").reset_index(name="n")
    failure_counts["rate"] = failure_counts["n"] / len(df)

    fail_rows = df[~df["_passed"]].copy()

    # Candidate safe envelope summaries.
    v_threshold_rows = []
    if col_v:
        for thr in [-50, -40, -30, -20, -10, 0, 10, 20, 30, 40, 50]:
            g = df[df["_velocity_delta_mps"] <= thr]
            if len(g) == 0:
                continue
            k = int(g["_passed"].sum())
            n = int(len(g))
            lo, hi = _wilson_ci(k, n)
            v_threshold_rows.append({
                "velocity_upper_mps": thr,
                "n_vehicle_rows": n,
                "pass": k,
                "fail": n-k,
                "pass_rate": _rate(k, n),
                "ci95_lo": lo,
                "ci95_hi": hi,
                "close_escape": int(g["_close_escape"].sum()),
            })
    v_threshold_df = pd.DataFrame(v_threshold_rows)

    # Diagnostic interpretation.
    close_fail = int(fail_rows["_close_escape"].sum()) if len(fail_rows) else 0
    total_fail = int(len(fail_rows))
    close_fail_rate = _rate(close_fail, total_fail)
    dominant_close = total_fail > 0 and close_fail_rate >= 0.60

    worst_v = None
    if not by_velocity_bin.empty:
        tmp = by_velocity_bin.sort_values(["pass_rate", "n"], ascending=[True, False])
        worst_v = tmp.iloc[0].to_dict()
    worst_h = None
    if not by_height_bin.empty:
        tmp = by_height_bin.sort_values(["pass_rate", "n"], ascending=[True, False])
        worst_h = tmp.iloc[0].to_dict()

    # Conservative decision label.
    case_pass_rate = float("nan")
    case_n = 0
    case_pass_n = 0
    if case_summary is not None and not case_summary.empty and "pass_rate" in case_summary:
        # A case passes only when all its vehicle rows pass.
        case_n = int(len(case_summary))
        case_pass_n = int((case_summary["pass_rate"] >= 0.999999).sum())
        case_pass_rate = _rate(case_pass_n, case_n)

    if case_pass_rate >= 0.80 and vehicle_rate >= 0.85 and not dominant_close:
        decision = "B5B_F_LOCAL_U3_SUPPORT"
    elif dominant_close:
        decision = "B5B_F_CLOSE_PASS_DOMINATED_FRAGILITY"
    else:
        decision = "B5B_F_MIXED_FRAGILITY"

    # Write CSV outputs.
    enriched_cols = [c for c in [col_case, col_h, col_v, col_vehicle, col_role, col_decision, col_label, col_end, col_close_l,
                                  col_dwell_s, col_dwell_count, col_sgo_min, col_h_final_err, col_v_final_err,
                                  col_sgo_final_err, col_sgo_min_state, col_sgo_final_state] if c]
    extra_cols = ["_passed", "_close_escape", "_failure_class", "_height_bin", "_velocity_bin"]
    df[enriched_cols + extra_cols].to_csv(outdir / "b5b_enriched_by_vehicle.csv", index=False)
    fail_rows[enriched_cols + extra_cols].to_csv(outdir / "b5b_failure_rows.csv", index=False)
    case_summary.to_csv(outdir / "b5b_case_failure_summary.csv", index=False)
    by_velocity_bin.to_csv(outdir / "b5b_marginal_by_velocity_bin.csv", index=False)
    by_height_bin.to_csv(outdir / "b5b_marginal_by_height_bin.csv", index=False)
    by_hv_bin.to_csv(outdir / "b5b_marginal_by_height_velocity_bin.csv", index=False)
    by_vehicle.to_csv(outdir / "b5b_marginal_by_vehicle.csv", index=False)
    if not by_role.empty:
        by_role.to_csv(outdir / "b5b_marginal_by_role.csv", index=False)
    failure_counts.to_csv(outdir / "b5b_failure_mode_counts.csv", index=False)
    v_threshold_df.to_csv(outdir / "b5b_velocity_upper_threshold_candidates.csv", index=False)

    # Optional: copy/compare original case summaries if present.
    original_case_summary_info = None
    if case_csv and case_csv.exists():
        try:
            case_df = pd.read_csv(case_csv)
            original_case_summary_info = {"rows": int(len(case_df)), "columns": list(case_df.columns)}
            case_df.to_csv(outdir / "b5b_original_by_case_all_copy.csv", index=False)
        except Exception as exc:
            original_case_summary_info = {"error": str(exc)}

    # Text report.
    lines: list[str] = []
    lines.append("PHASE 2 / B5B-F — MONTE CARLO FAILURE DIAGNOSIS")
    lines.append("=" * 72)
    lines.append(f"vehicle_csv          : {vehicle_csv}")
    lines.append(f"case_csv             : {case_csv if case_csv else 'not supplied'}")
    lines.append(f"rows                 : {n_rows}")
    lines.append(f"decision             : {decision}")
    lines.append(f"vehicle_pass_rate    : {n_pass}/{n_rows} = {vehicle_rate:.6f} CI95={_fmt_ci(n_pass, n_rows)}")
    lines.append(f"case_pass_rate       : {case_pass_n}/{case_n} = {case_pass_rate:.6f} CI95={_fmt_ci(case_pass_n, case_n) if case_n else '[nan,nan]'}")
    lines.append(f"failure_rows         : {total_fail}")
    lines.append(f"close_escape_failures: {close_fail}/{total_fail} = {close_fail_rate:.6f}" if total_fail else "close_escape_failures: 0/0")
    lines.append("")

    lines.append("[COLUMN MAP]")
    for k, v in cols.items():
        lines.append(f"  {k:16s}: {v}")
    lines.append("")

    lines.append("[MARGINAL BY VELOCITY BIN]")
    for _, r in by_velocity_bin.sort_values("_velocity_bin").iterrows():
        lines.append(
            f"{r['_velocity_bin']:>12s} | pass={int(r['pass'])}/{int(r['n'])} "
            f"rate={r['pass_rate']:.3f} CI95=[{r['pass_ci95_lo']:.3f},{r['pass_ci95_hi']:.3f}] "
            f"close_escape={int(r['close_escape'])}"
        )
    lines.append("")

    lines.append("[MARGINAL BY HEIGHT BIN]")
    for _, r in by_height_bin.sort_values("_height_bin").iterrows():
        lines.append(
            f"{r['_height_bin']:>14s} | pass={int(r['pass'])}/{int(r['n'])} "
            f"rate={r['pass_rate']:.3f} CI95=[{r['pass_ci95_lo']:.3f},{r['pass_ci95_hi']:.3f}] "
            f"close_escape={int(r['close_escape'])}"
        )
    lines.append("")

    lines.append("[MARGINAL BY VEHICLE]")
    for _, r in by_vehicle.sort_values("_vehicle_id").iterrows():
        lines.append(
            f"vehicle={r['_vehicle_id']} | pass={int(r['pass'])}/{int(r['n'])} "
            f"rate={r['pass_rate']:.3f} CI95=[{r['pass_ci95_lo']:.3f},{r['pass_ci95_hi']:.3f}] "
            f"close_escape={int(r['close_escape'])}"
        )
    lines.append("")

    if not by_role.empty:
        lines.append("[MARGINAL BY ROLE]")
        for _, r in by_role.iterrows():
            role_val = str(r[col_role])
            lines.append(
                f"role={role_val} | pass={int(r['pass'])}/{int(r['n'])} "
                f"rate={r['pass_rate']:.3f} CI95=[{r['pass_ci95_lo']:.3f},{r['pass_ci95_hi']:.3f}] "
                f"close_escape={int(r['close_escape'])}"
            )
        lines.append("")

    lines.append("[FAILURE MODE COUNTS]")
    for _, r in failure_counts.iterrows():
        lines.append(f"{r['failure_class']} | n={int(r['n'])} rate={r['rate']:.3f}")
    lines.append("")

    lines.append("[WORST BINS]")
    if worst_v:
        lines.append(f"Worst velocity bin: {worst_v.get('_velocity_bin')} | pass_rate={worst_v.get('pass_rate'):.3f} | n={int(worst_v.get('n'))}")
    if worst_h:
        lines.append(f"Worst height bin  : {worst_h.get('_height_bin')} | pass_rate={worst_h.get('pass_rate'):.3f} | n={int(worst_h.get('n'))}")
    lines.append("")

    lines.append("[VELOCITY UPPER-BOUND CANDIDATES]")
    if not v_threshold_df.empty:
        for _, r in v_threshold_df.iterrows():
            lines.append(
                f"v <= {r['velocity_upper_mps']:+.0f} m/s | pass={int(r['pass'])}/{int(r['n_vehicle_rows'])} "
                f"rate={r['pass_rate']:.3f} CI95=[{r['ci95_lo']:.3f},{r['ci95_hi']:.3f}] "
                f"close_escape={int(r['close_escape'])}"
            )
    else:
        lines.append("No velocity column available for threshold candidates.")
    lines.append("")

    lines.append("[FAILED ROWS — COMPACT]")
    compact_cols = [c for c in [col_case, col_h, col_v, col_vehicle, col_role, col_decision, col_label, col_end, col_close_l,
                                col_dwell_s, col_dwell_count, col_sgo_min, col_h_final_err, col_v_final_err,
                                col_sgo_final_err, col_sgo_min_state, col_sgo_final_state, "_failure_class"] if c]
    if fail_rows.empty:
        lines.append("No failed vehicle rows.")
    else:
        # Limit in text, full CSV is written separately.
        lines.append(fail_rows[compact_cols].to_string(index=False, max_rows=80))
    lines.append("")

    lines.append("[INTERPRETATION]")
    if dominant_close:
        lines.append("- Monte Carlo fragility is dominated by close-pass / range-closure escape failures.")
    else:
        lines.append("- Monte Carlo failures are mixed; close-pass escape is not the only observed mode.")
    lines.append("- This diagnosis supports a cautious U3/U4 interpretation: deterministic role-distinct success does not automatically transfer to stochastic perturbations.")
    if worst_v:
        lines.append(f"- The weakest sampled velocity sector is {worst_v.get('_velocity_bin')} with pass_rate={worst_v.get('pass_rate'):.3f}.")
    if worst_h:
        lines.append(f"- The weakest sampled height sector is {worst_h.get('_height_bin')} with pass_rate={worst_h.get('pass_rate'):.3f}.")
    lines.append("- Do not use this B5B pilot to claim U4 universality.")
    lines.append("- Recommended next steps: either define a narrower validated local envelope, or implement range-closure recovery before broader Monte Carlo.")
    lines.append("")

    lines.append("[GENERATED FILES]")
    for name in [
        "b5b_enriched_by_vehicle.csv",
        "b5b_failure_rows.csv",
        "b5b_case_failure_summary.csv",
        "b5b_marginal_by_velocity_bin.csv",
        "b5b_marginal_by_height_bin.csv",
        "b5b_marginal_by_height_velocity_bin.csv",
        "b5b_marginal_by_vehicle.csv",
        "b5b_failure_mode_counts.csv",
        "b5b_velocity_upper_threshold_candidates.csv",
        "b5b_failure_diagnosis_summary.json",
    ]:
        lines.append(f"  - {outdir / name}")

    summary_txt = outdir / "b5b_failure_diagnosis_summary.txt"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")

    summary_json = {
        "vehicle_csv": str(vehicle_csv),
        "case_csv": str(case_csv) if case_csv else None,
        "rows": n_rows,
        "decision": decision,
        "vehicle_pass": n_pass,
        "vehicle_total": n_rows,
        "vehicle_pass_rate": vehicle_rate,
        "case_pass": case_pass_n,
        "case_total": case_n,
        "case_pass_rate": case_pass_rate,
        "failure_rows": total_fail,
        "close_escape_failures": close_fail,
        "close_escape_failure_rate": close_fail_rate,
        "dominant_close_pass": dominant_close,
        "worst_velocity_bin": worst_v,
        "worst_height_bin": worst_h,
        "column_map": cols,
        "original_case_summary_info": original_case_summary_info,
    }
    (outdir / "b5b_failure_diagnosis_summary.json").write_text(json.dumps(summary_json, indent=2, ensure_ascii=False), encoding="utf-8")

    publication_note = outdir / "b5b_failure_diagnosis_for_manuscript.txt"
    pub_lines = [
        "B5B-F manuscript interpretation", "=" * 48, "",
        "The conservative U3 Monte Carlo pilot should be interpreted as a fragility diagnosis rather than a universality demonstration.",
        f"The vehicle-level pass rate was {n_pass}/{n_rows} ({vehicle_rate:.3f}), while the case-level 3/3 pass rate was {case_pass_n}/{case_n} ({case_pass_rate:.3f}).",
        f"Among failed vehicle rows, close-pass/range-closure behavior accounted for {close_fail}/{total_fail} failures.",
        "Therefore, the current guidance/evaluation stack supports deterministic and bounded role-distinct transfer, but stochastic robustness remains limited by terminal range-closure fragility.",
        "A U4-style universality claim should not be made until either the validated perturbation envelope is narrowed and statistically confirmed, or the terminal range-closure mechanism is improved and retested.",
    ]
    publication_note.write_text("\n".join(pub_lines), encoding="utf-8")

    print("\n".join(lines))
    print("")
    print("[OK] wrote:", summary_txt)
    print("[OK] wrote:", outdir / "b5b_failure_diagnosis_summary.json")
    print("[OK] wrote:", publication_note)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 B5B-F Monte Carlo failure diagnosis")
    parser.add_argument(
        "--vehicle-csv",
        default=r"store\data_saved\phase2_B5B_mc_conservative_u3_report\phase2_B5B_mc_by_vehicle_all.csv",
        help="B5B by-vehicle CSV",
    )
    parser.add_argument(
        "--case-csv",
        default=r"store\data_saved\phase2_B5B_mc_conservative_u3_report\phase2_B5B_mc_by_case_all.csv",
        help="Optional B5B by-case CSV",
    )
    parser.add_argument(
        "--outdir",
        default=r"store\data_saved\phase2_B5B_failure_diagnosis_report",
        help="Output directory",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
