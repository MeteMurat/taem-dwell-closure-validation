#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PHASE 2 / B3C — POST-PROCESS TAEM TOLERANCE SENSITIVITY

Purpose
-------
Evaluate whether already-generated exact-single sequential trajectories remain
TAEM-successful when the TAEM tolerance box is changed in post-processing.

Default tolerance grid:
  h_tol_m   = 2000, 3000
  v_tol_mps = 100, 150
  sgo_tol_m = 20000, 30000

Default inputs:
  store/data_saved/phase2_B2R_role_distinct_combined.csv
  store/data_saved/phase2_B3A_heading_spread_combined_all.csv

Outputs:
  phase2_B3C_tolerance_summary.txt
  phase2_B3C_tolerance_summary.json
  phase2_B3C_tolerance_by_case.csv
  phase2_B3C_tolerance_by_vehicle.csv

Notes
-----
- This is post-processing only. It does not modify guidance or rerun dynamics.
- Success is recomputed from taem_*_err columns, not simply copied from
  taem_success_latched.
- A pass requires at least `dwell_count_req` consecutive samples inside the
  selected tolerance box.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd


DEFAULT_INPUTS = [
    r"store\data_saved\phase2_B2R_role_distinct_combined.csv",
    r"store\data_saved\phase2_B3A_heading_spread_combined_all.csv",
]

CASE_COL_CANDIDATES = [
    "campaign_id",
    "case_id",
    "scenario_id",
    "scenario",
    "run_id",
    "spread_id",
    "spread_deg",
    "heading_spread_deg",
    "heading_spread",
    "spread",
    "heading_delta_set",
]

DYNAMIC_COLS = [
    "longitude",
    "latitude",
    "height",
    "velocity",
    "path_angle",
    "heading_angle",
    "s_go",
    "delta_psi",
    "bank_angle",
    "attack_angle",
    "E",
    "L12D",
    "taem_h_err",
    "taem_v_err",
    "taem_s_go_err",
]


def _parse_csv_floats(text: str) -> List[float]:
    vals = []
    for part in str(text).split(","):
        part = part.strip()
        if part:
            vals.append(float(part))
    if not vals:
        raise argparse.ArgumentTypeError("expected comma-separated numbers")
    return vals


def _safe_num(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype(float)
    if s.dtype == object:
        lower = s.astype(str).str.strip().str.lower()
        mapped = lower.map({
            "true": 1.0, "false": 0.0,
            "yes": 1.0, "no": 0.0,
            "y": 1.0, "n": 0.0,
            "1": 1.0, "0": 0.0,
        })
        num = pd.to_numeric(s, errors="coerce")
        return num.where(num.notna(), mapped).astype(float)
    return pd.to_numeric(s, errors="coerce").astype(float)


def _boolish(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def _max_consecutive_true(mask: Sequence[bool]) -> Tuple[int, int | None]:
    best = 0
    cur = 0
    first_best_end = None
    for i, v in enumerate(mask):
        if bool(v):
            cur += 1
            if cur > best:
                best = cur
                first_best_end = i
        else:
            cur = 0
    if first_best_end is None:
        return 0, None
    return best, first_best_end - best + 1


def _first_true_index(mask: Sequence[bool]) -> int | None:
    for i, v in enumerate(mask):
        if bool(v):
            return i
    return None


def _time_col(df: pd.DataFrame) -> str:
    for c in ["global_t", "t_local", "t"]:
        if c in df.columns:
            return c
    return "__row_index__"


def _id_col(df: pd.DataFrame) -> str:
    for c in ["mis_id", "vehicle_id", "id"]:
        if c in df.columns:
            return c
    raise RuntimeError("No vehicle id column found. Expected one of: mis_id, vehicle_id, id")


def _err_cols(df: pd.DataFrame) -> Tuple[str, str, str]:
    h = "taem_h_err" if "taem_h_err" in df.columns else None
    v = "taem_v_err" if "taem_v_err" in df.columns else None
    s = None
    for cand in ["taem_s_go_err", "taem_sgo_err", "taem_s_err"]:
        if cand in df.columns:
            s = cand
            break
    missing = [name for name, col in [("h", h), ("v", v), ("sgo", s)] if col is None]
    if missing:
        raise RuntimeError(f"Missing TAEM error columns for: {missing}. Available columns include: {list(df.columns)[:40]}")
    return h, v, s


def _case_cols(df: pd.DataFrame, forced: Sequence[str] | None = None) -> List[str]:
    if forced:
        cols = [c for c in forced if c in df.columns]
        if cols:
            return cols
    cols = [c for c in CASE_COL_CANDIDATES if c in df.columns]
    # Avoid over-grouping by per-vehicle labels if present; vehicle role is summarized separately.
    cols = [c for c in cols if c not in ["mis_id", "vehicle_id"]]
    return cols


def _source_label(path: Path) -> str:
    name = path.stem
    if "B2R" in name or "b2r" in name:
        return "B2R_role_distinct"
    if "B3A" in name or "b3a" in name:
        return "B3A_heading_spread"
    return name


def _role_distinct_stats(gcase: pd.DataFrame, idcol: str, tcol: str) -> Tuple[bool, float]:
    """Return (role_distinct_ok, max_dynamic_diff)."""
    mids = sorted(gcase[idcol].dropna().unique().tolist())
    if len(mids) < 2:
        return False, 0.0

    groups = {}
    for mid in mids:
        gm = gcase[gcase[idcol] == mid].copy()
        if tcol == "__row_index__":
            gm[tcol] = np.arange(len(gm), dtype=float)
        gm = gm.sort_values(tcol).reset_index(drop=True)
        groups[mid] = gm

    cols = [c for c in DYNAMIC_COLS if c in gcase.columns]
    maxdiff = 0.0
    for i in range(len(mids)):
        for j in range(i + 1, len(mids)):
            a, b = mids[i], mids[j]
            ga, gb = groups[a], groups[b]
            n = min(len(ga), len(gb))
            for c in cols:
                xa = _safe_num(ga[c].iloc[:n]).to_numpy(dtype=float)
                xb = _safe_num(gb[c].iloc[:n]).to_numpy(dtype=float)
                d = xa - xb
                finite = np.isfinite(d)
                if finite.any():
                    md = float(np.nanmax(np.abs(d[finite])))
                    if md > maxdiff:
                        maxdiff = md
    return bool(maxdiff > 1e-7), maxdiff


def _case_label(source: str, case_values: Dict[str, object]) -> str:
    if not case_values:
        return f"{source}|default"
    parts = [f"{k}={case_values[k]}" for k in sorted(case_values)]
    return f"{source}|" + "|".join(parts)


def _evaluate_vehicle(
    gv: pd.DataFrame,
    id_value,
    tcol: str,
    hcol: str,
    vcol: str,
    scol: str,
    htol: float,
    vtol: float,
    stol: float,
    dwell_count_req: int,
) -> Dict[str, object]:
    if tcol == "__row_index__":
        gv = gv.copy()
        gv[tcol] = np.arange(len(gv), dtype=float)
    gv = gv.sort_values(tcol).reset_index(drop=True)

    h_err = _safe_num(gv[hcol])
    v_err = _safe_num(gv[vcol])
    s_err = _safe_num(gv[scol])

    in_box = (h_err.abs() <= htol) & (v_err.abs() <= vtol) & (s_err.abs() <= stol)
    in_box = in_box.fillna(False).to_numpy(dtype=bool)

    max_consec, first_consec_start = _max_consecutive_true(in_box)
    first_in_box = _first_true_index(in_box)
    pass_post = bool(max_consec >= int(dwell_count_req))

    first_pass_t = np.nan
    if pass_post and first_consec_start is not None:
        first_pass_t = float(_safe_num(gv[tcol]).iloc[first_consec_start])

    last = gv.iloc[-1]
    row = {
        "vehicle_id": id_value,
        "n_rows": int(len(gv)),
        "t_start": float(_safe_num(gv[tcol]).iloc[0]) if len(gv) else np.nan,
        "t_end": float(_safe_num(gv[tcol]).iloc[-1]) if len(gv) else np.nan,
        "h_tol_m": float(htol),
        "v_tol_mps": float(vtol),
        "sgo_tol_m": float(stol),
        "dwell_count_req": int(dwell_count_req),
        "post_in_box_any": bool(in_box.any()),
        "post_first_in_box_t": float(_safe_num(gv[tcol]).iloc[first_in_box]) if first_in_box is not None else np.nan,
        "post_max_consecutive_in_box": int(max_consec),
        "post_first_pass_t": first_pass_t,
        "post_pass": pass_post,
        "decision": "PASS_STRICT_POST" if pass_post else "FAIL_TOLERANCE_POST",
        "taem_h_err_min_abs": float(np.nanmin(np.abs(h_err.to_numpy(dtype=float)))) if np.isfinite(h_err).any() else np.nan,
        "taem_v_err_min_abs": float(np.nanmin(np.abs(v_err.to_numpy(dtype=float)))) if np.isfinite(v_err).any() else np.nan,
        "taem_s_go_err_min_abs": float(np.nanmin(np.abs(s_err.to_numpy(dtype=float)))) if np.isfinite(s_err).any() else np.nan,
        "taem_h_err_final": float(h_err.iloc[-1]) if len(h_err) else np.nan,
        "taem_v_err_final": float(v_err.iloc[-1]) if len(v_err) else np.nan,
        "taem_s_go_err_final": float(s_err.iloc[-1]) if len(s_err) else np.nan,
    }

    for c in ["taem_success_latched", "taem_reached_ever", "taem_reached_event", "taem_reached", "taem_in_box", "close_pass_escape"]:
        if c in gv.columns:
            b = _boolish(gv[c])
            row[f"logged_any_{c}"] = bool(b.any())
            row[f"logged_last_{c}"] = bool(b.iloc[-1])
    if "end_reason" in gv.columns:
        row["end_reason_last"] = str(last.get("end_reason", ""))
    if "guide_phase" in gv.columns:
        row["guide_phase_last"] = str(last.get("guide_phase", ""))
    if "s_go" in gv.columns:
        sgo = _safe_num(gv["s_go"])
        row["s_go_min"] = float(np.nanmin(sgo.to_numpy(dtype=float))) if np.isfinite(sgo).any() else np.nan
        row["s_go_final"] = float(sgo.iloc[-1]) if len(sgo) else np.nan
    if "height" in gv.columns:
        hh = _safe_num(gv["height"])
        row["height_final"] = float(hh.iloc[-1]) if len(hh) else np.nan
    if "velocity" in gv.columns:
        vv = _safe_num(gv["velocity"])
        row["velocity_final"] = float(vv.iloc[-1]) if len(vv) else np.nan

    return row


def _load_one(path: Path, forced_case_cols: Sequence[str] | None) -> Tuple[pd.DataFrame, List[str], str]:
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {path}")
    df = pd.read_csv(path)
    source = _source_label(path)
    df["b3c_source"] = source

    idcol = _id_col(df)
    tcol = _time_col(df)
    if tcol == "__row_index__":
        df[tcol] = np.arange(len(df), dtype=float)

    # If no case columns, create default. If present, keep them.
    case_cols = _case_cols(df, forced_case_cols)
    if not case_cols:
        df["b3c_case"] = "default"
        case_cols = ["b3c_case"]

    return df, case_cols, source


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=DEFAULT_INPUTS, help="Input combined trajectory CSV files")
    ap.add_argument("--outdir", default=r"store\data_saved\phase2_B3C_tolerance_report", help="Output directory")
    ap.add_argument("--h-tols", type=_parse_csv_floats, default=[2000.0, 3000.0], help="Comma-separated height tolerances")
    ap.add_argument("--v-tols", type=_parse_csv_floats, default=[100.0, 150.0], help="Comma-separated velocity tolerances")
    ap.add_argument("--sgo-tols", type=_parse_csv_floats, default=[20000.0, 30000.0], help="Comma-separated s_go tolerances")
    ap.add_argument("--dwell-count-req", type=int, default=3, help="Consecutive in-box sample count required")
    ap.add_argument("--case-cols", nargs="*", default=None, help="Optional case grouping columns")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    by_vehicle_rows = []
    by_case_rows = []
    line_rows = []

    for inp in args.inputs:
        path = Path(inp)
        df, case_cols, source = _load_one(path, args.case_cols)
        idcol = _id_col(df)
        tcol = _time_col(df)
        hcol, vcol, scol = _err_cols(df)

        # groupby with dropna=False can be awkward across pandas versions; fill case labels.
        work = df.copy()
        for c in case_cols:
            work[c] = work[c].astype(str).fillna("NA")

        grouped = work.groupby(case_cols, dropna=False, sort=True)
        for case_key, gcase in grouped:
            if not isinstance(case_key, tuple):
                case_key = (case_key,)
            case_values = {c: case_key[i] for i, c in enumerate(case_cols)}
            case_label = _case_label(source, case_values)

            role_distinct_ok, max_dynamic_diff = _role_distinct_stats(gcase, idcol, tcol)
            n_vehicles = int(gcase[idcol].nunique())

            for htol in args.h_tols:
                for vtol in args.v_tols:
                    for stol in args.sgo_tols:
                        vehicle_rows_this = []
                        for vid, gv in gcase.groupby(idcol, sort=True):
                            r = _evaluate_vehicle(
                                gv, vid, tcol, hcol, vcol, scol,
                                htol, vtol, stol, args.dwell_count_req
                            )
                            r.update({
                                "source": source,
                                "input_csv": str(path),
                                "case_label": case_label,
                                **{f"case_{k}": v for k, v in case_values.items()},
                                "role_distinct_ok": role_distinct_ok,
                                "max_dynamic_diff": float(max_dynamic_diff),
                            })
                            vehicle_rows_this.append(r)
                            by_vehicle_rows.append(r)

                        pass_count = int(sum(1 for r in vehicle_rows_this if r["post_pass"]))
                        fail_count = int(len(vehicle_rows_this) - pass_count)
                        if pass_count == n_vehicles and role_distinct_ok:
                            decision = "B3C_TOL_PASS_ROLE_DISTINCT"
                        elif pass_count == n_vehicles:
                            decision = "B3C_TOL_PASS_REPLICATED"
                        else:
                            decision = "B3C_TOL_HAS_FAILURES"

                        row = {
                            "source": source,
                            "case_label": case_label,
                            **{f"case_{k}": v for k, v in case_values.items()},
                            "h_tol_m": float(htol),
                            "v_tol_mps": float(vtol),
                            "sgo_tol_m": float(stol),
                            "dwell_count_req": int(args.dwell_count_req),
                            "n_vehicles": n_vehicles,
                            "pass_count": pass_count,
                            "fail_count": fail_count,
                            "pass_rate": float(pass_count / n_vehicles) if n_vehicles else np.nan,
                            "role_distinct_ok": bool(role_distinct_ok),
                            "max_dynamic_diff": float(max_dynamic_diff),
                            "decision": decision,
                        }
                        by_case_rows.append(row)

    by_vehicle = pd.DataFrame(by_vehicle_rows)
    by_case = pd.DataFrame(by_case_rows)

    by_vehicle.to_csv(outdir / "phase2_B3C_tolerance_by_vehicle.csv", index=False)
    by_case.to_csv(outdir / "phase2_B3C_tolerance_by_case.csv", index=False)

    n_cases = int(len(by_case))
    n_pass_role = int((by_case["decision"] == "B3C_TOL_PASS_ROLE_DISTINCT").sum()) if n_cases else 0
    n_pass_rep = int((by_case["decision"] == "B3C_TOL_PASS_REPLICATED").sum()) if n_cases else 0
    n_fail = int((by_case["decision"] == "B3C_TOL_HAS_FAILURES").sum()) if n_cases else 0

    if n_cases and n_pass_role == n_cases:
        overall = "B3C_PASS_ALL_TOLERANCE_SETS"
    elif n_pass_role > 0 and n_fail == 0:
        overall = "B3C_PASS_ALL_BUT_SOME_REPLICATED"
    elif n_pass_role > 0:
        overall = "B3C_PARTIAL_PASS"
    else:
        overall = "B3C_FAIL_OR_REPLICATED_ONLY"

    lines = []
    lines.append("PHASE 2 / B3C — POST-PROCESS TAEM TOLERANCE SENSITIVITY")
    lines.append("=" * 72)
    lines.append(f"inputs             : {args.inputs}")
    lines.append(f"h_tols_m           : {args.h_tols}")
    lines.append(f"v_tols_mps         : {args.v_tols}")
    lines.append(f"sgo_tols_m         : {args.sgo_tols}")
    lines.append(f"dwell_count_req    : {args.dwell_count_req}")
    lines.append(f"overall_decision   : {overall}")
    lines.append(f"case_tolerance_rows: {n_cases}")
    lines.append(f"pass_role_distinct : {n_pass_role}")
    lines.append(f"pass_replicated    : {n_pass_rep}")
    lines.append(f"fail_rows          : {n_fail}")
    lines.append("")
    lines.append("Case/tolerance summary:")

    for _, r in by_case.iterrows():
        lines.append(
            f"  {r['case_label']} | "
            f"h={r['h_tol_m']:.0f} v={r['v_tol_mps']:.0f} sgo={r['sgo_tol_m']:.0f} | "
            f"{r['decision']} | pass={int(r['pass_count'])}/{int(r['n_vehicles'])} | "
            f"role_distinct_ok={bool(r['role_distinct_ok'])} | "
            f"max_dynamic_diff={float(r['max_dynamic_diff']):.6g}"
        )

    lines.append("")
    lines.append("Interpretation:")
    if overall == "B3C_PASS_ALL_TOLERANCE_SETS":
        lines.append("  - All tested tolerance boxes retain role-distinct 3/3 TAEM success.")
    elif overall == "B3C_PARTIAL_PASS":
        lines.append("  - At least one tested tolerance box retains role-distinct 3/3 TAEM success, but failures occur under stricter settings.")
    elif overall == "B3C_PASS_ALL_BUT_SOME_REPLICATED":
        lines.append("  - All tested tolerance boxes pass, but at least one case is not dynamically role-distinct.")
    else:
        lines.append("  - No role-distinct tolerance setting passed across the tested grid.")

    (outdir / "phase2_B3C_tolerance_summary.txt").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "inputs": args.inputs,
        "h_tols_m": args.h_tols,
        "v_tols_mps": args.v_tols,
        "sgo_tols_m": args.sgo_tols,
        "dwell_count_req": args.dwell_count_req,
        "overall_decision": overall,
        "n_case_tolerance_rows": n_cases,
        "n_pass_role_distinct": n_pass_role,
        "n_pass_replicated": n_pass_rep,
        "n_fail_rows": n_fail,
        "outdir": str(outdir),
    }
    (outdir / "phase2_B3C_tolerance_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n".join(lines))
    print("")
    print("[OK] wrote:", outdir / "phase2_B3C_tolerance_summary.txt")
    print("[OK] wrote:", outdir / "phase2_B3C_tolerance_by_case.csv")
    print("[OK] wrote:", outdir / "phase2_B3C_tolerance_by_vehicle.csv")


if __name__ == "__main__":
    main()
