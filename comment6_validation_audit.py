#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comment6_validation_audit.py

Purpose
-------
Post-process EntryGuidance TAEM CSV logs for Reviewer Comment 6.
The script does not modify the guidance law. It reconstructs the evidence used by
our validation framework so that the manuscript can compare this framework with
common endpoint, tracking, dispersion, and cooperative-guidance evaluation styles.

What it produces
----------------
1) comment6_by_vehicle.csv
   One row per CSV/case/vehicle with reconstructed TAEM errors, dwell counts,
   strict/logged terminal evidence, and role-separation diagnostics.

2) comment6_by_case.csv
   One row per CSV/case with vehicle-level and case-level success indicators.

3) comment6_summary.json
   Compact numerical summary suitable for manuscript/reviewer-response wording.

4) comment6_latex_summary.tex
   A small LaTeX table that can be copied into the manuscript or response file.

Typical PowerShell use
----------------------
cd "D:\\acta-paper\\savunma-makale-adımlar\\savunma makale-2.adım\\EntryGuidance-master"
python .\\multi_main.py
python .\\comment6_validation_audit.py --glob ".\\store\\data_saved\\*.csv" --outdir ".\\store\\data_saved\\comment6_audit" --idcol mis_id

If you only have one known CSV:
python .\\comment6_validation_audit.py --inputs ".\\store\\data_saved\\multiSimulation_case.csv" --outdir ".\\store\\data_saved\\comment6_audit" --idcol mis_id
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

EARTH_R_M = 6371000.0


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return _safe_num(s).fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def _pick_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _pick_time_col(df: pd.DataFrame) -> str:
    for c in ("global_t", "t_local", "t"):
        if c in df.columns and np.isfinite(_safe_num(df[c])).any():
            return c
    return "__row_index__"


def _ensure_idcol(df: pd.DataFrame, idcol: Optional[str]) -> Tuple[pd.DataFrame, str]:
    if idcol and idcol in df.columns:
        return df, idcol
    if "mis_id" in df.columns:
        return df, "mis_id"
    out = df.copy()
    out["mis_id"] = 0
    return out, "mis_id"


def _maybe_rad_to_deg(a: pd.Series) -> pd.Series:
    x = _safe_num(a)
    mx = np.nanmax(np.abs(x.to_numpy())) if len(x) else np.nan
    if np.isfinite(mx) and mx < 6.5:
        return np.degrees(x)
    return x


def _lonlat_rad(df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[pd.Series]]:
    loncol = _pick_col(df, ["longitude", "lon", "lng"])
    latcol = _pick_col(df, ["latitude", "lat"])
    if loncol is None or latcol is None:
        return None, None
    lon = _safe_num(df[loncol])
    lat = _safe_num(df[latcol])
    lon_mx = np.nanmax(np.abs(lon.to_numpy())) if len(lon) else np.nan
    lat_mx = np.nanmax(np.abs(lat.to_numpy())) if len(lat) else np.nan
    if np.isfinite(lon_mx) and np.isfinite(lat_mx) and lon_mx < 6.5 and lat_mx < 3.5:
        return lon, lat
    return np.radians(lon), np.radians(lat)


def haversine_vec(lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2.0 * EARTH_R_M * np.arcsin(np.sqrt(a))


def consecutive_dwell_count(in_box: np.ndarray) -> Tuple[np.ndarray, int, Optional[int]]:
    counts = np.zeros(len(in_box), dtype=int)
    cur = 0
    first_idx = None
    max_count = 0
    for i, ok in enumerate(in_box.astype(bool)):
        cur = cur + 1 if ok else 0
        counts[i] = cur
        if cur > max_count:
            max_count = cur
        if first_idx is None and cur >= 1:
            first_idx = i
    return counts, int(max_count), first_idx


def dwell_confirmation_index(in_box: np.ndarray, dwell_samples: int) -> Optional[int]:
    cur = 0
    for i, ok in enumerate(in_box.astype(bool)):
        cur = cur + 1 if ok else 0
        if cur >= dwell_samples:
            return i
    return None


def compute_role_separation_km(df: pd.DataFrame, idcol: str, tcol: str) -> Dict[str, float]:
    """Approximate max pairwise surface separation using nearest common sample index.

    This is a diagnostic role-distinction metric, not a collision-avoidance proof.
    """
    if idcol not in df.columns:
        return {"role_sep_max_km": np.nan, "role_sep_min_of_max_pair_km": np.nan}
    lon, lat = _lonlat_rad(df)
    if lon is None or lat is None:
        return {"role_sep_max_km": np.nan, "role_sep_min_of_max_pair_km": np.nan}
    d = df.copy()
    d["__lon_rad__"] = lon
    d["__lat_rad__"] = lat
    groups = []
    for vid, g in d.groupby(idcol):
        g = g.sort_values(tcol).reset_index(drop=True)
        if len(g) > 0:
            groups.append((vid, g))
    if len(groups) < 2:
        return {"role_sep_max_km": 0.0, "role_sep_min_of_max_pair_km": 0.0}

    pair_max = []
    for i in range(len(groups)):
        for j in range(i + 1, len(groups)):
            _, gi = groups[i]
            _, gj = groups[j]
            n = min(len(gi), len(gj))
            if n <= 0:
                continue
            dist_m = haversine_vec(
                gi["__lon_rad__"].iloc[:n].to_numpy(float),
                gi["__lat_rad__"].iloc[:n].to_numpy(float),
                gj["__lon_rad__"].iloc[:n].to_numpy(float),
                gj["__lat_rad__"].iloc[:n].to_numpy(float),
            )
            pair_max.append(float(np.nanmax(dist_m) / 1000.0))
    if not pair_max:
        return {"role_sep_max_km": np.nan, "role_sep_min_of_max_pair_km": np.nan}
    return {
        "role_sep_max_km": float(np.nanmax(pair_max)),
        "role_sep_min_of_max_pair_km": float(np.nanmin(pair_max)),
    }


def process_one_csv(
    path: Path,
    idcol_arg: Optional[str],
    h_taem: float,
    v_taem: float,
    s_taem: float,
    tol_h: float,
    tol_v: float,
    tol_s: float,
    dwell_samples: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(path)
    df, idcol = _ensure_idcol(df, idcol_arg)
    tcol = _pick_time_col(df)
    if tcol == "__row_index__":
        df[tcol] = np.arange(len(df), dtype=float)

    # Derive TAEM errors when absent.
    hcol = _pick_col(df, ["height", "altitude", "h"])
    vcol = _pick_col(df, ["velocity", "v"])
    scol = _pick_col(df, ["s_go", "sgo", "range_to_go", "range_to_go_m"])

    if "taem_h_err" not in df.columns and hcol:
        df["taem_h_err"] = _safe_num(df[hcol]) - h_taem
    if "taem_v_err" not in df.columns and vcol:
        df["taem_v_err"] = _safe_num(df[vcol]) - v_taem
    if "taem_s_go_err" not in df.columns and scol:
        df["taem_s_go_err"] = _safe_num(df[scol]) - s_taem

    # Compute in-box from explicit flag if available; otherwise from component errors.
    if "taem_in_box" in df.columns:
        df["__in_box__"] = _bool_series(df, "taem_in_box")
        in_box_source = "logged_taem_in_box"
    elif all(c in df.columns for c in ["taem_h_err", "taem_v_err", "taem_s_go_err"]):
        df["__in_box__"] = (
            (_safe_num(df["taem_h_err"]).abs() <= tol_h)
            & (_safe_num(df["taem_v_err"]).abs() <= tol_v)
            & (_safe_num(df["taem_s_go_err"]).abs() <= tol_s)
        )
        in_box_source = "reconstructed_from_h_v_sgo"
    elif "taem_reached" in df.columns:
        df["__in_box__"] = _bool_series(df, "taem_reached")
        in_box_source = "logged_taem_reached_only"
    else:
        df["__in_box__"] = False
        in_box_source = "missing"

    sep = compute_role_separation_km(df, idcol, tcol)

    vehicle_rows: List[Dict[str, Any]] = []
    for vid, g in df.groupby(idcol):
        g = g.sort_values(tcol).reset_index(drop=True)
        t = _safe_num(g[tcol]).to_numpy(float)
        in_box = g["__in_box__"].to_numpy(bool)
        dwell_counts, dwell_max_samples, first_in_box_idx = consecutive_dwell_count(in_box)
        conf_idx = dwell_confirmation_index(in_box, dwell_samples)
        reconstructed_pass = conf_idx is not None

        # Logged strict evidence if the simulation emits final latch/terminal reason fields.
        taem_reached_logged = bool(_bool_series(g, "taem_reached").any()) if "taem_reached" in g.columns else reconstructed_pass
        latch_cols = [c for c in ["taem_success_latched", "taem_latched", "taem_event_latched"] if c in g.columns]
        latch_logged = bool(pd.concat([_bool_series(g, c) for c in latch_cols], axis=1).any().any()) if latch_cols else taem_reached_logged
        end_reason = str(g["end_reason"].dropna().iloc[-1]) if "end_reason" in g.columns and len(g["end_reason"].dropna()) else ""
        end_reason_ok = (end_reason == "taem_dwell_reached") if "end_reason" in g.columns else reconstructed_pass
        escape_cols = [c for c in ["close_pass_escape", "close_pass_escape_latched", "taem_close_pass_escape"] if c in g.columns]
        escape = bool(pd.concat([_bool_series(g, c) for c in escape_cols], axis=1).any().any()) if escape_cols else False
        logged_strict_pass = bool(latch_logged and end_reason_ok and not escape)

        if conf_idx is not None:
            event_row = g.iloc[int(conf_idx)]
            t_conf = float(t[int(conf_idx)]) if len(t) else np.nan
        elif first_in_box_idx is not None:
            event_row = g.iloc[int(first_in_box_idx)]
            t_conf = float(t[int(first_in_box_idx)]) if len(t) else np.nan
        else:
            event_row = g.iloc[-1]
            t_conf = np.nan

        row: Dict[str, Any] = {
            "csv": str(path),
            "case_id": path.stem,
            "vehicle_id": vid,
            "time_col": tcol,
            "in_box_source": in_box_source,
            "n_samples": int(len(g)),
            "t_start": float(t[0]) if len(t) else np.nan,
            "t_end": float(t[-1]) if len(t) else np.nan,
            "first_in_box_time": float(t[first_in_box_idx]) if first_in_box_idx is not None and len(t) else np.nan,
            "dwell_confirmation_time": t_conf,
            "dwell_max_samples": int(dwell_max_samples),
            "dwell_required_samples": int(dwell_samples),
            "reconstructed_dwell_pass": bool(reconstructed_pass),
            "logged_latch_or_reached": bool(latch_logged),
            "logged_end_reason": end_reason,
            "logged_end_reason_ok": bool(end_reason_ok),
            "logged_close_pass_escape": bool(escape),
            "logged_strict_pass": bool(logged_strict_pass),
            **sep,
        }
        for ec in ["taem_h_err", "taem_v_err", "taem_s_go_err"]:
            if ec in g.columns:
                row[f"event_{ec}"] = float(pd.to_numeric(event_row.get(ec), errors="coerce"))
                row[f"final_{ec}"] = float(_safe_num(g[ec]).iloc[-1])
        for c in ["height", "velocity", "s_go", "q", "q_inf", "L", "D", "bank_angle", "attack_angle", "delta_psi"]:
            if c in g.columns:
                row[f"event_{c}"] = float(pd.to_numeric(event_row.get(c), errors="coerce"))
                row[f"final_{c}"] = float(_safe_num(g[c]).iloc[-1])
        vehicle_rows.append(row)

    by_vehicle = pd.DataFrame(vehicle_rows)
    case_row = {
        "csv": str(path),
        "case_id": path.stem,
        "n_vehicles": int(len(by_vehicle)),
        "vehicle_reconstructed_passes": int(by_vehicle["reconstructed_dwell_pass"].sum()) if len(by_vehicle) else 0,
        "vehicle_logged_strict_passes": int(by_vehicle["logged_strict_pass"].sum()) if len(by_vehicle) else 0,
        "case_reconstructed_pass": bool(by_vehicle["reconstructed_dwell_pass"].all()) if len(by_vehicle) else False,
        "case_logged_strict_pass": bool(by_vehicle["logged_strict_pass"].all()) if len(by_vehicle) else False,
        "role_sep_max_km": float(by_vehicle["role_sep_max_km"].max()) if "role_sep_max_km" in by_vehicle else np.nan,
        "role_sep_min_of_max_pair_km": float(by_vehicle["role_sep_min_of_max_pair_km"].min()) if "role_sep_min_of_max_pair_km" in by_vehicle else np.nan,
    }
    by_case = pd.DataFrame([case_row])
    return by_vehicle, by_case


def read_paths(inputs: List[str], glob_pat: Optional[str]) -> List[Path]:
    paths: List[Path] = [Path(p) for p in inputs]
    if glob_pat:
        paths.extend(sorted(Path().glob(glob_pat)))
    out: List[Path] = []
    seen = set()
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def write_latex_summary(summary: Dict[str, Any], outpath: Path) -> None:
    tex = rf"""% Auto-generated by comment6_validation_audit.py
% Copy this compact table into the reviewer response or manuscript if desired.
\begin{{table}}[!htbp]
\centering
\scriptsize
\caption{{Code-audited validation evidence used to support the framework comparison.}}
\label{{tab:comment6_code_audit_summary}}
\begin{{tabular}}{{l r}}
\toprule
Audit item & Value \\
\midrule
CSV/case files processed & {summary['n_cases']} \\
Vehicle-level records & {summary['n_vehicle_records']} \\
Reconstructed dwell-confirmed vehicle passes & {summary['vehicle_reconstructed_passes']}/{summary['n_vehicle_records']} \\
Logged strict vehicle passes & {summary['vehicle_logged_strict_passes']}/{summary['n_vehicle_records']} \\
Reconstructed dwell-confirmed case passes & {summary['case_reconstructed_passes']}/{summary['n_cases']} \\
Logged strict case passes & {summary['case_logged_strict_passes']}/{summary['n_cases']} \\
Maximum role-separation diagnostic & {summary['role_sep_max_km']:.3f} km \\
Minimum pairwise maximum role separation & {summary['role_sep_min_of_max_pair_km']:.3f} km \\
\bottomrule
\end{{tabular}}
\end{{table}}
"""
    outpath.write_text(tex, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=[], help="Explicit CSV files to audit.")
    ap.add_argument("--glob", default=None, help="Glob pattern for CSV files, e.g. .\\store\\data_saved\\*.csv")
    ap.add_argument("--outdir", required=True, help="Output directory.")
    ap.add_argument("--idcol", default=None, help="Vehicle id column, usually mis_id.")
    ap.add_argument("--h-taem", type=float, default=25000.0)
    ap.add_argument("--v-taem", type=float, default=2000.0)
    ap.add_argument("--s-taem", type=float, default=50000.0)
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=100.0)
    ap.add_argument("--tol-s", type=float, default=20000.0)
    ap.add_argument("--dwell-samples", type=int, default=3)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    paths = read_paths(args.inputs, args.glob)
    if not paths:
        raise SystemExit("[ERR] No CSV files found. Use --inputs or --glob.")

    veh_frames = []
    case_frames = []
    for p in paths:
        bv, bc = process_one_csv(
            p,
            args.idcol,
            args.h_taem,
            args.v_taem,
            args.s_taem,
            args.tol_h,
            args.tol_v,
            args.tol_s,
            args.dwell_samples,
        )
        veh_frames.append(bv)
        case_frames.append(bc)

    by_vehicle = pd.concat(veh_frames, ignore_index=True) if veh_frames else pd.DataFrame()
    by_case = pd.concat(case_frames, ignore_index=True) if case_frames else pd.DataFrame()

    by_vehicle.to_csv(outdir / "comment6_by_vehicle.csv", index=False)
    by_case.to_csv(outdir / "comment6_by_case.csv", index=False)

    nveh = int(len(by_vehicle))
    ncase = int(len(by_case))
    summary: Dict[str, Any] = {
        "n_cases": ncase,
        "n_vehicle_records": nveh,
        "vehicle_reconstructed_passes": int(by_vehicle["reconstructed_dwell_pass"].sum()) if nveh else 0,
        "vehicle_logged_strict_passes": int(by_vehicle["logged_strict_pass"].sum()) if nveh else 0,
        "case_reconstructed_passes": int(by_case["case_reconstructed_pass"].sum()) if ncase else 0,
        "case_logged_strict_passes": int(by_case["case_logged_strict_pass"].sum()) if ncase else 0,
        "role_sep_max_km": float(np.nanmax(by_case["role_sep_max_km"].to_numpy())) if ncase else float("nan"),
        "role_sep_min_of_max_pair_km": float(np.nanmin(by_case["role_sep_min_of_max_pair_km"].to_numpy())) if ncase else float("nan"),
        "h_taem": args.h_taem,
        "v_taem": args.v_taem,
        "s_taem": args.s_taem,
        "tol_h": args.tol_h,
        "tol_v": args.tol_v,
        "tol_s": args.tol_s,
        "dwell_samples": args.dwell_samples,
    }
    (outdir / "comment6_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_latex_summary(summary, outdir / "comment6_latex_summary.tex")

    print("[OK] Comment 6 validation audit complete")
    print(f"  by_vehicle: {outdir / 'comment6_by_vehicle.csv'}")
    print(f"  by_case   : {outdir / 'comment6_by_case.csv'}")
    print(f"  summary   : {outdir / 'comment6_summary.json'}")
    print(f"  latex     : {outdir / 'comment6_latex_summary.tex'}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
