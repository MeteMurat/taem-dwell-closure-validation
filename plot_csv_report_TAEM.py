# -*- coding: utf-8 -*-
"""plot_csv_report.py with TAEM vertical markers and summary fields."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# -----------------------------
# Publication label helpers
# -----------------------------
def vehicle_label(gid) -> str:
    """Return a publication-friendly vehicle label: Vehicle 1, Vehicle 2, ..."""
    try:
        return f"Vehicle {int(float(gid)) + 1}"
    except Exception:
        return "Vehicle"

def clean_case_label(text, max_words: int = 6) -> str:
    """Remove underscore-heavy technical labels from figure axes."""
    s = str(text)
    s = s.replace("_", " ").replace("hp", "h+").replace("hm", "h-").replace("vp", "v+").replace("vm", "v-")
    s = s.replace("deg", " deg").replace("p", ".")
    words = s.split()
    if len(words) > max_words:
        return " ".join(words[:max_words])
    return s

def audit_label(i: int) -> str:
    return f"Audit {int(i) + 1}"

def variable_label(name: str) -> str:
    mapping = {
        "global_t": "Global time (s)",
        "t_local": "Local time (s)",
        "t": "Time (s)",
        "height": "Altitude (m)",
        "altitude": "Altitude (m)",
        "velocity": "Velocity (m/s)",
        "v": "Velocity (m/s)",
        "q": "Dynamic pressure (Pa)",
        "s_go": "Range-to-go (m)",
        "sgo": "Range-to-go (m)",
        "range_to_go": "Range-to-go (m)",
        "E": "Specific energy",
        "bank_angle": "Bank angle (deg)",
        "attack_angle": "Angle of attack (deg)",
        "path_angle": "Flight-path angle (deg)",
        "heading_angle": "Heading angle (deg)",
        "delta_psi": "Heading error (deg)",
        "sigma_max": "Maximum bank angle (deg)",
        "longitude": "Longitude (deg)",
        "latitude": "Latitude (deg)",
        "longitude_deg": "Longitude (deg)",
        "latitude_deg": "Latitude (deg)",
        "L12D": "Reference lift-to-drag metric",
        "CL": "Lift coefficient",
        "CD": "Drag coefficient",
        "L": "Lift (N)",
        "D": "Drag (N)",
        "box_score": "TAEM in-box score",
        "taem_h_err": "TAEM altitude error (m)",
        "taem_v_err": "TAEM velocity error (m/s)",
        "taem_s_go_err": "TAEM range-to-go error (m)",
    }
    return mapping.get(str(name), str(name).replace("_", " "))

def time_label(tcol: str) -> str:
    return variable_label(tcol)



def maybe_rad2deg(series: pd.Series) -> pd.Series:
    a = pd.to_numeric(series, errors="coerce").astype(float)
    mx = np.nanmax(np.abs(a.to_numpy())) if len(a) else np.nan
    if np.isfinite(mx) and mx < 6.5:
        return np.degrees(a)
    return a


def pick_first_existing(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input CSV path")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--downsample", type=int, default=1, help="Downsample rows (keep every Nth)")
    ap.add_argument("--idcol", default=None, help="Vehicle id column (default: mis_id if present)")
    ap.add_argument("--vars", nargs="*", default=None, help="Variables to plot")
    ap.add_argument(
        "--xcol",
        default="auto",
        choices=["auto", "global_t", "t_local"],
        help="Time axis for all timeseries plots.",
    )
    return ap.parse_args()


def ensure_t_local(df: pd.DataFrame, idcol: str) -> pd.DataFrame:
    if "t_local" in df.columns:
        return df
    if "global_t" not in df.columns:
        return df
    g = df.copy()
    if "launch_time" in g.columns:
        g["t_local"] = safe_numeric(g["global_t"]) - safe_numeric(g["launch_time"])
    else:
        g["t_local"] = safe_numeric(g["global_t"]) - g.groupby(idcol)["global_t"].transform("min")
    return g


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def safe_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s
    if pd.api.types.is_numeric_dtype(s):
        return safe_numeric(s).fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def _pick_taem_markers(df: pd.DataFrame, idcol: str, tcol: str) -> Dict[object, float]:
    markers: Dict[object, float] = {}
    for gid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        t = safe_numeric(g[tcol])

        # 1) Explicit pulse row.
        if "taem_reached" in g.columns:
            m = _bool_col(g, "taem_reached")
            if m.any():
                markers[gid] = float(t.loc[m].iloc[0])
                continue

        # 2) Stored first-reach timestamp aligned to current time-axis.
        if tcol == "t_local" and "taem_t_local" in g.columns:
            tt = safe_numeric(g["taem_t_local"]).dropna()
            if len(tt):
                markers[gid] = float(tt.iloc[0])
                continue
        if tcol == "global_t" and "taem_t_global" in g.columns:
            tt = safe_numeric(g["taem_t_global"]).dropna()
            if len(tt):
                markers[gid] = float(tt.iloc[0])
                continue

        # 3) First in-box row fallback.
        if "taem_in_box" in g.columns:
            m = _bool_col(g, "taem_in_box")
            if m.any():
                markers[gid] = float(t.loc[m].iloc[0])
    return markers


def plot_timeseries(pdf: PdfPages, outdir: Path, df: pd.DataFrame, idcol: str, tcol: str, var: str, taem_markers):
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)

    for gid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        x = safe_numeric(g[tcol])
        y = safe_numeric(g[var])
        ax.plot(x, y, label=vehicle_label(gid))
        if gid in taem_markers and np.isfinite(taem_markers[gid]):
            ax.axvline(float(taem_markers[gid]), linestyle="--", linewidth=1.0, alpha=0.8)

    ax.set_xlabel(time_label(tcol))
    ax.set_ylabel(variable_label(var))
    ax.set_title(f"{variable_label(var)} versus {time_label(tcol)}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)

    png_path = outdir / f"{var}_vs_{tcol}.png"
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def plot_ground_track(pdf: PdfPages, outdir: Path, df: pd.DataFrame, idcol: str):
    loncol = pick_first_existing(df, ["longitude", "lon", "lng"])
    latcol = pick_first_existing(df, ["latitude", "lat"])
    if loncol is None or latcol is None:
        return

    d = df.copy()
    d["_lon_deg"] = maybe_rad2deg(d[loncol])
    d["_lat_deg"] = maybe_rad2deg(d[latcol])

    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)
    for gid, g in d.groupby(idcol):
        g = g.sort_values("global_t" if "global_t" in g.columns else g.index.name or "index")
        ax.plot(safe_numeric(g["_lon_deg"]), safe_numeric(g["_lat_deg"]), label=vehicle_label(gid))
        ax.plot(float(g["_lon_deg"].iloc[-1]), float(g["_lat_deg"].iloc[-1]), marker="o")
        if "taem_reached" in g.columns:
            m = _bool_col(g, "taem_reached")
            if m.any():
                gt = g.loc[m].iloc[0]
                ax.plot(float(gt["_lon_deg"]), float(gt["_lat_deg"]), marker="x", markersize=8)

    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Ground track")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)

    png_path = outdir / "ground_track_lonlat.png"
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def make_summary(outdir: Path, df: pd.DataFrame, idcol: str, tcol: str):
    loncol = pick_first_existing(df, ["longitude", "lon", "lng"])
    latcol = pick_first_existing(df, ["latitude", "lat"])
    hcol = pick_first_existing(df, ["height", "altitude", "h"])
    vcol = pick_first_existing(df, ["velocity", "v"])
    qcol = pick_first_existing(df, ["q"])
    sgocol = pick_first_existing(df, ["s_go", "ref_sgo"])
    L12Dcol = pick_first_existing(df, ["L12D", "ref_L12D"])

    rows = []
    for gid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        row = {"mis_id": gid}
        row["t_start"] = float(safe_numeric(g[tcol]).iloc[0])
        row["t_end"] = float(safe_numeric(g[tcol]).iloc[-1])
        if hcol:
            row["h_min_m"] = float(np.nanmin(safe_numeric(g[hcol]).to_numpy()))
            row["h_end_m"] = float(safe_numeric(g[hcol]).iloc[-1])
        if vcol:
            row["v_min"] = float(np.nanmin(safe_numeric(g[vcol]).to_numpy()))
            row["v_end"] = float(safe_numeric(g[vcol]).iloc[-1])
        if qcol:
            row["q_max"] = float(np.nanmax(safe_numeric(g[qcol]).to_numpy()))
        if sgocol:
            row["s_go_min"] = float(np.nanmin(safe_numeric(g[sgocol]).to_numpy()))
        if L12Dcol:
            row["L12D_min"] = float(np.nanmin(safe_numeric(g[L12Dcol]).to_numpy()))

        if loncol and latcol:
            lon_deg = maybe_rad2deg(g[loncol])
            lat_deg = maybe_rad2deg(g[latcol])
            row["lon_start_deg"] = float(safe_numeric(lon_deg).iloc[0])
            row["lat_start_deg"] = float(safe_numeric(lat_deg).iloc[0])
            row["lon_end_deg"] = float(safe_numeric(lon_deg).iloc[-1])
            row["lat_end_deg"] = float(safe_numeric(lat_deg).iloc[-1])

        if "taem_reached" in g.columns:
            pulse = _bool_col(g, "taem_reached")
            row["taem_reached_any"] = bool(pulse.any())
        elif "taem_reached_ever" in g.columns:
            row["taem_reached_any"] = bool(_bool_col(g, "taem_reached_ever").any())

        for c in ["taem_t_global", "taem_t_local", "taem_h_err", "taem_v_err", "taem_s_go_err", "taem_dwell_s"]:
            if c in g.columns:
                vals = safe_numeric(g[c]).dropna()
                if len(vals):
                    row[c] = float(vals.iloc[-1] if c.endswith("_err") or c == "taem_dwell_s" else vals.iloc[0])

        rows.append(row)

    pd.DataFrame(rows).to_csv(outdir / "summary_by_vehicle.csv", index=False)


def auto_vars(df: pd.DataFrame) -> list:
    preferred = [
        "height", "velocity", "q", "s_go", "L12D",
        "bank_angle", "attack_angle", "path_angle", "heading_angle",
        "CL", "CD", "L", "D", "E", "sigma_max",
        "taem_h_err", "taem_v_err", "taem_s_go_err",
        "longitude", "latitude",
    ]
    expanded = [v for v in preferred if v in df.columns]
    alternates = {
        "bank_angle": ["bank", "sigma"],
        "attack_angle": ["alpha", "aoa"],
        "path_angle": ["gamma"],
        "heading_angle": ["psi", "heading"],
    }
    for base, alts in alternates.items():
        if base not in expanded:
            for a in alts:
                if a in df.columns:
                    expanded.append(a)
                    break
    return expanded


def main():
    args = parse_args()
    inp = Path(args.input)
    outdir = Path(args.outdir)
    ensure_dir(outdir)

    df = pd.read_csv(inp)
    idcol = args.idcol or ("mis_id" if "mis_id" in df.columns else None)
    if not idcol or idcol not in df.columns:
        df["mis_id"] = 0
        idcol = "mis_id"

    if "global_t" not in df.columns:
        df["global_t"] = np.arange(len(df), dtype=float)

    if args.xcol in ("t_local", "auto"):
        df = ensure_t_local(df, idcol)

    if args.xcol == "global_t":
        tcol = "global_t"
    elif args.xcol == "t_local":
        tcol = "t_local" if "t_local" in df.columns else "global_t"
    else:
        tcol = "t_local" if "t_local" in df.columns else "global_t"

    df = df.sort_values([idcol, tcol]).reset_index(drop=True)
    if args.downsample and args.downsample > 1:
        df = df.iloc[::args.downsample].reset_index(drop=True)

    vars_to_plot = args.vars if args.vars else auto_vars(df)
    taem_markers = _pick_taem_markers(df, idcol, tcol)

    pdf_path = outdir / "timeseries_plots.pdf"
    with PdfPages(pdf_path) as pdf:
        plot_ground_track(pdf, outdir, df, idcol)
        for var in vars_to_plot:
            if var == "longitude" or var == "latitude":
                tmp = df.copy()
                if var == "longitude":
                    tmp["longitude_deg"] = maybe_rad2deg(tmp[var])
                    plot_timeseries(pdf, outdir, tmp, idcol, tcol, "longitude_deg", taem_markers)
                else:
                    tmp["latitude_deg"] = maybe_rad2deg(tmp[var])
                    plot_timeseries(pdf, outdir, tmp, idcol, tcol, "latitude_deg", taem_markers)
                continue
            if var in df.columns:
                plot_timeseries(pdf, outdir, df, idcol, tcol, var, taem_markers)

    make_summary(outdir, df, idcol, tcol)
    print(f"[OK] Wrote: {pdf_path}")
    print(f"[OK] Wrote: {outdir / 'summary_by_vehicle.csv'}")
    print(f"[INFO] PNGs are in: {outdir}")


if __name__ == "__main__":
    main()