# -*- coding: utf-8 -*-
"""
taem_threshold_sensitivity_postprocess.py

Recompute TAEM event success from an existing trajectory CSV using user-specified
thresholds. This intentionally ignores any pre-existing taem_in_box /
taem_reached flags in the CSV, so it is suitable for post-processing threshold
sensitivity while keeping the trajectory/guidance dynamics frozen.

Example:
python .\taem_threshold_sensitivity_postprocess.py --input .\store\data_saved\mis1_state_first_v8_2_final_success_flags.csv --outdir .\store\data_saved\v8_2_threshold_sensitivity --idcol mis_id --h-tol 2500 --v-tol 130 --sgo-tol 30000 --dwell-count 3
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

ERR_ALIASES = {
    "h": ["taem_h_err", "taem_err_h"],
    "v": ["taem_v_err", "taem_err_v"],
    "sgo": ["taem_s_go_err", "taem_err_sgo"],
}

def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)

def pick_col(df: pd.DataFrame, names: list[str]) -> str | None:
    for c in names:
        if c in df.columns:
            return c
    return None

def pick_time_col(df: pd.DataFrame) -> str:
    for c in ["t_local", "t", "global_t"]:
        if c in df.columns:
            return c
    return "__row_index__"

def ensure_idcol(df: pd.DataFrame, idcol: str | None) -> tuple[pd.DataFrame, str]:
    if idcol and idcol in df.columns:
        return df, idcol
    if "mis_id" in df.columns:
        return df, "mis_id"
    d = df.copy()
    d["mis_id"] = 0
    return d, "mis_id"

def segment_stats(t: np.ndarray, mask: np.ndarray, dwell_count_req: int) -> dict:
    t = np.asarray(t, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    n = len(t)
    if n == 0:
        return {
            "reached": False,
            "first_reached_t": np.nan,
            "dwell_count_max": 0,
            "dwell_s_total": 0.0,
            "dwell_s_max": 0.0,
        }

    # dt per sample
    dt = np.diff(t)
    if len(dt):
        med = np.nanmedian(dt)
        last = float(med) if np.isfinite(med) else float(dt[-1])
        dt = np.append(dt, last)
    else:
        dt = np.array([0.0])

    dwell_count_max = 0
    cur_count = 0
    dwell_s_total = 0.0
    dwell_s_max = 0.0
    cur_s = 0.0
    reached = False
    first_t = np.nan

    for i, ok in enumerate(mask):
        if ok:
            cur_count += 1
            cur_s += float(dt[i])
            dwell_s_total += float(dt[i])
            dwell_count_max = max(dwell_count_max, cur_count)
            dwell_s_max = max(dwell_s_max, cur_s)
            if (not reached) and cur_count >= dwell_count_req:
                reached = True
                first_t = float(t[i])
        else:
            cur_count = 0
            cur_s = 0.0

    return {
        "reached": bool(reached),
        "first_reached_t": first_t,
        "dwell_count_max": int(dwell_count_max),
        "dwell_s_total": float(dwell_s_total),
        "dwell_s_max": float(dwell_s_max),
    }

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input trajectory CSV")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--idcol", default="mis_id")
    ap.add_argument("--h-tol", type=float, required=True)
    ap.add_argument("--v-tol", type=float, required=True)
    ap.add_argument("--sgo-tol", type=float, required=True)
    ap.add_argument("--dwell-count", type=int, default=3)
    ap.add_argument("--tag", default=None, help="Optional label for output rows")
    return ap.parse_args()

def main():
    args = parse_args()
    inp = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(inp, low_memory=False)
    df, idcol = ensure_idcol(df, args.idcol)
    tcol = pick_time_col(df)
    if tcol == "__row_index__":
        df[tcol] = np.arange(len(df), dtype=float)

    hcol = pick_col(df, ERR_ALIASES["h"])
    vcol = pick_col(df, ERR_ALIASES["v"])
    scol = pick_col(df, ERR_ALIASES["sgo"])
    missing = [name for name, col in [("h", hcol), ("v", vcol), ("sgo", scol)] if col is None]
    if missing:
        raise SystemExit(f"[ERR] Missing TAEM error columns for: {missing}")

    rows = []
    event_frames = []
    for vid, g in df.groupby(idcol):
        g = g.sort_values(tcol).copy()
        h_err = safe_num(g[hcol])
        v_err = safe_num(g[vcol])
        s_err = safe_num(g[scol])

        strict_in_box = (
            (h_err.abs() <= args.h_tol) &
            (v_err.abs() <= args.v_tol) &
            (s_err.abs() <= args.sgo_tol)
        )

        t = safe_num(g[tcol]).to_numpy()
        stats = segment_stats(t, strict_in_box.to_numpy(), args.dwell_count)

        # first strict in-box sample
        if strict_in_box.any():
            first_idx = strict_in_box[strict_in_box].index[0]
            first_in_box_t = float(df.loc[first_idx, tcol])
        else:
            first_in_box_t = np.nan

        idx_best_joint = (
            (h_err.abs() / args.h_tol) +
            (v_err.abs() / args.v_tol) +
            (s_err.abs() / args.sgo_tol)
        ).idxmin()

        r = {
            "tag": args.tag or inp.stem,
            "csv": str(inp),
            "vehicle_id": vid,
            "time_col": tcol,
            "h_tol": float(args.h_tol),
            "v_tol": float(args.v_tol),
            "sgo_tol": float(args.sgo_tol),
            "dwell_count_req": int(args.dwell_count),
            "strict_reached": bool(stats["reached"]),
            "strict_first_reached_t": stats["first_reached_t"],
            "strict_first_in_box_t": first_in_box_t,
            "strict_dwell_count_max": stats["dwell_count_max"],
            "strict_dwell_s_total": stats["dwell_s_total"],
            "strict_dwell_s_max": stats["dwell_s_max"],
            "n_strict_in_box_samples": int(strict_in_box.sum()),
            "min_abs_h_err": float(h_err.abs().min()),
            "min_abs_v_err": float(v_err.abs().min()),
            "min_abs_sgo_err": float(s_err.abs().min()),
            "final_h_err": float(h_err.iloc[-1]),
            "final_v_err": float(v_err.iloc[-1]),
            "final_sgo_err": float(s_err.iloc[-1]),
            "best_joint_t": float(df.loc[idx_best_joint, tcol]),
            "best_joint_h_err": float(h_err.loc[idx_best_joint]),
            "best_joint_v_err": float(v_err.loc[idx_best_joint]),
            "best_joint_sgo_err": float(s_err.loc[idx_best_joint]),
        }
        rows.append(r)

        ev = g[[idcol, tcol, hcol, vcol, scol]].copy()
        ev["strict_in_box_recomputed"] = strict_in_box.to_numpy()
        event_frames.append(ev)

    summary = pd.DataFrame(rows)
    out_summary = outdir / "taem_threshold_sensitivity_summary.csv"
    out_events = outdir / "taem_threshold_sensitivity_events.csv"
    summary.to_csv(out_summary, index=False)
    pd.concat(event_frames, ignore_index=True).to_csv(out_events, index=False)

    print("[OK] Wrote:")
    print(f"  - {out_summary}")
    print(f"  - {out_events}")
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
