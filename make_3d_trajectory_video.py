#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_3d_trajectory_video.py

Create a publication/supplementary 3D trajectory animation from a multi-vehicle CSV.

Inputs expected by default:
  - mis_id or another vehicle identifier column
  - global_t or another time column
  - longitude, latitude, height/altitude columns

Outputs:
  - MP4 if ffmpeg is available and --out ends with .mp4
  - GIF if --out ends with .gif or MP4 writer is unavailable
  - Optional static PDF/PNG of the final 3D trajectories

Example:
  python make_3d_trajectory_video.py \
    --input store/data_saved/phase2_B5D_tight_local_envelope_validation_report/representative_success.csv \
    --out figs/supp_movie_S1_role_distinct_trajectory.mp4 \
    --idcol mis_id --tcol global_t --downsample 20 --fps 20 --max_frames 500 \
    --trail_len 80 --static_out figs/fig06_representative_3D_trajectory_professional.pdf
"""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter


def vehicle_label(gid) -> str:
    """Return manuscript-friendly labels: Vehicle 1, Vehicle 2, ..."""
    try:
        return f"Vehicle {int(float(gid)) + 1}"
    except Exception:
        return f"Vehicle {gid}"


def maybe_rad2deg(values: np.ndarray) -> np.ndarray:
    """If values look like radians, convert to degrees."""
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return arr
    if np.nanmax(np.abs(finite)) < 6.5:
        return np.degrees(arr)
    return arr


def pick_col(df: pd.DataFrame, candidates: List[str], required: bool = False) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        raise SystemExit(f"Missing required column. Tried: {candidates}")
    return None


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Input trajectory CSV")
    ap.add_argument("--out", required=True, help="Output animation path: .mp4 or .gif")
    ap.add_argument("--static_out", default=None, help="Optional static final-trajectory figure path: .pdf/.png")
    ap.add_argument("--idcol", default=None, help="Vehicle ID column; default tries mis_id")
    ap.add_argument("--tcol", default=None, help="Time column; default tries global_t, t_local, t")
    ap.add_argument("--loncol", default=None, help="Longitude column; default tries longitude/lon/lng")
    ap.add_argument("--latcol", default=None, help="Latitude column; default tries latitude/lat")
    ap.add_argument("--hcol", default=None, help="Altitude column; default tries height/altitude/h")
    ap.add_argument("--downsample", type=int, default=10, help="Keep every Nth sample per vehicle before animation")
    ap.add_argument("--fps", type=int, default=20, help="Frames per second")
    ap.add_argument("--max_frames", type=int, default=600, help="Maximum number of animation frames")
    ap.add_argument("--trail_len", type=int, default=100, help="Number of retained samples in the moving trail")
    ap.add_argument("--dpi", type=int, default=180, help="Animation DPI")
    ap.add_argument("--title", default="Role-distinct multi-vehicle entry trajectories", help="Animation title")
    ap.add_argument("--elev", type=float, default=24.0, help="3D view elevation angle")
    ap.add_argument("--azim", type=float, default=-62.0, help="3D view azimuth angle")
    return ap.parse_args()


def load_groups(args: argparse.Namespace) -> Tuple[Dict[object, pd.DataFrame], str, str, str, str, str]:
    df = pd.read_csv(args.input)

    idcol = args.idcol or ("mis_id" if "mis_id" in df.columns else None)
    if not idcol or idcol not in df.columns:
        df["__vehicle_id__"] = 0
        idcol = "__vehicle_id__"

    tcol = args.tcol or pick_col(df, ["global_t", "t_local", "t"], required=False)
    if not tcol or tcol not in df.columns:
        df["__time__"] = np.arange(len(df), dtype=float)
        tcol = "__time__"

    loncol = args.loncol or pick_col(df, ["longitude", "lon", "lng"], required=True)
    latcol = args.latcol or pick_col(df, ["latitude", "lat"], required=True)
    hcol = args.hcol or pick_col(df, ["height", "altitude", "h"], required=True)

    df = df.sort_values([idcol, tcol]).reset_index(drop=True)
    df["_lon_deg"] = maybe_rad2deg(pd.to_numeric(df[loncol], errors="coerce").to_numpy())
    df["_lat_deg"] = maybe_rad2deg(pd.to_numeric(df[latcol], errors="coerce").to_numpy())
    df["_alt_m"] = pd.to_numeric(df[hcol], errors="coerce").to_numpy(dtype=float)
    df["_time"] = pd.to_numeric(df[tcol], errors="coerce").to_numpy(dtype=float)

    groups: Dict[object, pd.DataFrame] = {}
    step = max(1, int(args.downsample))
    for gid, g in df.groupby(idcol):
        gg = g.sort_values(tcol).iloc[::step].copy().reset_index(drop=True)
        gg = gg[np.isfinite(gg["_lon_deg"]) & np.isfinite(gg["_lat_deg"]) & np.isfinite(gg["_alt_m"])]
        if len(gg) > 1:
            groups[gid] = gg.reset_index(drop=True)

    if not groups:
        raise SystemExit("No usable trajectory groups found after column selection/downsampling.")

    return groups, idcol, tcol, loncol, latcol, hcol


def compute_limits(groups: Dict[object, pd.DataFrame]) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    lon = np.concatenate([g["_lon_deg"].to_numpy(float) for g in groups.values()])
    lat = np.concatenate([g["_lat_deg"].to_numpy(float) for g in groups.values()])
    alt = np.concatenate([g["_alt_m"].to_numpy(float) for g in groups.values()])

    def pad_lim(a: np.ndarray, frac: float = 0.06, min_pad: float = 1.0) -> Tuple[float, float]:
        lo = float(np.nanmin(a)); hi = float(np.nanmax(a))
        pad = max(min_pad, (hi - lo) * frac)
        return lo - pad, hi + pad

    return pad_lim(lon), pad_lim(lat), pad_lim(alt, min_pad=1000.0)


def make_frame_indices(groups: Dict[object, pd.DataFrame], max_frames: int) -> np.ndarray:
    max_len = max(len(g) for g in groups.values())
    if max_len <= max_frames:
        return np.arange(max_len, dtype=int)
    return np.linspace(0, max_len - 1, int(max_frames)).round().astype(int)


def draw_static(groups: Dict[object, pd.DataFrame], static_out: str, title: str, elev: float, azim: float) -> None:
    out = Path(static_out)
    out.parent.mkdir(parents=True, exist_ok=True)

    xlim, ylim, zlim = compute_limits(groups)
    fig = plt.figure(figsize=(7.2, 5.6))
    ax = fig.add_subplot(111, projection="3d")

    for gid, g in groups.items():
        label = vehicle_label(gid)
        ax.plot(g["_lon_deg"], g["_lat_deg"], g["_alt_m"], label=label)
        ax.scatter(g["_lon_deg"].iloc[0], g["_lat_deg"].iloc[0], g["_alt_m"].iloc[0], marker="o", s=22)
        ax.scatter(g["_lon_deg"].iloc[-1], g["_lat_deg"].iloc[-1], g["_alt_m"].iloc[-1], marker="^", s=28)

    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_zlim(*zlim)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_zlabel("Altitude (m)")
    ax.set_title(title)
    ax.view_init(elev=elev, azim=azim)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] wrote static figure: {out}")


def animate(groups: Dict[object, pd.DataFrame], out_path: str, args: argparse.Namespace) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    frame_indices = make_frame_indices(groups, args.max_frames)
    xlim, ylim, zlim = compute_limits(groups)

    fig = plt.figure(figsize=(7.2, 5.6))
    ax = fig.add_subplot(111, projection="3d")

    gids = list(groups.keys())
    lines = {}
    markers = {}
    for gid in gids:
        (line,) = ax.plot([], [], [], lw=1.8, label=vehicle_label(gid))
        (marker,) = ax.plot([], [], [], marker="o", markersize=5, linestyle="")
        lines[gid] = line
        markers[gid] = marker

    ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.set_zlim(*zlim)
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_zlabel("Altitude (m)")
    ax.set_title(args.title)
    ax.view_init(elev=args.elev, azim=args.azim)
    ax.legend(loc="best", fontsize=8)

    def update(frame_number: int):
        fi = int(frame_indices[frame_number])
        for gid in gids:
            g = groups[gid]
            idx = min(fi, len(g) - 1)
            start = max(0, idx - int(args.trail_len))
            xs = g["_lon_deg"].iloc[start:idx + 1].to_numpy(float)
            ys = g["_lat_deg"].iloc[start:idx + 1].to_numpy(float)
            zs = g["_alt_m"].iloc[start:idx + 1].to_numpy(float)
            lines[gid].set_data(xs, ys)
            lines[gid].set_3d_properties(zs)
            markers[gid].set_data([xs[-1]], [ys[-1]])
            markers[gid].set_3d_properties([zs[-1]])
        ax.set_title(f"{args.title} | frame {frame_number + 1}/{len(frame_indices)}")
        return list(lines.values()) + list(markers.values())

    anim = FuncAnimation(fig, update, frames=len(frame_indices), interval=1000 / max(1, args.fps), blit=False)

    suffix = out.suffix.lower()
    if suffix == ".mp4" and shutil.which("ffmpeg"):
        writer = FFMpegWriter(fps=args.fps, bitrate=2400)
        anim.save(str(out), writer=writer, dpi=args.dpi)
        print(f"[OK] wrote MP4 animation: {out}")
    else:
        if suffix != ".gif":
            out = out.with_suffix(".gif")
            print("[WARN] ffmpeg not found or non-MP4 writer unavailable; writing GIF instead.")
        writer = PillowWriter(fps=args.fps)
        anim.save(str(out), writer=writer, dpi=args.dpi)
        print(f"[OK] wrote GIF animation: {out}")

    plt.close(fig)


def main() -> None:
    args = parse_args()
    groups, *_ = load_groups(args)
    if args.static_out:
        draw_static(groups, args.static_out, args.title, args.elev, args.azim)
    animate(groups, args.out, args)


if __name__ == "__main__":
    main()
