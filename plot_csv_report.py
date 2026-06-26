# -*- coding: utf-8 -*-
"""Robust multi-vehicle CSV plot/report generator with TAEM diagnostics."""
import argparse
from pathlib import Path
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



def safe_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def maybe_rad2deg(series: pd.Series) -> pd.Series:
    a = safe_numeric(series)
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
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--downsample", type=int, default=1)
    ap.add_argument("--idcol", default=None)
    ap.add_argument("--vars", nargs="*", default=None)
    ap.add_argument("--xcol", default="auto", choices=["auto", "global_t", "t_local", "t"])
    return ap.parse_args()


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def ensure_time_axes(df: pd.DataFrame, idcol: str) -> pd.DataFrame:
    out = df.copy()

    def good_col(name: str):
        if name not in out.columns:
            return None
        s = safe_numeric(out[name])
        return s if s.notna().any() else None

    base = good_col("global_t")
    if base is None:
        base = good_col("t")
    if base is None:
        base = pd.Series(np.arange(len(out), dtype=float), index=out.index)
    out["global_t"] = base

    cur_tlocal = good_col("t_local")
    if cur_tlocal is not None:
        out["t_local"] = cur_tlocal
    else:
        if "launch_time" in out.columns:
            out["t_local"] = out["global_t"] - safe_numeric(out["launch_time"]).fillna(0.0)
        else:
            out["t_local"] = out["global_t"] - out.groupby(idcol)["global_t"].transform("min")
    out["t"] = safe_numeric(out["global_t"])
    return out


def pick_time_col(df: pd.DataFrame, requested: str) -> str:
    if requested != "auto":
        if requested in df.columns and safe_numeric(df[requested]).notna().any():
            return requested
    for c in ["t_local", "global_t", "t"]:
        if c in df.columns and safe_numeric(df[c]).notna().any():
            return c
    df["__row_index__"] = np.arange(len(df), dtype=float)
    return "__row_index__"


def taem_time_for_group(g: pd.DataFrame, tcol: str):
    if "taem_reached" in g.columns:
        s = g["taem_reached"]
        if s.dtype == bool:
            mask = s.fillna(False)
        elif pd.api.types.is_numeric_dtype(s):
            mask = safe_numeric(s).fillna(0.0) > 0.5
        else:
            mask = s.astype(str).str.lower().isin(["true", "1", "yes"])
        if mask.any():
            vals = safe_numeric(g.loc[mask, tcol]).dropna()
            if len(vals):
                return float(vals.iloc[0])
    if "taem_t_local" in g.columns and tcol == "t_local":
        vals = safe_numeric(g["taem_t_local"]).dropna()
        if len(vals):
            return float(vals.iloc[0])
    if "taem_t_global" in g.columns and tcol == "global_t":
        vals = safe_numeric(g["taem_t_global"]).dropna()
        if len(vals):
            return float(vals.iloc[0])
    for c in ("taem_t_local", "taem_t_global", "taem_entry_t"):
        if c in g.columns:
            vals = safe_numeric(g[c]).dropna()
            if len(vals):
                return float(vals.iloc[0])
    return None


def add_ref_lines(ax, var: str, g: pd.DataFrame):
    refs = {"s_go": ["STAEM"], "height": ["HTAEM"], "velocity": ["VTAEM"], "E": ["ETAEM"]}
    for rc in refs.get(var, []):
        if rc in g.columns:
            vals = safe_numeric(g[rc]).dropna()
            if len(vals):
                ax.axhline(float(vals.iloc[0]), linestyle="--", linewidth=1, alpha=0.7)


def plot_timeseries(pdf: PdfPages, outdir: Path, df: pd.DataFrame, idcol: str, tcol: str, var: str):
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)
    plotted = False
    for gid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        x = safe_numeric(g[tcol])
        y = safe_numeric(g[var])
        mask = x.notna() & y.notna()
        if not mask.any():
            continue
        ax.plot(x[mask], y[mask], label=vehicle_label(gid))

        if "taem_reached" in g.columns:
            taem_mask = pd.to_numeric(g["taem_reached"], errors="coerce").fillna(0).astype(float) > 0.5
            if taem_mask.any():
                t_taem = float(pd.to_numeric(g.loc[taem_mask, tcol], errors="coerce").iloc[0])
                ax.axvline(t_taem, linestyle="--", linewidth=1.0, alpha=0.8)

        add_ref_lines(ax, var, g)
        plotted = True
    if not plotted:
        plt.close(fig)
        return
    ax.set_xlabel(time_label(tcol))
    ax.set_ylabel(variable_label(var))
    ax.set_title(f"{variable_label(var)} versus {time_label(tcol)}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.savefig(outdir / f"{var}_vs_{tcol}.png", dpi=200, bbox_inches="tight")
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
    plotted = False
    for gid, g in d.groupby(idcol):
        x = safe_numeric(g["_lon_deg"])
        y = safe_numeric(g["_lat_deg"])
        mask = x.notna() & y.notna()
        if not mask.any():
            continue
        ax.plot(x[mask], y[mask], label=vehicle_label(gid))
        ax.plot(float(x[mask].iloc[-1]), float(y[mask].iloc[-1]), marker="o")
        plotted = True
    if not plotted:
        plt.close(fig)
        return
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Ground track")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=8)
    fig.savefig(outdir / "ground_track_lonlat.png", dpi=200, bbox_inches="tight")
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def plot_taem_diagnostics(pdf: PdfPages, outdir: Path, df: pd.DataFrame, idcol: str, tcol: str):
    if "box_score" not in df.columns and "taem_in_box" in df.columns:
        df = df.copy()
        df["box_score"] = safe_numeric(df["taem_in_box"])
    if not any(c in df.columns for c in ["box_score", "s_go", "height", "velocity"]):
        return
    for gid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        fig, axes = plt.subplots(2, 2, figsize=(10, 7))
        panels = [("box_score", None), ("s_go", "STAEM"), ("height", "HTAEM"), ("velocity", "VTAEM")]
        for ax, (var, ref) in zip(axes.flat, panels):
            if var not in g.columns:
                ax.axis("off")
                continue
            x = safe_numeric(g[tcol])
            y = safe_numeric(g[var])
            mask = x.notna() & y.notna()
            if not mask.any():
                ax.axis("off")
                continue
            ax.plot(x[mask], y[mask])
            if ref and ref in g.columns:
                rv = safe_numeric(g[ref]).dropna()
                if len(rv):
                    ax.axhline(float(rv.iloc[0]), linestyle="--", linewidth=1)
            if var == "box_score":
                ax.axhline(1.0, linestyle="--", linewidth=1)
            t_taem = taem_time_for_group(g, tcol)
            if t_taem is not None and np.isfinite(t_taem):
                ax.axvline(t_taem, linestyle=":", linewidth=1)
            ax.set_title(variable_label(var))
            ax.set_xlabel(time_label(tcol))
            ax.grid(True, alpha=0.3)
        fig.suptitle(f"TAEM diagnostics — {vehicle_label(gid)}")
        fig.tight_layout()
        fig.savefig(outdir / f"taem_diag_{idcol}_{gid}.png", dpi=200, bbox_inches="tight")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)


def make_summary(outdir: Path, df: pd.DataFrame, idcol: str, tcol: str):
    rows = []
    loncol = pick_first_existing(df, ["longitude", "lon", "lng"])
    latcol = pick_first_existing(df, ["latitude", "lat"])
    for gid, g in df.groupby(idcol):
        g = g.sort_values(tcol)
        t = safe_numeric(g[tcol])
        row = {"mis_id": gid}
        row["t_start"] = float(t.dropna().iloc[0]) if t.notna().any() else np.nan
        row["t_end"] = float(t.dropna().iloc[-1]) if t.notna().any() else np.nan
        for src, dst, fn in [
            ("height", "h_min_m", np.nanmin), ("height", "h_end_m", None),
            ("velocity", "v_min", np.nanmin), ("velocity", "v_end", None),
            ("q", "q_max", np.nanmax), ("s_go", "s_go_min", np.nanmin), ("L12D", "L12D_min", np.nanmin),
        ]:
            if src in g.columns:
                vals = safe_numeric(g[src])
                if fn is None:
                    row[dst] = float(vals.dropna().iloc[-1]) if vals.notna().any() else np.nan
                else:
                    row[dst] = float(fn(vals.to_numpy())) if vals.notna().any() else np.nan

        if "taem_reached" in g.columns:
            tm = pd.to_numeric(g["taem_reached"], errors="coerce").fillna(0).astype(float) > 0.5
            row["taem_reached_any"] = bool(tm.any())
            if tm.any():
                row["taem_first_t"] = float(pd.to_numeric(g.loc[tm, tcol], errors="coerce").iloc[0])
            row["taem_reached"] = bool(tm.any())

        for c in ["taem_h_err", "taem_v_err", "taem_s_go_err", "taem_dwell_count"]:
            if c in g.columns:
                vals = pd.to_numeric(g[c], errors="coerce")
                vals = vals.dropna()
                row[f"{c}_end"] = float(vals.iloc[-1]) if len(vals) else np.nan

        for c in ["taem_t_local", "taem_t_global"]:
            if c in g.columns:
                vals = safe_numeric(g[c]).dropna()
                row[c] = float(vals.iloc[0]) if len(vals) else np.nan
        if "taem_dwell_count" in g.columns:
            vals = safe_numeric(g["taem_dwell_count"])
            row["taem_dwell_count_max"] = float(vals.max()) if vals.notna().any() else 0.0
        if loncol and latcol:
            lon_deg = maybe_rad2deg(g[loncol])
            lat_deg = maybe_rad2deg(g[latcol])
            lon_vals = safe_numeric(lon_deg).dropna()
            lat_vals = safe_numeric(lat_deg).dropna()
            if len(lon_vals) and len(lat_vals):
                row["lon_start_deg"] = float(lon_vals.iloc[0])
                row["lat_start_deg"] = float(lat_vals.iloc[0])
                row["lon_end_deg"] = float(lon_vals.iloc[-1])
                row["lat_end_deg"] = float(lat_vals.iloc[-1])
        rows.append(row)
    pd.DataFrame(rows).to_csv(outdir / "summary_by_vehicle.csv", index=False)


def auto_vars(df: pd.DataFrame):
    preferred = ["height", "velocity", "q", "s_go", "L12D", "bank_angle", "attack_angle", "path_angle", "heading_angle", "CL", "CD", "L", "D", "E", "sigma_max", "box_score", "longitude", "latitude"]
    return [v for v in preferred if v in df.columns]


def main():
    args = parse_args()
    inp = Path(args.input)
    outdir = Path(args.outdir)
    ensure_dir(outdir)
    df = pd.read_csv(inp, low_memory=False)
    idcol = args.idcol if args.idcol and args.idcol in df.columns else ("mis_id" if "mis_id" in df.columns else None)
    if not idcol:
        df["mis_id"] = 0
        idcol = "mis_id"
    df = ensure_time_axes(df, idcol)
    if "box_score" not in df.columns and "taem_in_box" in df.columns:
        df["box_score"] = safe_numeric(df["taem_in_box"])
    tcol = pick_time_col(df, args.xcol)
    df = df.sort_values([idcol, tcol]).reset_index(drop=True)
    if args.downsample and args.downsample > 1:
        df = df.groupby(idcol, group_keys=False).apply(lambda g: g.iloc[::args.downsample]).reset_index(drop=True)
    vars_to_plot = args.vars if args.vars else auto_vars(df)
    pdf_path = outdir / "timeseries_plots.pdf"
    with PdfPages(pdf_path) as pdf:
        plot_ground_track(pdf, outdir, df, idcol)
        for var in vars_to_plot:
            if var == "longitude":
                tmp = df.copy(); tmp["longitude_deg"] = maybe_rad2deg(tmp[var]); plot_timeseries(pdf, outdir, tmp, idcol, tcol, "longitude_deg"); continue
            if var == "latitude":
                tmp = df.copy(); tmp["latitude_deg"] = maybe_rad2deg(tmp[var]); plot_timeseries(pdf, outdir, tmp, idcol, tcol, "latitude_deg"); continue
            plot_timeseries(pdf, outdir, df, idcol, tcol, var)
        plot_taem_diagnostics(pdf, outdir, df, idcol, tcol)
    make_summary(outdir, df, idcol, tcol)
    print(f"[OK] Wrote: {pdf_path}")
    print(f"[OK] Wrote: {outdir / 'summary_by_vehicle.csv'}")
    print(f"[INFO] PNGs are in: {outdir}")


if __name__ == "__main__":
    main()