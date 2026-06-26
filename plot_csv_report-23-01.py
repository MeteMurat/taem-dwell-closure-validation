#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robust plotting + reporting for multi-vehicle trajectory CSVs.

Key fixes vs many ad-hoc versions:
- Always create usable time axes (global_t, t_local) even if missing/NaN in the CSV.
- Safer numeric coercion (handles numpy scalars, 0-d/1-d arrays, and strings).
- Closest-approach report: stable indexing even when t_local is missing/NaN.
- Touchdown handling: uses explicit touchdown flag if present; otherwise uses min(height).
"""

from __future__ import annotations

import argparse
import math
import os
from typing import Optional, Dict, Any, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

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



# -----------------------------
# Utilities
# -----------------------------
EARTH_R_M = 6371000.0


def _to_scalar(v: Any) -> Any:
    """Convert numpy-ish types to python scalars where safe."""
    if v is None:
        return None
    if isinstance(v, (np.generic,)):
        return v.item()
    if isinstance(v, np.ndarray):
        if v.size == 0:
            return None
        if v.size == 1:
            return v.reshape(-1)[0].item()
        # Multi-element arrays should not be silently stringified into CSV.
        # Keep the last element (common pattern for 1xN histories) but mark it explicitly.
        return v.reshape(-1)[-1].item()
    return v


def safe_numeric(s: pd.Series) -> pd.Series:
    """Coerce a series to numeric robustly."""
    # Convert numpy-ish objects to scalars first
    s2 = s.map(_to_scalar)
    return pd.to_numeric(s2, errors="coerce")


def haversine_m(lon1_rad: float, lat1_rad: float, lon2_rad: float, lat2_rad: float) -> float:
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_R_M * c


def ensure_time_axes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure df has:
      - global_t: monotonically increasing global time
      - t_local: per-vehicle time relative to launch_time (if launch_time exists; otherwise equals global_t)

    Logic:
      - Prefer existing global_t if it has any finite values
      - Else prefer t if it has any finite values
      - Else fall back to index
    """
    out = df.copy()

    def _first_good(col: str) -> Optional[pd.Series]:
        if col not in out.columns:
            return None
        s = safe_numeric(out[col])
        if np.isfinite(s).any():
            return s
        return None

    base = _first_good("global_t")
    if base is None:
        base = _first_good("t")
    if base is None:
        base = pd.Series(np.arange(len(out), dtype=float), index=out.index)

    out["global_t"] = base

    # launch_time may be missing or per-row; treat missing as 0
    if "launch_time" in out.columns:
        lt = safe_numeric(out["launch_time"]).fillna(0.0)
    else:
        lt = pd.Series(0.0, index=out.index)

    out["t_local"] = out["global_t"] - lt

    return out


def pick_touchdown_row(g: pd.DataFrame) -> pd.Series:
    """Pick a representative touchdown row safely."""
    if "touchdown" in g.columns:
        td_mask = safe_numeric(g["touchdown"]).fillna(0.0) > 0.5
        td = g.loc[td_mask]
        if len(td) > 0:
            return td.iloc[0]

    # Fallback: minimum finite height
    if "height" in g.columns:
        h = safe_numeric(g["height"])
        h_valid = h.dropna()
        if len(h_valid) > 0:
            return g.loc[h_valid.idxmin()]

    return g.iloc[-1]


def maybe_lonlat_deg(row: pd.Series) -> Tuple[Optional[float], Optional[float]]:
    """Return lon/lat in degrees assuming input lon/lat are radians if abs(val) <= ~pi."""
    if "longitude" not in row or "latitude" not in row:
        return None, None
    lon = _to_scalar(row["longitude"])
    lat = _to_scalar(row["latitude"])
    if lon is None or lat is None:
        return None, None
    try:
        lon = float(lon)
        lat = float(lat)
    except Exception:
        return None, None

    # If values look like radians (typical range ~[-pi, pi]), convert
    if abs(lon) <= 4.0 and abs(lat) <= 2.0:
        return math.degrees(lon), math.degrees(lat)
    # Already degrees
    return lon, lat


# -----------------------------
# Reports
# -----------------------------
def make_closest_approach_report(df: pd.DataFrame, out_csv: str, t_post_s: float = 60.0) -> pd.DataFrame:
    """
    Create a closest-approach report per vehicle.

    Assumptions:
      - df includes mis_id
      - If dist_to_target_m exists, closest approach is its minimum.
        Else if s_go exists, closest approach is its minimum.
        Else falls back to minimum (height) as diagnostic.
    """
    if "mis_id" not in df.columns:
        raise ValueError("CSV must include mis_id column for multi-vehicle reporting.")

    # choose metric for CA
    metric = None
    if "dist_to_target_m" in df.columns:
        metric = "dist_to_target_m"
    elif "s_go" in df.columns:
        metric = "s_go"
    elif "height" in df.columns:
        metric = "height"

    rows = []
    for mid, g in df.groupby("mis_id"):
        g = g.sort_values("global_t")
        if metric is None:
            continue

        m = safe_numeric(g[metric])
        # CA index: minimum metric (for height, minimum height is "closest to ground", used only as fallback)
        i_ca = int(m.idxmin()) if np.isfinite(m).any() else int(g.index[-1])
        ca = g.loc[i_ca]

        # post row: first row with global_t >= ca.global_t + t_post_s, else last
        t_ca = float(_to_scalar(ca["global_t"]))
        g2 = g[g["global_t"] >= (t_ca + float(t_post_s))]
        rp = g2.iloc[0] if len(g2) else g.iloc[-1]

        # touchdown / end rows
        td = pick_touchdown_row(g)
        end = g.iloc[-1]

        ca_lon_deg, ca_lat_deg = maybe_lonlat_deg(ca)
        td_lon_deg, td_lat_deg = maybe_lonlat_deg(td)
        end_lon_deg, end_lat_deg = maybe_lonlat_deg(end)

        row: Dict[str, Any] = {
            "mis_id": int(mid),
            "metric": metric,
            "t_ca_s": float(_to_scalar(ca.get("global_t", np.nan))),
            "t_post_s": float(t_post_s),
            "t_post_row_s": float(_to_scalar(rp.get("global_t", np.nan))),
            "ca_lon_deg": ca_lon_deg,
            "ca_lat_deg": ca_lat_deg,
            "td_t_s": float(_to_scalar(td.get("global_t", np.nan))),
            "td_lon_deg": td_lon_deg,
            "td_lat_deg": td_lat_deg,
            "end_t_s": float(_to_scalar(end.get("global_t", np.nan))),
            "end_lon_deg": end_lon_deg,
            "end_lat_deg": end_lat_deg,
        }

        # Optional diagnostics if present
        for col in [
            "guide_phase", "end_guide", "end_reason", "touchdown",
            "psi_bias_state", "psi_bias_raw", "psi_bias_clipped", "psi_bias_rate_limited",
            "heading_error", "cross_track_error", "s_go", "height", "velocity",
            "bank_angle", "attack_angle", "CL", "CD", "L", "D", "q",
            "tar_lon_deg", "tar_lat_deg",
        ]:
            if col in df.columns:
                row[f"ca_{col}"] = _to_scalar(ca.get(col))
                row[f"post_{col}"] = _to_scalar(rp.get(col))
                row[f"td_{col}"] = _to_scalar(td.get(col))
                row[f"end_{col}"] = _to_scalar(end.get(col))

        # Derived: distance from touchdown to target if target is provided (degrees)
        if td_lon_deg is not None and td_lat_deg is not None and "tar_lon_deg" in df.columns and "tar_lat_deg" in df.columns:
            tar_lon = float(_to_scalar(ca.get("tar_lon_deg", np.nan)))
            tar_lat = float(_to_scalar(ca.get("tar_lat_deg", np.nan)))
            if np.isfinite(tar_lon) and np.isfinite(tar_lat):
                row["td_to_target_m"] = haversine_m(
                    math.radians(td_lon_deg), math.radians(td_lat_deg),
                    math.radians(tar_lon), math.radians(tar_lat)
                )

        rows.append(row)

    rep = pd.DataFrame(rows)
    rep.to_csv(out_csv, index=False)
    return rep


def summary_by_vehicle(df: pd.DataFrame, out_csv: str) -> pd.DataFrame:
    """
    Basic per-vehicle summary (time bounds, min height, touchdown, etc.)
    """
    if "mis_id" not in df.columns:
        raise ValueError("CSV must include mis_id column.")
    rows = []
    for mid, g in df.groupby("mis_id"):
        g = g.sort_values("global_t")
        row: Dict[str, Any] = {"mis_id": int(mid)}
        row["t_start_s"] = float(g["global_t"].iloc[0])
        row["t_end_s"] = float(g["global_t"].iloc[-1])

        if "height" in g.columns:
            h = safe_numeric(g["height"])
            row["h_min_m"] = float(h.min()) if np.isfinite(h).any() else np.nan
            row["h_end_m"] = float(_to_scalar(g["height"].iloc[-1]))
        if "touchdown" in g.columns:
            td = g[g["touchdown"].astype(bool)]
            row["touchdown_any"] = bool(len(td) > 0)
            if len(td) > 0:
                row["touchdown_t_s"] = float(_to_scalar(td["global_t"].iloc[0]))
        if "s_go" in g.columns:
            s = safe_numeric(g["s_go"])
            if np.isfinite(s).any():
                j = int(s.idxmin())
                row["s_go_min_m"] = float(s.min())
                row["s_go_min_t_s"] = float(_to_scalar(g.loc[j, "global_t"]))

        if "taem_reached" in g.columns:
            tm = pd.to_numeric(g["taem_reached"], errors="coerce").fillna(0).astype(float) > 0.5
            row["taem_reached_any"] = bool(tm.any())
            if tm.any():
                row["taem_first_t"] = float(pd.to_numeric(g.loc[tm, "global_t"], errors="coerce").iloc[0])

        if "taem_dwell_count" in g.columns:
            dwell = pd.to_numeric(g["taem_dwell_count"], errors="coerce")
            if dwell.notna().any():
                row["taem_dwell_max"] = float(dwell.max())

        for c in ["taem_h_err", "taem_v_err", "taem_s_go_err", "taem_dwell_count"]:
            if c in g.columns:
                vals = pd.to_numeric(g[c], errors="coerce")
                if vals.notna().any():
                    row[f"{c}_end"] = float(vals.iloc[-1])

        rows.append(row)

    rep = pd.DataFrame(rows).sort_values("mis_id")
    rep.to_csv(out_csv, index=False)
    return rep

def plot_vs_time(df: pd.DataFrame, ycol: str, out_png: str, xlabel: str = "t_local", title: Optional[str] = None):
    if "mis_id" not in df.columns:
        raise ValueError("CSV must include mis_id column.")
    if ycol not in df.columns:
        raise ValueError(f"Missing column: {ycol}")

    # Choose x: prefer t_local if it has finite values; else use global_t
    x = df["t_local"]
    if not np.isfinite(safe_numeric(x)).any():
        xname = "global_t"
    else:
        xname = "t_local"

    plt.figure(figsize=(8, 6))
    for mid, g in df.groupby("mis_id"):
        gx = safe_numeric(g[xname])
        gy = safe_numeric(g[ycol])
        m = np.isfinite(gx) & np.isfinite(gy)
        plt.plot(gx[m], gy[m], label=vehicle_label(mid))

        if "taem_reached" in g.columns:
            taem_mask = pd.to_numeric(g["taem_reached"], errors="coerce").fillna(0).astype(float) > 0.5
            if taem_mask.any():
                t_taem = float(pd.to_numeric(g.loc[taem_mask, xname], errors="coerce").iloc[0])
                if np.isfinite(t_taem):
                    plt.axvline(t_taem, linestyle="--", linewidth=1.0, alpha=0.8)

    plt.xlabel(xlabel if xname == "t_local" else "t (global)")
    plt.ylabel(ycol)
    plt.title(title if title else f"{ycol} vs {xlabel}")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()

def plot_ground_track(df: pd.DataFrame, out_png: str):
    if "mis_id" not in df.columns or "longitude" not in df.columns or "latitude" not in df.columns:
        raise ValueError("CSV must include mis_id, longitude, latitude")

    plt.figure(figsize=(8, 6))
    for mid, g in df.groupby("mis_id"):
        lon = safe_numeric(g["longitude"])
        lat = safe_numeric(g["latitude"])
        m = np.isfinite(lon) & np.isfinite(lat)
        # assume radians if magnitude looks like radians
        lon_d = np.degrees(lon[m].to_numpy()) if (np.nanmax(np.abs(lon[m])) <= 4.0) else lon[m].to_numpy()
        lat_d = np.degrees(lat[m].to_numpy()) if (np.nanmax(np.abs(lat[m])) <= 2.0) else lat[m].to_numpy()
        plt.plot(lon_d, lat_d, label=vehicle_label(mid))

        # Mark touchdown if present
        if "touchdown" in g.columns:
            td = g[g["touchdown"].astype(bool)]
            if len(td) > 0:
                tlon = float(_to_scalar(td["longitude"].iloc[0]))
                tlat = float(_to_scalar(td["latitude"].iloc[0]))
                tlon_d = math.degrees(tlon) if abs(tlon) <= 4.0 else tlon
                tlat_d = math.degrees(tlat) if abs(tlat) <= 2.0 else tlat
                plt.scatter([tlon_d], [tlat_d], s=60)

    plt.xlabel("Longitude (deg)")
    plt.ylabel("Latitude (deg)")
    plt.title("Ground track (lon-lat)")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close()


# -----------------------------
# CLI
# -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--csv",
        default=None,
        help="Input simulation CSV (default: auto-detect store/data_saved/multiSimulation_case.csv)"
    )
    ap.add_argument(
        "--outdir",
        default=None,
        help="Output directory (default: <csv_dir>/report)"
    )
    ap.add_argument("--t_post_s", type=float, default=60.0, help="Seconds after CA for post snapshot")
    args = ap.parse_args()

    # -----------------------------
    # Auto-detect CSV if not given
    # -----------------------------
    here = os.path.dirname(os.path.abspath(__file__))

    # If user did not provide --csv, we assume canonical name
    req_name = args.csv if args.csv else "multiSimulation_case.csv"

    # Candidate search order (most reliable first)
    candidates = []

    # 0) If user gave an absolute/relative path, try it as-is
    candidates.append(req_name)

    # 1) Try store/data_saved relative to script directory
    candidates.append(os.path.join(here, "store", "data_saved", req_name))

    # 2) Try store/data_saved relative to current working dir
    candidates.append(os.path.join(os.getcwd(), "store", "data_saved", req_name))

    # 3) If user omitted extension, try adding .csv (both bases)
    if not req_name.lower().endswith(".csv"):
        candidates.append(req_name + ".csv")
        candidates.append(os.path.join(here, "store", "data_saved", req_name + ".csv"))
        candidates.append(os.path.join(os.getcwd(), "store", "data_saved", req_name + ".csv"))

    # 4) Optional: try multiset.STORE_DATA if available
    try:
        import multiset as glbs  # type: ignore
        sd = getattr(glbs, "STORE_DATA", None)
        if isinstance(sd, str) and sd:
            candidates.insert(1, sd)  # high priority
    except Exception:
        pass

    csv_path = None
    for p in candidates:
        if p and os.path.exists(p):
            csv_path = p
            break

    if csv_path is None:
        msg = "CSV bulunamadı. Denenen yollar:\n" + "\n".join([f"  - {p}" for p in candidates if p])
        raise FileNotFoundError(msg)

    # -----------------------------
    # Output directory
    # -----------------------------
    csv_dir = os.path.dirname(os.path.abspath(csv_path))
    outdir = args.outdir if args.outdir else os.path.join(csv_dir, "report")
    os.makedirs(outdir, exist_ok=True)

    print(f"[plot_csv_report] Using CSV: {csv_path}")
    print(f"[plot_csv_report] Output dir: {outdir}")

    # -----------------------------
    # Load + process
    # -----------------------------
    df = pd.read_csv(csv_path, low_memory=False)
    df = ensure_time_axes(df)

    # Reports
    make_closest_approach_report(df, os.path.join(outdir, "closest_approach_report.csv"), t_post_s=args.t_post_s)
    summary_by_vehicle(df, os.path.join(outdir, "summary_by_vehicle.csv"))

    # Plots (add/remove as needed)
    for col in [
        "height", "velocity", "s_go",
        "attack_angle", "bank_angle", "heading_angle", "path_angle",
        "CL", "CD", "L", "D", "q",
        "L12D",
    ]:
        if col in df.columns:
            plot_vs_time(
                df, col,
                os.path.join(outdir, f"{col}_vs_t_local.png"),
                xlabel="t_local",
                title=f"{col} vs t_local"
            )

    # Ground track
    if ("longitude" in df.columns) and ("latitude" in df.columns):
        plot_ground_track(df, os.path.join(outdir, "ground_track_lonlat.png"))



if __name__ == "__main__":
    main()