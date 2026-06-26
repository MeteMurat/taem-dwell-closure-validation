# -*- coding: utf-8 -*-
r"""B6 trajectory figures - FAST professional label revision v3.

Post-processing only. Does not run simulation or modify guidance.
Default behavior avoids broad recursive scans under store/data_saved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, List, Tuple, Dict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

OUTDIR_DEFAULT = Path("store/data_saved/phase2_B6_trajectory_figures_professional_fast_v3")

KNOWN_SUCCESS_CSVS = [
    Path("store/data_saved/phase2_B5D_tight_local_envelope_validation/case_reports/b5c000_hp173p144_vm1p127/phase2_B5A_hp173p144m_vm1p12688mps_sp2deg_combined.csv"),
    Path("store/data_saved/phase2_B5D_tight_local_envelope_validation_report/case_reports/b5c000_hp173p144_vm1p127/phase2_B5A_hp173p144m_vm1p12688mps_sp2deg_combined.csv"),
]

INVENTORY_CSVS = [
    Path("store/data_saved/phase2_B6_trajectory_figures_v2/trajectory_candidate_inventory.csv"),
    Path("store/data_saved/phase2_B6_trajectory_figures/trajectory_candidate_inventory.csv"),
]

B5D_SEARCH_ROOTS = [
    Path("store/data_saved/phase2_B5D_tight_local_envelope_validation/case_reports"),
    Path("store/data_saved/phase2_B5D_tight_local_envelope_validation_report/case_reports"),
]

LON_CANDS = ["longitude", "lon", "lng"]
LAT_CANDS = ["latitude", "lat"]
H_CANDS = ["height", "altitude", "h"]
T_CANDS = ["t_local", "global_t", "t"]
ID_CANDS = ["mis_id", "vehicle_id", "id"]
VEL_CANDS = ["velocity", "v"]
SGO_CANDS = ["s_go", "sgo", "range_to_go"]
BANK_CANDS = ["bank_angle", "sigma", "bank"]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def first_col(df: pd.DataFrame, names: List[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    s = df[col]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0) > 0.5
    return s.astype(str).str.lower().str.strip().isin(["1", "true", "t", "yes", "y", "pass", "pass_strict"])


def maybe_rad_to_deg(s: pd.Series) -> pd.Series:
    x = safe_num(s).astype(float)
    mx = np.nanmax(np.abs(x.to_numpy())) if len(x) else np.nan
    if np.isfinite(mx) and mx < 6.5:
        return pd.Series(np.degrees(x), index=s.index)
    return x


def angle_to_deg_if_needed(s: pd.Series) -> pd.Series:
    return maybe_rad_to_deg(s)


def vehicle_label(gid) -> str:
    try:
        return f"Vehicle {int(float(gid)) + 1}"
    except Exception:
        return "Vehicle"


def save_fig(fig, outdir: Path, stem: str) -> List[str]:
    ensure_dir(outdir)
    png = outdir / f"{stem}.png"
    pdf = outdir / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return [str(png), str(pdf)]


def header_has_trajectory_cols(path: Path) -> bool:
    try:
        cols = pd.read_csv(path, nrows=3).columns
    except Exception:
        return False
    return any(c in cols for c in LON_CANDS) and any(c in cols for c in LAT_CANDS) and any(c in cols for c in H_CANDS)


def pick_success_csv(root: Path, manual: Optional[str] = None, allow_search: bool = False, max_files: int = 200) -> Optional[Path]:
    if manual:
        p = Path(manual)
        if not p.is_absolute():
            p = root / p
        return p if p.exists() else None

    for rel in KNOWN_SUCCESS_CSVS:
        p = root / rel
        if p.exists():
            return p

    for inv_rel in INVENTORY_CSVS:
        inv = root / inv_rel
        if inv.exists():
            try:
                d = pd.read_csv(inv)
                if "path" not in d.columns:
                    continue
                mask = d["path"].astype(str).str.lower().str.contains("b5d|tight_local|local_envelope", regex=True)
                if "physical_ok" in d.columns:
                    mask &= d["physical_ok"].astype(str).str.lower().isin(["true", "1", "yes"])
                dd = d.loc[mask].copy()
                if len(dd):
                    if "success_score" in dd.columns:
                        dd["_score"] = pd.to_numeric(dd["success_score"], errors="coerce").fillna(-1e9)
                        dd = dd.sort_values("_score", ascending=False)
                    for raw in dd["path"].astype(str).tolist():
                        p = Path(raw)
                        if not p.is_absolute():
                            p = root / p
                        if p.exists():
                            return p
            except Exception:
                pass

    if not allow_search:
        return None

    checked = 0
    candidates: List[Tuple[int, Path]] = []
    for sr_rel in B5D_SEARCH_ROOTS:
        sr = root / sr_rel
        if not sr.exists():
            continue
        for p in sr.rglob("*.csv"):
            checked += 1
            if checked > max_files:
                break
            s = str(p).lower()
            if "b5e" in s or "b5f" in s:
                continue
            if header_has_trajectory_cols(p):
                score = 0
                if "b5d" in s: score += 100
                if "tight_local" in s or "local_envelope" in s: score += 80
                if "combined" in p.name.lower(): score += 40
                candidates.append((score, p))
        if checked > max_files:
            break
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]


def load_trajectory(path: Path) -> Tuple[pd.DataFrame, Dict[str, str]]:
    df = pd.read_csv(path, low_memory=False).copy()
    idc = first_col(df, ID_CANDS)
    if idc is None:
        idc = "mis_id"
        df[idc] = 0
    tc = first_col(df, T_CANDS)
    if tc is None:
        df["_time"] = np.arange(len(df), dtype=float)
    else:
        df["_time"] = safe_num(df[tc]).astype(float)
        if df["_time"].isna().all():
            df["_time"] = np.arange(len(df), dtype=float)
    lon = first_col(df, LON_CANDS)
    lat = first_col(df, LAT_CANDS)
    h = first_col(df, H_CANDS)
    if lon is None or lat is None or h is None:
        raise ValueError(f"Trajectory CSV missing longitude/latitude/height columns: {path}")
    df["_lon_deg"] = maybe_rad_to_deg(df[lon])
    df["_lat_deg"] = maybe_rad_to_deg(df[lat])
    df["_alt_km"] = safe_num(df[h]).astype(float) / 1000.0
    df["_t_local"] = df["_time"] - df.groupby(idc)["_time"].transform("min")
    return df, {"idc": idc, "time": tc or "_time", "lon": lon, "lat": lat, "h": h}


def taem_marker_time(g: pd.DataFrame) -> Optional[float]:
    for c in ["taem_success_latched", "taem_reached", "taem_in_box"]:
        if c in g.columns:
            bs = bool_series(g, c)
            if bs.any():
                vals = safe_num(g.loc[bs, "_t_local"]).dropna()
                if len(vals):
                    return float(vals.iloc[0])
    sgo = first_col(g, SGO_CANDS)
    if sgo and "STAEM" in g.columns:
        diff = (safe_num(g[sgo]) - safe_num(g["STAEM"])).abs()
        if diff.notna().any():
            idx = diff.idxmin()
            val = safe_num(pd.Series([g.loc[idx, "_t_local"]])).iloc[0]
            if pd.notna(val):
                return float(val)
    if "TAEM range-to-go-error" in g.columns:
        diff = safe_num(g["TAEM range-to-go-error"]).abs()
        if diff.notna().any():
            idx = diff.idxmin()
            val = safe_num(pd.Series([g.loc[idx, "_t_local"]])).iloc[0]
            if pd.notna(val):
                return float(val)
    return None


def plot_ground_track(outdir: Path, df: pd.DataFrame, meta: Dict[str, str]) -> List[str]:
    idc = meta["idc"]
    fig = plt.figure(figsize=(8.8, 6.0))
    ax = fig.add_subplot(1, 1, 1)
    for gid, g in df.groupby(idc):
        g = g.sort_values("_time")
        x = safe_num(g["_lon_deg"]); y = safe_num(g["_lat_deg"])
        m = x.notna() & y.notna()
        if not m.any(): continue
        ax.plot(x[m], y[m], linewidth=2.0, label=vehicle_label(gid))
        ax.plot(float(x[m].iloc[0]), float(y[m].iloc[0]), marker="o", markersize=6)
        ax.plot(float(x[m].iloc[-1]), float(y[m].iloc[-1]), marker="x", markersize=7)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Representative successful ground track")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", frameon=True)
    fig.tight_layout()
    return save_fig(fig, outdir, "figT01_success_ground_track_professional")


def plot_3d(outdir: Path, df: pd.DataFrame, meta: Dict[str, str]) -> List[str]:
    idc = meta["idc"]
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    fig = plt.figure(figsize=(9.0, 7.0))
    ax = fig.add_subplot(1, 1, 1, projection="3d")
    for gid, g in df.groupby(idc):
        g = g.sort_values("_time")
        x = safe_num(g["_lon_deg"]); y = safe_num(g["_lat_deg"]); z = safe_num(g["_alt_km"])
        m = x.notna() & y.notna() & z.notna()
        if not m.any(): continue
        ax.plot(x[m], y[m], z[m], linewidth=2.0, label=vehicle_label(gid))
        ax.scatter([float(x[m].iloc[0])], [float(y[m].iloc[0])], [float(z[m].iloc[0])], marker="o", s=30)
        ax.scatter([float(x[m].iloc[-1])], [float(y[m].iloc[-1])], [float(z[m].iloc[-1])], marker="x", s=40)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_zlabel("Altitude (km)")
    ax.set_title("Representative successful 3D trajectory")
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    files = save_fig(fig, outdir, "figT02_success_3d_trajectory_professional")
    try:
        import plotly.graph_objects as go
        pfig = go.Figure()
        for gid, g in df.groupby(idc):
            g = g.sort_values("_time")
            pfig.add_trace(go.Scatter3d(x=g["_lon_deg"], y=g["_lat_deg"], z=g["_alt_km"], mode="lines", name=vehicle_label(gid)))
        pfig.update_layout(title="Representative successful 3D trajectory", scene=dict(xaxis_title="Longitude (deg)", yaxis_title="Latitude (deg)", zaxis_title="Altitude (km)"), legend=dict(itemsizing="constant"))
        html = outdir / "figT02_success_3d_trajectory_professional.html"
        pfig.write_html(str(html), include_plotlyjs="cdn")
        files.append(str(html))
    except Exception as exc:
        note = outdir / "figT02_interactive_html_not_generated.txt"
        note.write_text(f"Plotly HTML not generated: {exc}\n", encoding="utf-8")
        files.append(str(note))
    return files


def plot_time_history(outdir: Path, df: pd.DataFrame, meta: Dict[str, str]) -> List[str]:
    idc = meta["idc"]
    fig, axes = plt.subplots(4, 1, figsize=(10.2, 12.0), sharex=True)
    for gid, g in df.groupby(idc):
        g = g.sort_values("_time")
        x = safe_num(g["_t_local"]).astype(float)
        y = safe_num(g[meta["h"]]).astype(float) / 1000.0
        m = x.notna() & y.notna()
        if m.any(): axes[0].plot(x[m], y[m], linewidth=1.6, label=vehicle_label(gid))
        vc = first_col(g, VEL_CANDS)
        if vc:
            y = safe_num(g[vc]).astype(float) / 1000.0
            m = x.notna() & y.notna()
            if m.any(): axes[1].plot(x[m], y[m], linewidth=1.6, label=vehicle_label(gid))
        sc = first_col(g, SGO_CANDS)
        if sc:
            y = safe_num(g[sc]).astype(float) / 1000.0
            m = x.notna() & y.notna()
            if m.any(): axes[2].plot(x[m], y[m], linewidth=1.6, label=vehicle_label(gid))
        bc = first_col(g, BANK_CANDS)
        if bc:
            y = angle_to_deg_if_needed(g[bc])
            m = x.notna() & y.notna()
            if m.any(): axes[3].plot(x[m], y[m], linewidth=1.6, label=vehicle_label(gid))
        tm = taem_marker_time(g)
        if tm is not None:
            for ax in axes:
                ax.axvline(tm, linestyle="--", linewidth=0.9, alpha=0.6)
    labels = ["Altitude (km)", "Velocity (km/s)", "Range-to-go (km)", "Bank angle (deg)"]
    for ax, lab in zip(axes, labels):
        ax.set_ylabel(lab)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", frameon=True, fontsize=8)
    axes[-1].set_xlabel("Local time (s)")
    fig.suptitle("Representative TAEM approach time history")
    fig.tight_layout()
    return save_fig(fig, outdir, "figT03_taem_approach_time_history_professional")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--success-csv", default=None, help="Optional explicit B5D successful trajectory CSV.")
    ap.add_argument("--allow-search", action="store_true", help="Allow bounded B5D-only search if known/inventory paths fail.")
    ap.add_argument("--outdir", default=str(OUTDIR_DEFAULT))
    args = ap.parse_args()
    root = Path.cwd()
    outdir = root / Path(args.outdir)
    ensure_dir(outdir)
    traj = pick_success_csv(root, manual=args.success_csv, allow_search=args.allow_search, max_files=200)
    if traj is None:
        raise SystemExit("[ERR] No B5D successful trajectory CSV found. Run with --success-csv or rerun B5D trajectory generation.")
    df, meta = load_trajectory(traj)
    generated = []
    generated += plot_ground_track(outdir, df, meta)
    generated += plot_3d(outdir, df, meta)
    generated += plot_time_history(outdir, df, meta)
    note = outdir / "figT04_skipped_note.txt"
    note.write_text("Figure T4 skipped: no confirmed B5E/B5F physical boundary trajectory was selected by the fast script.\n", encoding="utf-8")
    generated.append(str(note))
    captions = outdir / "phase2_B6_trajectory_figure_captions_professional.txt"
    captions.write_text("Figure T1. Representative successful ground track for the bounded local U3 envelope.\nFigure T2. Representative successful 3D trajectory for the bounded local U3 envelope.\nFigure T3. Representative TAEM approach time history with professional vehicle and range-to-go labels.\n", encoding="utf-8")
    generated.append(str(captions))
    manifest = {"success_csv": str(traj), "generated_files": generated}
    mp = outdir / "phase2_B6_trajectory_figures_professional_manifest.json"
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[B6-TRAJ-FAST] Done.")
    print("[B6-TRAJ-FAST] Output dir:", outdir)
    print("[B6-TRAJ-FAST] Success CSV:", traj)
    for f in generated:
        print(" -", f)


if __name__ == "__main__":
    main()
