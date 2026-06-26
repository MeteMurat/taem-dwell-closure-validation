#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_scoreboard.py (LATEST)

- Robust run_id from parent directory name.
- Robust time parsing (numeric/timedelta/datetime -> seconds; fallback to row index).
- Produces:
  - scoreboard_by_vehicle.csv
  - scoreboard_by_run.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

__version__ = "2026-03-05-latest"


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _safe_time_sec(s: pd.Series) -> pd.Series:
    a = pd.to_numeric(s, errors="coerce")
    if a.notna().any():
        return a.astype(float)
    td = pd.to_timedelta(s, errors="coerce")
    if td.notna().any():
        return td.dt.total_seconds().astype(float)
    dt = pd.to_datetime(s, errors="coerce")
    if dt.notna().any():
        base = dt.iloc[0]
        return (dt - base).dt.total_seconds().astype(float)
    return a.astype(float)


def _pick_time_col(df: pd.DataFrame) -> str:
    for c in ("t_local", "global_t", "t"):
        if c in df.columns:
            s = _safe_time_sec(df[c])
            if len(s) and float(np.isfinite(s.to_numpy()).mean()) >= 0.5:
                return c
    return "__row_index__"


def _ensure_idcol(df: pd.DataFrame, idcol: str | None) -> tuple[pd.DataFrame, str]:
    if idcol and idcol in df.columns:
        return df, idcol
    if "mis_id" in df.columns:
        return df, "mis_id"
    d = df.copy()
    d["mis_id"] = 0
    return d, "mis_id"


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s
    if pd.api.types.is_numeric_dtype(s):
        return _safe_num(s).fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])



def _nan_only(df: pd.DataFrame, col: str) -> bool:
    if col not in df.columns:
        return False
    s = df[col]
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").isna().all()
    ss = s.astype(str).str.strip().str.lower()
    return ss.isin(["nan", "none", "null", ""]).all()

def _compute_err_from_refs(df: pd.DataFrame) -> dict[str, pd.Series] | None:
    need_refs = all(c in df.columns for c in ("HTAEM","VTAEM","STAEM"))
    need_state = all(c in df.columns for c in ("height","velocity","s_go"))
    if not (need_refs and need_state):
        return None
    h  = _safe_num(df["height"])
    v  = _safe_num(df["velocity"])
    sg = _safe_num(df["s_go"])
    HT = _safe_num(df["HTAEM"])
    VT = _safe_num(df["VTAEM"])
    ST = _safe_num(df["STAEM"])
    return {
        "taem_err_h_m": (h - HT),
        "taem_err_v_mps": (v - VT),
        "taem_err_sgo_m": (sg - ST),
    }
def per_vehicle_metrics(df: pd.DataFrame, idcol: str, run_id: str, csv_path: Path) -> pd.DataFrame:
    tcol = _pick_time_col(df)
    if tcol == "__row_index__":
        df = df.copy()
        df[tcol] = np.arange(len(df), dtype=float)

    rows = []
    for vid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        t = _safe_time_sec(g[tcol]).to_numpy()
        if np.isfinite(t).sum() < 2:
            t = np.arange(len(g), dtype=float)
        else:
            t = pd.Series(t).interpolate(limit_direction="both").to_numpy()

        r = {
            "run_id": run_id,
            "csv": str(csv_path),
            "vehicle_id": vid,
            "t_end": float(t[-1]) if len(t) else np.nan,
        }

        # TAEM quick flags (ignore NaN-only columns)
        if ("taem_in_box" in g.columns) and (not _nan_only(g, "taem_in_box")):
            r["taem_in_box_any"] = bool(_bool_col(g, "taem_in_box").any())
        if ("taem_reached" in g.columns) and (not _nan_only(g, "taem_reached")):
            r["taem_reached_any"] = bool(_bool_col(g, "taem_reached").any())

        # TAEM proximity from refs (works even when log channels are NaN)
        comp = _compute_err_from_refs(g)
        if comp is not None:
            r["taem_err_h_min_abs_m"] = float(np.nanmin(np.abs(comp["taem_err_h_m"].to_numpy())))
            r["taem_err_v_min_abs_mps"] = float(np.nanmin(np.abs(comp["taem_err_v_mps"].to_numpy())))
            r["taem_err_sgo_min_abs_m"] = float(np.nanmin(np.abs(comp["taem_err_sgo_m"].to_numpy())))

        # core trajectory metrics
        if "q" in g.columns:
            r["q_max"] = float(np.nanmax(_safe_num(g["q"]).to_numpy()))
        if "s_go" in g.columns:
            r["s_go_min"] = float(np.nanmin(_safe_num(g["s_go"]).to_numpy()))

        # L12D diagnostics
        if "L12D" in g.columns:
            L = _safe_num(g["L12D"]).to_numpy()
            r["L12D_min"] = float(np.nanmin(L))
            r["L12D_nan_frac"] = float(np.mean(~np.isfinite(L)))

        # bank smoothness
        if "bank_angle" in g.columns:
            ba = _safe_num(g["bank_angle"]).to_numpy()
            if len(ba) >= 2 and len(t) >= 2:
                dt = np.diff(t)
                dt = np.where(dt <= 1e-9, 1e-9, dt)
                br = np.diff(ba) / dt
                r["bank_rate_max"] = float(np.nanmax(np.abs(br)))
                r["bank_TV"] = float(np.nansum(np.abs(np.diff(ba))))

        if "sigma_cmd_raw" in g.columns:
            sc = _safe_num(g["sigma_cmd_raw"]).to_numpy()
            r["sigma_cmd_raw_spike"] = float(np.nanmax(np.abs(np.diff(sc)))) if len(sc) >= 2 else np.nan

        if "L12D_singularity" in g.columns:
            r["L12D_singularity_cnt"] = int(_bool_col(g, "L12D_singularity").sum())
        if "L12D_den_singularity" in g.columns:
            r["L12D_den_singularity_cnt"] = int(_bool_col(g, "L12D_den_singularity").sum())
        if "L12D_update_hold" in g.columns:
            r["L12D_update_hold_cnt"] = int(_bool_col(g, "L12D_update_hold").sum())

        rows.append(r)

    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True, help="Glob to run CSVs (e.g., store/data_saved/runs/*/multiSimulation_case.csv)")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--idcol", default="mis_id", help="Vehicle id column (default: mis_id)")
    ap.add_argument("--verbose", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    paths = sorted(Path().glob(args.glob))
    if not paths:
        pat = args.glob.replace("\\", "/")
        paths = sorted(Path().glob(pat))
    if not paths:
        raise SystemExit(f"[ERR] no files match glob: {args.glob}")

    if args.verbose:
        print(f"[make_scoreboard] version={__version__} matched={len(paths)}")
        for p in paths[:5]:
            print("  ", str(p))

    all_rows = []
    for p in paths:
        df = pd.read_csv(p, low_memory=False)
        df, idcol = _ensure_idcol(df, args.idcol)
        run_id = p.parent.name
        all_rows.append(per_vehicle_metrics(df, idcol, run_id, p))

    by_vehicle = pd.concat(all_rows, ignore_index=True)
    by_vehicle.to_csv(outdir / "scoreboard_by_vehicle.csv", index=False)

    agg = by_vehicle.groupby("run_id").agg({
        "vehicle_id": "count",
        "q_max": "mean",
        "s_go_min": "mean",
        "L12D_min": "mean",
        "L12D_nan_frac": "mean",
        "bank_rate_max": "mean",
        "bank_TV": "mean",
        "sigma_cmd_raw_spike": "mean",
        "L12D_singularity_cnt": "sum",
        "L12D_den_singularity_cnt": "sum",
        "L12D_update_hold_cnt": "sum",
    }).rename(columns={"vehicle_id": "n_vehicles"}).reset_index()

    agg.to_csv(outdir / "scoreboard_by_run.csv", index=False)

    if args.verbose:
        print("[OK] wrote:", outdir / "scoreboard_by_vehicle.csv")
        print("[OK] wrote:", outdir / "scoreboard_by_run.csv")


if __name__ == "__main__":
    main()
