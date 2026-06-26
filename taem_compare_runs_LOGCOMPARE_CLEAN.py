# -*- coding: utf-8 -*-
"""TAEM comparison script with cleanup-aware reach extraction."""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


ERR_ALIASES = {
    "taem_h_err": ["taem_h_err", "taem_err_h"],
    "taem_v_err": ["taem_v_err", "taem_err_v"],
    "taem_s_go_err": ["taem_s_go_err", "taem_err_sgo"],
}


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _pick_time_col(df: pd.DataFrame) -> str:
    for c in ("t_local", "t", "global_t"):
        if c in df.columns:
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


def _pick_err_col(df: pd.DataFrame, canonical: str) -> str | None:
    for c in ERR_ALIASES[canonical]:
        if c in df.columns:
            return c
    return None


def _compute_in_box(df: pd.DataFrame, tol_h: float | None, tol_v: float | None, tol_sgo: float | None) -> pd.Series | None:
    h_col = _pick_err_col(df, "taem_h_err")
    v_col = _pick_err_col(df, "taem_v_err")
    s_col = _pick_err_col(df, "taem_s_go_err")
    have_any = any(c is not None for c in (h_col, v_col, s_col))
    have_tols = any(x is not None for x in (tol_h, tol_v, tol_sgo))
    if not (have_any and have_tols):
        return None

    in_box = pd.Series([True] * len(df), index=df.index)
    if h_col and tol_h is not None:
        in_box &= (_safe_num(df[h_col]).abs() <= float(tol_h))
    if v_col and tol_v is not None:
        in_box &= (_safe_num(df[v_col]).abs() <= float(tol_v))
    if s_col and tol_sgo is not None:
        in_box &= (_safe_num(df[s_col]).abs() <= float(tol_sgo))
    return in_box


def _segment_dwell(t: np.ndarray, in_box: np.ndarray) -> tuple[float, float, float | None, bool]:
    n = len(t)
    if n == 0:
        return (0.0, 0.0, None, False)
    dt = np.diff(t)
    if len(dt) == 0:
        dt = np.array([0.0])
    else:
        med = np.nanmedian(dt)
        last = float(med) if np.isfinite(med) else float(dt[-1])
        dt = np.append(dt, last)

    in_box = np.asarray(in_box, dtype=bool)
    dwell_total = float(np.nansum(dt[in_box]))
    dwell_max = 0.0
    cur = 0.0
    t_first = None
    reached = False
    for i in range(n):
        if in_box[i]:
            if not reached:
                reached = True
                t_first = float(t[i])
            cur += float(dt[i])
            dwell_max = max(dwell_max, cur)
        else:
            cur = 0.0
    return (float(dwell_total), float(dwell_max), t_first, reached)


def _read_many(inputs: list[str], glob_pat: str | None) -> list[Path]:
    paths = [Path(p) for p in inputs]
    if glob_pat:
        paths.extend(sorted(Path().glob(glob_pat)))
    seen = set()
    out = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def _first_non_nan(g: pd.DataFrame, col: str, mask: pd.Series | None = None) -> float:
    if col not in g.columns:
        return np.nan
    s = _safe_num(g[col])
    if mask is not None:
        s = s.loc[mask]
    s = s.dropna()
    return float(s.iloc[0]) if len(s) else np.nan


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=[], help="Explicit list of run CSVs")
    ap.add_argument("--glob", default=None, help="Glob pattern for run CSVs")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--idcol", default=None, help="Vehicle id column")
    ap.add_argument("--run_id", default=None, help="Explicit run label (only if one input)")
    ap.add_argument("--tol_h", type=float, default=None, help="TAEM |h_err| tolerance (m)")
    ap.add_argument("--tol_v", type=float, default=None, help="TAEM |v_err| tolerance")
    ap.add_argument("--tol_sgo", type=float, default=None, help="TAEM |s_go_err| tolerance (m)")
    return ap.parse_args()


def main():
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    run_paths = _read_many(args.inputs, args.glob)
    if not run_paths:
        raise SystemExit("[ERR] No inputs found. Use --inputs or --glob.")

    rows = []
    for p in run_paths:
        df = pd.read_csv(p, low_memory=False)
        df, idcol = _ensure_idcol(df, args.idcol)
        tcol = _pick_time_col(df)
        if tcol == "__row_index__":
            df[tcol] = np.arange(len(df), dtype=float)

        run_label = args.run_id if (args.run_id and len(run_paths) == 1) else p.stem

        err_cols = {canon: _pick_err_col(df, canon) for canon in ERR_ALIASES}

        for vid, g in df.groupby(idcol):
            g = g.sort_values(["global_t"] if "global_t" in g.columns else [tcol]).copy()

            # Remove frozen duplicate rows caused by late post-end logging. Keep last row per local time.
            if tcol in g.columns:
                g = g.drop_duplicates(subset=[tcol], keep="last").copy()
                g = g.sort_values(tcol)

            t = _safe_num(g[tcol]).to_numpy()

            if "taem_reached_event" in g.columns:
                reach_mask = _bool_col(g, "taem_reached_event")
            elif "taem_reached_ever" in g.columns:
                reach_mask = _bool_col(g, "taem_reached_ever")
            elif "taem_reached" in g.columns:
                reach_mask = _bool_col(g, "taem_reached")
            elif "taem_in_box" in g.columns:
                reach_mask = _bool_col(g, "taem_in_box")
            else:
                in_box_ser = _compute_in_box(g, args.tol_h, args.tol_v, args.tol_sgo)
                reach_mask = in_box_ser if in_box_ser is not None else pd.Series([False] * len(g), index=g.index)

            in_box_mask = _bool_col(g, "taem_in_box") if "taem_in_box" in g.columns else reach_mask

            dwell_total, dwell_max, t_first_seg, reached_seg = _segment_dwell(t, in_box_mask.to_numpy(dtype=bool))

            reached = bool(reach_mask.any() or reached_seg)

            # Prefer explicit TAEM times from the reach rows; otherwise fall back to segment first time.
            taem_t_global = _first_non_nan(g, "taem_t_global", reach_mask)
            taem_t_local = _first_non_nan(g, "taem_t_local", reach_mask)
            if not np.isfinite(taem_t_local) and t_first_seg is not None:
                taem_t_local = float(t_first_seg)

            end_mask = _bool_col(g, "end_guide") if "end_guide" in g.columns else pd.Series([False]*len(g), index=g.index)
            if end_mask.any():
                g_end = g.loc[end_mask].sort_values(tcol)
                t_end = float(_safe_num(g_end[tcol]).iloc[0])
                end_reason = str(g_end.get("end_reason", pd.Series([""])).iloc[0]) if len(g_end) else ""
            else:
                t_end = float(t[-1]) if len(t) else np.nan
                end_reason = str(g.get("end_reason", pd.Series([""])).iloc[-1]) if len(g) else ""

            r = {
                "run_id": run_label,
                "csv": str(p),
                "vehicle_id": vid,
                "time_col": tcol,
                "t_start": float(t[0]) if len(t) else np.nan,
                "t_end": t_end,
                "end_reason": end_reason,
                "taem_reached": bool(reached),
                "taem_t_first_reached": float(taem_t_local) if np.isfinite(taem_t_local) else np.nan,
                "taem_t_global": float(taem_t_global) if np.isfinite(taem_t_global) else np.nan,
                "taem_t_local": float(taem_t_local) if np.isfinite(taem_t_local) else np.nan,
                "taem_dwell_s": float(dwell_total),
                "taem_dwell_max_s": float(dwell_max),
            }

            for canon, col in err_cols.items():
                if col is not None:
                    r[canon] = float(_safe_num(g[col]).iloc[-1])

            rows.append(r)

    by_vehicle = pd.DataFrame(rows).sort_values(["run_id", "vehicle_id"])
    by_vehicle.to_csv(outdir / "taem_compare_by_vehicle.csv", index=False)

    agg_rows = []
    for run_id, g in by_vehicle.groupby("run_id"):
        n = len(g)
        agg_rows.append({
            "run_id": run_id,
            "n_vehicles": int(n),
            "reached_rate": float(np.mean(g["taem_reached"].astype(float))) if n else np.nan,
            "avg_dwell_s": float(np.nanmean(g["taem_dwell_s"].to_numpy())) if n else np.nan,
            "avg_dwell_max_s": float(np.nanmean(g["taem_dwell_max_s"].to_numpy())) if n else np.nan,
            "median_t_first_reached": float(np.nanmedian(g["taem_t_first_reached"].to_numpy())) if n else np.nan,
        })

    pd.DataFrame(agg_rows).sort_values("run_id").to_csv(outdir / "taem_compare_by_run.csv", index=False)
    print("[OK] Wrote:")
    print(f"  - {outdir / 'taem_compare_by_vehicle.csv'}")
    print(f"  - {outdir / 'taem_compare_by_run.csv'}")


if __name__ == "__main__":
    main()
