#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B3B-post dwell sensitivity

Post-processes already generated exact-single sequential campaign CSVs and checks
whether the logged TAEM dwell evidence supports dwell requirements N=3,4,5.

Important interpretation:
- If a simulation terminates immediately at the original dwell latch (usually 3 s
  or 3 count), post-processing cannot prove that the same trajectory would have
  stayed in-box for N=4 or N=5. Such cases are labelled INCONCLUSIVE_LATCH_TERMINATED.
- This script is therefore a fast screening step, not a replacement for a rerun
  with a larger guidance/event dwell threshold.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

TRUE_STRINGS = {"1", "true", "yes", "y", "t"}
FALSE_STRINGS = {"0", "false", "no", "n", "f", "nan", "none", ""}

SUCCESS_COLS = [
    "taem_success_latched",
    "taem_reached_ever",
    "taem_reached_event",
    "taem_reached",
    "taem_in_box",
]
DWELL_S_COLS = [
    "taem_dwell_s",
    "taem_dwell_time_s",
    "taem_dwell_sec",
    "taem_dwell_seconds",
]
DWELL_COUNT_COLS = [
    "taem_dwell_count",
    "taem_dwell_steps",
]
ERR_COLS = ["taem_h_err", "taem_v_err", "taem_s_go_err", "taem_sgo_err"]
GROUP_CANDIDATES = [
    "campaign", "case", "case_id", "run_id", "scenario", "scenario_id",
    "spread_deg", "heading_spread_deg", "b3a_spread_deg", "B3A_spread_deg",
    "heading_delta_deg", "B2R_heading_delta_deg", "role", "Phase2Role",
]


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return _safe_num(s).fillna(0.0) > 0.5
    lower = s.astype(str).str.strip().str.lower()
    return lower.isin(TRUE_STRINGS)


def _last_nonnull(g: pd.DataFrame, col: str, default: Any = None) -> Any:
    if col not in g.columns:
        return default
    s = g[col].dropna()
    if len(s) == 0:
        return default
    return s.iloc[-1]


def _max_numeric(g: pd.DataFrame, cols: Iterable[str]) -> Tuple[float, Optional[str]]:
    best = -math.inf
    best_col = None
    for c in cols:
        if c not in g.columns:
            continue
        vals = _safe_num(g[c]).to_numpy(dtype=float)
        if np.isfinite(vals).any():
            m = float(np.nanmax(vals))
            if m > best:
                best = m
                best_col = c
    if best == -math.inf:
        return (float("nan"), None)
    return (best, best_col)


def _pick_time_col(df: pd.DataFrame) -> str:
    for c in ("global_t", "t_local", "t"):
        if c in df.columns:
            return c
    return "__row_index__"


def _compute_in_box_from_errors(g: pd.DataFrame, tol_h: float, tol_v: float, tol_sgo: float) -> Optional[pd.Series]:
    have = False
    mask = pd.Series([True] * len(g), index=g.index)
    if "taem_h_err" in g.columns:
        have = True
        mask &= _safe_num(g["taem_h_err"]).abs() <= float(tol_h)
    if "taem_v_err" in g.columns:
        have = True
        mask &= _safe_num(g["taem_v_err"]).abs() <= float(tol_v)
    sgo_col = "taem_s_go_err" if "taem_s_go_err" in g.columns else ("taem_sgo_err" if "taem_sgo_err" in g.columns else None)
    if sgo_col is not None:
        have = True
        mask &= _safe_num(g[sgo_col]).abs() <= float(tol_sgo)
    return mask if have else None


def _computed_dwell_max(g: pd.DataFrame, tcol: str, tol_h: float, tol_v: float, tol_sgo: float) -> Tuple[float, float, str]:
    if len(g) == 0:
        return (0.0, 0.0, "empty")
    if tcol == "__row_index__":
        t = np.arange(len(g), dtype=float)
    else:
        t = _safe_num(g[tcol]).to_numpy(dtype=float)
        if not np.isfinite(t).any():
            t = np.arange(len(g), dtype=float)
    if "taem_in_box" in g.columns:
        in_box = _bool_series(g, "taem_in_box").to_numpy(dtype=bool)
        source = "taem_in_box"
    else:
        comp = _compute_in_box_from_errors(g, tol_h, tol_v, tol_sgo)
        if comp is None:
            return (0.0, 0.0, "missing_in_box_and_errors")
        in_box = comp.to_numpy(dtype=bool)
        source = "computed_from_errors"

    if len(t) <= 1:
        dt = np.array([0.0])
    else:
        diffs = np.diff(t)
        med = float(np.nanmedian(diffs[np.isfinite(diffs)])) if np.isfinite(diffs).any() else 0.0
        dt = np.append(diffs, med)
        dt = np.where(np.isfinite(dt) & (dt >= 0), dt, 0.0)

    total = float(np.nansum(dt[in_box])) if len(dt) == len(in_box) else 0.0
    cur = 0.0
    max_seg = 0.0
    for flag, dti in zip(in_box, dt):
        if bool(flag):
            cur += float(dti)
            max_seg = max(max_seg, cur)
        else:
            cur = 0.0
    return (total, float(max_seg), source)


def _success_any(g: pd.DataFrame) -> bool:
    for c in SUCCESS_COLS:
        if c in g.columns and bool(_bool_series(g, c).any()):
            return True
    return False


def _last_close_escape(g: pd.DataFrame) -> bool:
    for c in ("close_pass_escape", "close_pass_escape_latched"):
        if c in g.columns:
            s = _bool_series(g, c)
            if len(s):
                return bool(s.iloc[-1])
    return False


def _group_keys(df: pd.DataFrame) -> List[str]:
    keys: List[str] = []
    for c in GROUP_CANDIDATES:
        if c in df.columns and c != "mis_id":
            # Keep useful run/case columns, but skip columns that are all null.
            if df[c].dropna().nunique() > 0:
                keys.append(c)
    return keys


def _case_label(row: pd.Series, keys: List[str]) -> str:
    if not keys:
        return "default"
    parts = []
    for k in keys:
        v = row.get(k, None)
        if pd.isna(v):
            continue
        parts.append(f"{k}={v}")
    return ";".join(parts) if parts else "default"


def analyze_csv(path: Path, label: str, dwell_reqs: List[float], tol_h: float, tol_v: float, tol_sgo: float) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    df = pd.read_csv(path)
    if "mis_id" not in df.columns:
        df["mis_id"] = 0
    tcol = _pick_time_col(df)
    if tcol == "__row_index__":
        df[tcol] = np.arange(len(df), dtype=float)

    keys = _group_keys(df)
    group_cols = keys + ["mis_id"]
    rows: List[Dict[str, Any]] = []
    log_lines: List[str] = []
    log_lines.append(f"INPUT: {label}")
    log_lines.append(f"  csv: {path}")
    log_lines.append(f"  rows: {len(df)}")
    log_lines.append(f"  group_keys: {keys if keys else ['<none>']}")
    log_lines.append(f"  dwell_reqs: {dwell_reqs}")

    for group_key, g in df.groupby(group_cols, dropna=False):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)
        group_map = dict(zip(group_cols, group_key))
        g = g.sort_values(tcol).reset_index(drop=True)
        mid = int(group_map.get("mis_id", 0))
        case_vals = {k: group_map.get(k) for k in keys}
        case_label = ";".join(f"{k}={case_vals[k]}" for k in keys) if keys else "default"

        success_any = _success_any(g)
        close_last = _last_close_escape(g)
        end_reason_last = str(_last_nonnull(g, "end_reason", ""))
        guide_phase_last = str(_last_nonnull(g, "guide_phase", ""))
        dwell_s_max, dwell_s_col = _max_numeric(g, DWELL_S_COLS)
        dwell_count_max, dwell_count_col = _max_numeric(g, DWELL_COUNT_COLS)
        comp_total, comp_max, comp_source = _computed_dwell_max(g, tcol, tol_h, tol_v, tol_sgo)

        # Primary evidence: logged dwell seconds if present, otherwise computed dwell max.
        evidence_candidates = []
        if np.isfinite(dwell_s_max):
            evidence_candidates.append(dwell_s_max)
        if np.isfinite(comp_max):
            evidence_candidates.append(comp_max)
        evidence_max = max(evidence_candidates) if evidence_candidates else 0.0

        for req in dwell_reqs:
            eps = 1e-9
            if success_any and (not close_last) and evidence_max + eps >= req:
                decision = "PASS_POST_EVIDENCE"
            elif success_any and (not close_last) and "taem_dwell_reached" in end_reason_last and evidence_max > 0 and req > evidence_max + eps:
                decision = "INCONCLUSIVE_LATCH_TERMINATED_AT_LOWER_DWELL"
            elif success_any and evidence_max + eps >= req:
                decision = "PASS_WITH_WARNING_FLAGS"
            else:
                decision = "FAIL_POST_EVIDENCE"

            row: Dict[str, Any] = {
                "input_label": label,
                "csv": str(path),
                "case_label": case_label,
                **case_vals,
                "mis_id": mid,
                "dwell_req_s": float(req),
                "decision": decision,
                "success_any": bool(success_any),
                "last_close_pass_escape": bool(close_last),
                "end_reason_last": end_reason_last,
                "guide_phase_last": guide_phase_last,
                "n_rows": int(len(g)),
                "t_start": float(_safe_num(g[tcol]).iloc[0]) if len(g) else np.nan,
                "t_end": float(_safe_num(g[tcol]).iloc[-1]) if len(g) else np.nan,
                "dwell_evidence_max_s": float(evidence_max),
                "dwell_s_max_logged": float(dwell_s_max) if np.isfinite(dwell_s_max) else np.nan,
                "dwell_s_source": dwell_s_col,
                "dwell_count_max_logged": float(dwell_count_max) if np.isfinite(dwell_count_max) else np.nan,
                "dwell_count_source": dwell_count_col,
                "computed_dwell_total_s": float(comp_total),
                "computed_dwell_max_s": float(comp_max),
                "computed_dwell_source": comp_source,
            }
            # Helpful terminal diagnostics
            for c in ["taem_h_err", "taem_v_err", "taem_s_go_err", "s_go", "height", "velocity", "delta_psi"]:
                if c in g.columns:
                    vals = _safe_num(g[c])
                    row[f"{c}_final"] = float(vals.iloc[-1]) if len(vals) else np.nan
                    row[f"{c}_min_abs"] = float(np.nanmin(np.abs(vals.to_numpy(dtype=float)))) if np.isfinite(vals).any() else np.nan
            rows.append(row)

    by_vehicle = pd.DataFrame(rows)
    agg_rows: List[Dict[str, Any]] = []
    if len(by_vehicle):
        group_agg_cols = ["input_label", "case_label", "dwell_req_s"]
        for (inp, case, req), g in by_vehicle.groupby(group_agg_cols, dropna=False):
            n = len(g)
            n_pass = int((g["decision"] == "PASS_POST_EVIDENCE").sum())
            n_incon = int((g["decision"] == "INCONCLUSIVE_LATCH_TERMINATED_AT_LOWER_DWELL").sum())
            n_fail = int((g["decision"] == "FAIL_POST_EVIDENCE").sum())
            if n_pass == n:
                dec = "PASS_ALL_POST"
            elif n_incon > 0 and n_fail == 0:
                dec = "INCONCLUSIVE_NEEDS_RERUN_WITH_HIGHER_DWELL"
            else:
                dec = "FAIL_OR_MIXED_POST"
            agg_rows.append({
                "input_label": inp,
                "case_label": case,
                "dwell_req_s": float(req),
                "n_vehicles": int(n),
                "n_pass": n_pass,
                "n_inconclusive": n_incon,
                "n_fail": n_fail,
                "decision": dec,
            })
    by_case = pd.DataFrame(agg_rows)
    return by_vehicle, by_case, log_lines


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=None, help="CSV inputs. If omitted, auto-detects B2R and B3A CSVs.")
    ap.add_argument("--labels", nargs="*", default=None, help="Optional labels for inputs.")
    ap.add_argument("--outdir", default=r"store\data_saved\phase2_B3B_post_dwell_report")
    ap.add_argument("--dwell-reqs", nargs="*", type=float, default=[3.0, 4.0, 5.0])
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=150.0)
    ap.add_argument("--tol-sgo", type=float, default=30000.0)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.inputs:
        inputs = [Path(p) for p in args.inputs]
    else:
        candidates = [
            Path(r"store\data_saved\phase2_B2R_role_distinct_combined.csv"),
            Path(r"store\data_saved\phase2_B3A_heading_spread_combined_all.csv"),
        ]
        inputs = [p for p in candidates if p.exists()]
    if not inputs:
        raise SystemExit("[ERR] No input CSVs found. Provide --inputs or run B2R/B3A first.")

    labels: List[str] = []
    if args.labels and len(args.labels) == len(inputs):
        labels = list(args.labels)
    else:
        for p in inputs:
            if "B3A" in p.name or "b3a" in p.name:
                labels.append("B3A_heading_spread")
            elif "B2R" in p.name or "b2r" in p.name:
                labels.append("B2R_role_distinct")
            else:
                labels.append(p.stem)

    all_vehicle = []
    all_case = []
    all_log_lines: List[str] = []
    for p, lab in zip(inputs, labels):
        if not p.exists():
            all_log_lines.append(f"[SKIP] missing input: {p}")
            continue
        bv, bc, log_lines = analyze_csv(p, lab, args.dwell_reqs, args.tol_h, args.tol_v, args.tol_sgo)
        all_vehicle.append(bv)
        all_case.append(bc)
        all_log_lines.extend(log_lines)
        all_log_lines.append("")

    by_vehicle = pd.concat(all_vehicle, ignore_index=True) if all_vehicle else pd.DataFrame()
    by_case = pd.concat(all_case, ignore_index=True) if all_case else pd.DataFrame()

    by_vehicle.to_csv(outdir / "phase2_B3B_post_dwell_by_vehicle.csv", index=False)
    by_case.to_csv(outdir / "phase2_B3B_post_dwell_by_case.csv", index=False)

    lines: List[str] = []
    lines.append("PHASE 2 / B3B-post — DWELL SENSITIVITY FROM EXISTING CSVs")
    lines.append("=" * 72)
    lines.append(f"inputs: {[str(p) for p in inputs]}")
    lines.append(f"dwell_reqs: {args.dwell_reqs}")
    lines.append("")
    lines.append("Interpretation rule:")
    lines.append("  - PASS_ALL_POST: existing logs contain enough dwell evidence for all vehicles.")
    lines.append("  - INCONCLUSIVE_NEEDS_RERUN_WITH_HIGHER_DWELL: trajectory latched/ended at a lower dwell threshold; rerun is required for N=4/5.")
    lines.append("  - FAIL_OR_MIXED_POST: at least one vehicle lacks success/dwell evidence.")
    lines.append("")

    if len(by_case):
        for _, r in by_case.sort_values(["input_label", "case_label", "dwell_req_s"]).iterrows():
            lines.append(
                f"{r['input_label']} | {r['case_label']} | dwell_req={r['dwell_req_s']:g} "
                f"-> {r['decision']} | pass={int(r['n_pass'])}/{int(r['n_vehicles'])} "
                f"inconclusive={int(r['n_inconclusive'])} fail={int(r['n_fail'])}"
            )
    else:
        lines.append("[WARN] No case rows generated.")

    lines.append("")
    lines.append("Recommended next step:")
    if len(by_case) and (by_case["decision"] == "INCONCLUSIVE_NEEDS_RERUN_WITH_HIGHER_DWELL").any():
        lines.append("  Run B3B-run with the guidance/event dwell threshold actually set to 4 and 5.")
    elif len(by_case) and (by_case["decision"] == "PASS_ALL_POST").all():
        lines.append("  Existing CSVs support all requested dwell thresholds; freeze B3B-post and move to tolerance sensitivity.")
    else:
        lines.append("  Inspect failed/mixed cases before rerunning.")

    with open(outdir / "phase2_B3B_post_dwell_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    with open(outdir / "phase2_B3B_post_dwell_summary.json", "w", encoding="utf-8") as f:
        json.dump({
            "inputs": [str(p) for p in inputs],
            "dwell_reqs": args.dwell_reqs,
            "by_case": by_case.to_dict(orient="records") if len(by_case) else [],
        }, f, ensure_ascii=False, indent=2)

    print("\n".join(lines))
    print("")
    print(f"[OK] wrote: {outdir / 'phase2_B3B_post_dwell_summary.txt'}")
    print(f"[OK] wrote: {outdir / 'phase2_B3B_post_dwell_by_vehicle.csv'}")
    print(f"[OK] wrote: {outdir / 'phase2_B3B_post_dwell_by_case.csv'}")


if __name__ == "__main__":
    main()
