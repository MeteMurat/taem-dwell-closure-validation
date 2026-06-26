#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a reduced-order terminal dataset from one or more simulation CSV files.

Goal:
- Extract terminal-window samples using only a small state/control set:
    states   : h, v, s_go, delta_psi
    controls : alpha, sigma
- Estimate local time-derivatives by finite differences:
    dh_dt, dv_dt, dsgo_dt, dpsi_dt
- Produce a clean dataset for terminal regulator redesign.

Usage (PowerShell):
python .\terminal_reduced_order_builder.py `
  --inputs .\store\data_saved\mis1_state_first_v1.csv `
           .\store\data_saved\mis1_state_first_v2_taem_latch.csv `
           .\store\data_saved\mis1_state_first_v3_arch.csv `
           .\store\data_saved\mis1_state_first_v4_corridor.csv `
  --outdir .\store\data_saved\terminal_reduced_order

Optional:
  --window_mode authority_or_last
  --tail_s 400
  --max_rows_per_run 2000
"""
from __future__ import annotations

import argparse
from pathlib import Path
import math

import numpy as np
import pandas as pd


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def pick_first(df: pd.DataFrame, names: list[str]) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def bool_col(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    s = df[name]
    if s.dtype == bool:
        return s
    if pd.api.types.is_numeric_dtype(s):
        return safe_num(s).fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def maybe_rad_to_deg(s: pd.Series) -> pd.Series:
    a = safe_num(s)
    arr = a.to_numpy()
    finite = np.isfinite(arr)
    if finite.any():
        mx = float(np.nanmax(np.abs(arr[finite])))
        if mx < 6.5:
            return pd.Series(np.degrees(arr), index=s.index)
    return a


def finite_difference(t: np.ndarray, x: np.ndarray) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=float)
    if n < 2:
        return out
    for i in range(n):
        if i == 0:
            dt = t[1] - t[0]
            if np.isfinite(dt) and abs(dt) > 1e-9:
                out[i] = (x[1] - x[0]) / dt
        elif i == n - 1:
            dt = t[-1] - t[-2]
            if np.isfinite(dt) and abs(dt) > 1e-9:
                out[i] = (x[-1] - x[-2]) / dt
        else:
            dt = t[i + 1] - t[i - 1]
            if np.isfinite(dt) and abs(dt) > 1e-9:
                out[i] = (x[i + 1] - x[i - 1]) / dt
    return out


def authority_start_mask(g: pd.DataFrame) -> pd.Series:
    if "terminal_authority_active" in g.columns:
        s = bool_col(g, "terminal_authority_active")
        if s.any():
            return s
    if "terminal_supervisor_state" in g.columns:
        sts = g["terminal_supervisor_state"].astype(str).str.strip().str.lower()
        return sts.isin(["geometry_align", "corridor_track", "box_capture",
                         "heading_capture", "state_capture",
                         "latched_success", "latched_fail"])
    return pd.Series([False] * len(g), index=g.index)


def build_terminal_slice(g: pd.DataFrame, tail_s: float, window_mode: str) -> pd.DataFrame:
    tcol = pick_first(g, ["t_local", "t", "global_t"])
    if tcol is None:
        g = g.copy()
        g["__t__"] = np.arange(len(g), dtype=float)
        tcol = "__t__"
    g = g.sort_values(tcol).copy()
    t = safe_num(g[tcol])

    auth = authority_start_mask(g)
    if auth.any():
        t0 = float(t.loc[auth].iloc[0])
        sel_auth = t >= t0
    else:
        sel_auth = pd.Series([False] * len(g), index=g.index)

    t_end = float(t.iloc[-1]) if len(t) else 0.0
    sel_tail = t >= (t_end - float(tail_s))

    if window_mode == "authority":
        sel = sel_auth if sel_auth.any() else sel_tail
    elif window_mode == "last":
        sel = sel_tail
    else:  # authority_or_last
        sel = sel_auth | sel_tail

    out = g.loc[sel].copy()
    if len(out) == 0:
        out = g.tail(min(len(g), 200)).copy()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--window_mode", default="authority_or_last",
                    choices=["authority_or_last", "authority", "last"])
    ap.add_argument("--tail_s", type=float, default=400.0)
    ap.add_argument("--max_rows_per_run", type=int, default=2000)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    summary = []

    for p_str in args.inputs:
        p = Path(p_str)
        df = pd.read_csv(p, low_memory=False)
        if "mis_id" in df.columns:
            groups = list(df.groupby("mis_id"))
        else:
            df = df.copy()
            df["mis_id"] = 0
            groups = list(df.groupby("mis_id"))

        for vid, g in groups:
            g = build_terminal_slice(g, tail_s=args.tail_s, window_mode=args.window_mode)

            tcol = pick_first(g, ["t_local", "t", "global_t"])
            if tcol is None:
                g["__t__"] = np.arange(len(g), dtype=float)
                tcol = "__t__"

            hcol = pick_first(g, ["height", "h"])
            vcol = pick_first(g, ["velocity", "v"])
            scol = pick_first(g, ["s_go"])
            psicol = pick_first(g, ["delta_psi", "heading_error", "psi_err"])
            acol = pick_first(g, ["attack_angle", "alpha"])
            sigcol = pick_first(g, ["bank_angle", "sigma"])

            if not all([hcol, vcol, scol, psicol, acol, sigcol]):
                summary.append({
                    "run_id": p.stem,
                    "vehicle_id": vid,
                    "status": "missing_columns",
                    "tcol": tcol,
                    "hcol": hcol,
                    "vcol": vcol,
                    "scol": scol,
                    "psicol": psicol,
                    "acol": acol,
                    "sigcol": sigcol,
                })
                continue

            g = g.sort_values(tcol).copy()
            if len(g) > args.max_rows_per_run:
                stride = int(math.ceil(len(g) / args.max_rows_per_run))
                g = g.iloc[::max(1, stride)].copy()

            t = safe_num(g[tcol]).to_numpy(dtype=float)
            h = safe_num(g[hcol]).to_numpy(dtype=float)
            v = safe_num(g[vcol]).to_numpy(dtype=float)
            sgo = safe_num(g[scol]).to_numpy(dtype=float)
            dpsi = safe_num(g[psicol]).to_numpy(dtype=float)
            alpha = safe_num(g[acol]).to_numpy(dtype=float)
            sigma = safe_num(g[sigcol]).to_numpy(dtype=float)

            dh_dt = finite_difference(t, h)
            dv_dt = finite_difference(t, v)
            dsgo_dt = finite_difference(t, sgo)
            dpsi_dt = finite_difference(t, dpsi)

            states = pd.DataFrame({
                "run_id": p.stem,
                "source_csv": str(p),
                "vehicle_id": vid,
                "t": t,
                "h": h,
                "v": v,
                "s_go": sgo,
                "delta_psi": dpsi,
                "alpha": alpha,
                "sigma": sigma,
                "dh_dt": dh_dt,
                "dv_dt": dv_dt,
                "dsgo_dt": dsgo_dt,
                "dpsi_dt": dpsi_dt,
            }, index=g.index)

            # carry useful labels if available
            for c in [
                "terminal_authority_active", "terminal_supervisor_state",
                "taem_in_box", "taem_reached", "taem_reached_event",
                "taem_reached_ever", "taem_success_latched",
                "taem_fail_latched", "end_guide", "end_reason",
                "box_score", "taem_h_err", "taem_v_err", "taem_s_go_err",
                "corridor_h_ref", "corridor_v_ref", "corridor_h_err", "corridor_v_err",
                "close_pass_escape"
            ]:
                if c in g.columns:
                    states[c] = g[c].values

            rows.append(states)

            summary.append({
                "run_id": p.stem,
                "vehicle_id": vid,
                "status": "ok",
                "n_rows": int(len(states)),
                "t_start": float(np.nanmin(t)) if len(t) else np.nan,
                "t_end": float(np.nanmax(t)) if len(t) else np.nan,
                "h_start": float(h[0]) if len(h) else np.nan,
                "h_end": float(h[-1]) if len(h) else np.nan,
                "v_start": float(v[0]) if len(v) else np.nan,
                "v_end": float(v[-1]) if len(v) else np.nan,
                "sgo_start": float(sgo[0]) if len(sgo) else np.nan,
                "sgo_end": float(sgo[-1]) if len(sgo) else np.nan,
                "dpsi_start": float(dpsi[0]) if len(dpsi) else np.nan,
                "dpsi_end": float(dpsi[-1]) if len(dpsi) else np.nan,
            })

    dataset = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    dataset.to_csv(outdir / "terminal_reduced_order_dataset.csv", index=False)
    pd.DataFrame(summary).to_csv(outdir / "terminal_reduced_order_summary.csv", index=False)

    notes = f"""# terminal_reduced_order_builder outputs

Files:
- terminal_reduced_order_dataset.csv
- terminal_reduced_order_summary.csv

Dataset columns:
- states: h, v, s_go, delta_psi
- controls: alpha, sigma
- estimated derivatives: dh_dt, dv_dt, dsgo_dt, dpsi_dt

Suggested next analysis:
1. Correlate sigma with dpsi_dt and dsgo_dt
2. Correlate alpha with dh_dt and dv_dt
3. Split by terminal_supervisor_state
4. Fit a local linear model around terminal-authority-active samples
"""
    (outdir / "terminal_reduced_order_notes.md").write_text(notes, encoding="utf-8")

    print("[OK] wrote:")
    print(f"  - {outdir / 'terminal_reduced_order_dataset.csv'}")
    print(f"  - {outdir / 'terminal_reduced_order_summary.csv'}")
    print(f"  - {outdir / 'terminal_reduced_order_notes.md'}")


if __name__ == "__main__":
    main()
