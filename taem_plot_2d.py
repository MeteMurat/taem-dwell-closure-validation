# -*- coding: utf-8 -*-
"""
taem_plot_2d.py
Generate quick 2D diagnostics for a single run CSV:
- s_go vs time with STAEM and TAEM lock time markers
- height vs time with HTAEM marker
- velocity vs time with VTAEM marker
- box_score vs time with in-box thresholds

Designed to work with the TAEM "sgo_nominal" definition where HTAEM/VTAEM are
derived from the nominal vehicle at s_go ~= STAEM.

Usage (recommended: use manifest produced by taem_compare_runs.py):
  python taem_plot_2d.py --csv store/data_saved/runs/<RUN>/multiSimulation_case.csv \
      --manifest store/data_saved/taem_compare/taem_compare_manifest.csv \
      --run_id <RUN> --outdir store/data_saved/taem_compare/plots_2d

If you omit --manifest, the script will derive TAEM refs on the fly using:
  --nominal_id (default 1), --staem_m (default 50000), --lock_method closest|first_below
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def pick_idcol(df: pd.DataFrame, idcol: str | None) -> str:
    if idcol and idcol in df.columns:
        return idcol
    for c in ("mis_id", "vehicle_id", "id"):
        if c in df.columns:
            return c
    df["mis_id"] = 0
    return "mis_id"


def pick_tcol(df: pd.DataFrame, tcol: str | None) -> str:
    if tcol and tcol in df.columns:
        return tcol
    for c in ("t", "t_local", "global_t"):
        if c in df.columns and safe_num(df[c]).notna().any():
            return c
    df["t"] = np.arange(len(df), dtype=float)
    return "t"


def derive_taem_refs_sgo_nominal(df: pd.DataFrame, idcol: str, tcol: str,
                                nominal_id: int, staem_m: float, lock_method: str):
    gnom = df[df[idcol] == nominal_id].copy()
    if gnom.empty:
        raise SystemExit(f"[ERR] nominal_id={nominal_id} not found in {idcol}.")
    t = safe_num(gnom[tcol]).to_numpy()
    sgo = safe_num(gnom["s_go"]).to_numpy()
    h = safe_num(gnom["height"]).to_numpy()
    v = safe_num(gnom["velocity"]).to_numpy()

    if lock_method == "first_below":
        idx = np.where(np.isfinite(sgo) & (sgo <= staem_m))[0]
        j = int(idx[0]) if len(idx) else int(np.nanargmin(np.abs(sgo - staem_m)))
    else:
        j = int(np.nanargmin(np.abs(sgo - staem_m)))

    return dict(
        taem_lock_t=float(t[j]) if np.isfinite(t[j]) else float(j),
        HTAEM=float(h[j]),
        VTAEM=float(v[j]),
        STAEM=float(staem_m),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Run CSV path (multiSimulation_case.csv)")
    ap.add_argument("--outdir", required=True, help="Output directory for PNG/PDF")
    ap.add_argument("--manifest", default=None, help="taem_compare_manifest.csv (optional but recommended)")
    ap.add_argument("--run_id", default=None, help="Run id to pick from manifest (folder name)")
    ap.add_argument("--idcol", default=None, help="Vehicle id column (default mis_id)")
    ap.add_argument("--tcol", default=None, help="Time column (default t)")
    ap.add_argument("--nominal_id", type=int, default=1, help="Nominal vehicle id for TAEM lock (if deriving)")
    ap.add_argument("--staem_m", type=float, default=50000.0, help="STAEM in meters (if deriving)")
    ap.add_argument("--lock_method", choices=["closest", "first_below"], default="closest", help="Nominal lock method")
    ap.add_argument("--tol_h", type=float, default=200.0, help="TAEM tol_h for box_score (m)")
    ap.add_argument("--tol_v", type=float, default=50.0, help="TAEM tol_v for box_score (m/s)")
    ap.add_argument("--tol_sgo", type=float, default=200.0, help="TAEM tol_sgo for box_score (m)")
    ap.add_argument("--exit_margin", type=float, default=0.2, help="Hysteresis exit margin (plot only)")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path, low_memory=False)
    idcol = pick_idcol(df, args.idcol)
    tcol = pick_tcol(df, args.tcol)

    # TAEM refs
    refs = None
    if args.manifest and args.run_id:
        m = pd.read_csv(args.manifest)
        sel = m[m["run_id"] == args.run_id]
        if len(sel):
            row = sel.iloc[0]
            refs = dict(
                taem_lock_t=float(row.get("taem_lock_t", np.nan)),
                HTAEM=float(row.get("HTAEM", np.nan)),
                VTAEM=float(row.get("VTAEM", np.nan)),
                STAEM=float(row.get("STAEM", np.nan)),
            )
    if refs is None:
        refs = derive_taem_refs_sgo_nominal(df, idcol, tcol, args.nominal_id, args.staem_m, args.lock_method)

    HT, VT, ST, t_lock = refs["HTAEM"], refs["VTAEM"], refs["STAEM"], refs["taem_lock_t"]

    # build per-vehicle figures
    pdf_path = outdir / f"taem_2d_{csv_path.parent.name}.pdf"
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(pdf_path) as pdf:
        for vid, g in df.groupby(idcol):
            g = g.sort_values(tcol)
            t = safe_num(g[tcol]).to_numpy()
            h = safe_num(g["height"]).to_numpy() if "height" in g.columns else np.full(len(g), np.nan)
            v = safe_num(g["velocity"]).to_numpy() if "velocity" in g.columns else np.full(len(g), np.nan)
            sgo = safe_num(g["s_go"]).to_numpy() if "s_go" in g.columns else np.full(len(g), np.nan)

            h_err = np.abs(h - HT)
            v_err = np.abs(v - VT)
            s_err = np.abs(sgo - ST)

            score = np.maximum.reduce([h_err/args.tol_h, v_err/args.tol_v, s_err/args.tol_sgo])
            score = np.where(np.isfinite(score), score, np.inf)

            fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
            fig.suptitle(f"TAEM 2D Diagnostics | run={csv_path.parent.name} | vehicle={vid}")

            # s_go
            axs[0].plot(t, sgo)
            axs[0].axhline(ST, linestyle="--")
            axs[0].axvline(t_lock, linestyle="--")
            axs[0].set_ylabel("s_go [m]")

            # height + velocity
            axs[1].plot(t, h, label="height")
            axs[1].axhline(HT, linestyle="--")
            axs[1].axvline(t_lock, linestyle="--")
            axs[1].set_ylabel("height [m]")

            ax2 = axs[1].twinx()
            ax2.plot(t, v, label="velocity")
            ax2.axhline(VT, linestyle=":")
            ax2.set_ylabel("velocity [m/s]")

            # score
            axs[2].plot(t, score)
            axs[2].axhline(1.0, linestyle="--")
            axs[2].axhline(1.0 + args.exit_margin, linestyle=":")
            axs[2].axvline(t_lock, linestyle="--")
            axs[2].set_ylabel("box_score [-]")
            axs[2].set_xlabel(f"time ({tcol})")

            fig.tight_layout(rect=[0, 0.03, 1, 0.95])
            png_path = outdir / f"taem_2d_{csv_path.parent.name}_veh{vid}.png"
            fig.savefig(png_path, dpi=200)
            pdf.savefig(fig)
            plt.close(fig)

    print("[OK] wrote", pdf_path)
    print("[OK] wrote PNGs to", outdir)


if __name__ == "__main__":
    main()
