# -*- coding: utf-8 -*-
"""
visualize_3d_anim_safe_fixed.py
Memory-safe 3D multi-trajectory visualization (Plotly) with optional animation + trail.

Key features:
- Supports multiple vehicles using an ID column (default: mis_id if present).
- Auto-detects radians vs degrees for latitude/longitude.
- Prevents MemoryError by limiting frames via --frame_stride and --max_frames.
- Provides --static mode (no animation; very light).

Example (static):
python visualize_3d_anim_safe_fixed.py --input store/data_saved/multiSimulation_case.csv --out store/data_saved/multi_3d_static.html --idcol mis_id --static --downsample 10

Example (animated trail):
python visualize_3d_anim_safe_fixed.py --input store/data_saved/multiSimulation_case.csv --out store/data_saved/multi_3d_trail.html --idcol mis_id --trail --trail_len 80 --downsample 10 --frame_stride 20 --max_frames 1200
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

def vehicle_label(gid) -> str:
    """Return a publication-friendly vehicle label: Vehicle 1, Vehicle 2, ..."""
    try:
        return f"Vehicle {int(float(gid)) + 1}"
    except Exception:
        return "Vehicle"



def maybe_rad2deg(arr: np.ndarray) -> np.ndarray:
    """Heuristic conversion: if values look like radians (|max| < ~2*pi), convert to degrees."""
    mx = np.nanmax(np.abs(arr))
    if np.isfinite(mx) and mx < 6.5:
        return np.degrees(arr)
    return arr


def _pick_col(df, candidates, required=False):
    for c in candidates:
        if c in df.columns:
            return c
    if required:
        raise SystemExit(f"CSV missing required column(s): tried {candidates}")
    return None


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV path")
    ap.add_argument("--out", required=True, help="Output HTML path")
    ap.add_argument("--idcol", default=None, help="Vehicle id column (e.g., mis_id). If omitted, tries mis_id.")
    ap.add_argument("--tcol", default=None, help="Time column (e.g., global_t). If omitted, tries global_t.")
    ap.add_argument("--loncol", default=None, help="Longitude column (default: longitude)")
    ap.add_argument("--latcol", default=None, help="Latitude column (default: latitude)")
    ap.add_argument("--hcol", default=None, help="Height/altitude column in meters (default: height)")
    ap.add_argument("--downsample", type=int, default=1, help="Row downsample before everything else.")
    ap.add_argument("--frame_stride", type=int, default=25, help="Use every Kth sample as an animation frame.")
    ap.add_argument("--max_frames", type=int, default=1500, help="Hard cap on number of frames.")
    ap.add_argument("--trail", action="store_true", help="Enable trail line behind marker.")
    ap.add_argument("--trail_len", type=int, default=100, help="Trail length in frames (after frame_stride).")
    ap.add_argument("--static", action="store_true", help="No animation; just draw trajectories + start/end markers.")
    ap.add_argument("--title", default="3D Trajectories", help="Figure title")
    ap.add_argument("--include_earth", action="store_true", help="Draw an Earth sphere (approx).")
    ap.add_argument("--earth_radius_m", type=float, default=6371000.0, help="Earth radius (m) for sphere reference.")
    return ap.parse_args()


def add_earth_sphere(fig: go.Figure, R: float):
    u = np.linspace(0, 2*np.pi, 80)
    v = np.linspace(0, np.pi, 40)
    x = R * np.outer(np.cos(u), np.sin(v))
    y = R * np.outer(np.sin(u), np.sin(v))
    z = R * np.outer(np.ones_like(u), np.cos(v))
    fig.add_trace(go.Surface(x=x, y=y, z=z, name="Earth", showscale=False, opacity=0.15))


def main():
    args = parse_args()
    inp = Path(args.input)
    out = Path(args.out)

    df = pd.read_csv(inp)

    idcol = args.idcol or ("mis_id" if "mis_id" in df.columns else None)
    if not idcol or idcol not in df.columns:
        df["__id__"] = 0
        idcol = "__id__"

    tcol = args.tcol or ("global_t" if "global_t" in df.columns else None)
    if not tcol or tcol not in df.columns:
        df["__t__"] = np.arange(len(df), dtype=float)
        tcol = "__t__"

    loncol = args.loncol or _pick_col(df, ["longitude", "lon", "lng"], required=True)
    latcol = args.latcol or _pick_col(df, ["latitude", "lat"], required=True)
    hcol = args.hcol or _pick_col(df, ["height", "altitude", "h"], required=True)

    df = df.sort_values([idcol, tcol]).reset_index(drop=True)

    if args.downsample and args.downsample > 1:
        df = df.iloc[::args.downsample].reset_index(drop=True)

    lon = df[loncol].to_numpy(dtype=float)
    lat = df[latcol].to_numpy(dtype=float)
    h = df[hcol].to_numpy(dtype=float)

    df["_lon_deg"] = maybe_rad2deg(lon)
    df["_lat_deg"] = maybe_rad2deg(lat)
    df["_h"] = h

    groups = {}
    for gid, g in df.groupby(idcol):
        try:
            gid_key = int(gid)
        except Exception:
            gid_key = gid
        groups[gid_key] = g.reset_index(drop=True)

    fig = go.Figure()

    if args.include_earth:
        add_earth_sphere(fig, args.earth_radius_m)

    # Base trajectories
    for gid, g in groups.items():
        fig.add_trace(go.Scatter3d(
            x=g["_lon_deg"], y=g["_lat_deg"], z=g["_h"],
            mode="lines", name=f"{vehicle_label(gid)} trajectory"
        ))
        fig.add_trace(go.Scatter3d(
            x=[float(g["_lon_deg"].iloc[0])], y=[float(g["_lat_deg"].iloc[0])], z=[float(g["_h"].iloc[0])],
            mode="markers", showlegend=False, marker=dict(size=4), name=f"{vehicle_label(gid)} start"
        ))
        fig.add_trace(go.Scatter3d(
            x=[float(g["_lon_deg"].iloc[-1])], y=[float(g["_lat_deg"].iloc[-1])], z=[float(g["_h"].iloc[-1])],
            mode="markers", showlegend=False, marker=dict(size=4), name=f"{vehicle_label(gid)} terminal"
        ))

    if args.static:
        fig.update_layout(
            title=args.title,
            scene=dict(
                xaxis_title="Longitude (deg)",
                yaxis_title="Latitude (deg)",
                zaxis_title="Altitude (m)",
            ),
            legend=dict(itemsizing="constant"),
        )
        fig.write_html(str(out), include_plotlyjs="cdn", validate=False)
        print(f"[OK] wrote static html: {out}")
        return

    # Animated layer: per vehicle trail + marker
    vehicle_keys = list(groups.keys())
    anim_trace_indices = []

    for gid in vehicle_keys:
        if args.trail:
            fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode="lines", name=f"{vehicle_label(gid)} trail"))
            anim_trace_indices.append(len(fig.data) - 1)

        g = groups[gid]
        fig.add_trace(go.Scatter3d(
            x=[float(g["_lon_deg"].iloc[0])],
            y=[float(g["_lat_deg"].iloc[0])],
            z=[float(g["_h"].iloc[0])],
            mode="markers",
            showlegend=False,
            marker=dict(size=6),
            name=f"{vehicle_label(gid)} current state"
        ))
        anim_trace_indices.append(len(fig.data) - 1)

    # Build frames
    max_len = max(len(groups[gid]) for gid in vehicle_keys)
    stride = max(1, int(args.frame_stride))
    frame_idx = list(range(0, max_len, stride))

    if len(frame_idx) > args.max_frames:
        step = int(np.ceil(len(frame_idx) / args.max_frames))
        frame_idx = frame_idx[::max(1, step)]

    frames = []
    for fi in frame_idx:
        frame_data = []
        for gid in vehicle_keys:
            g = groups[gid]
            i = min(fi, len(g) - 1)

            if args.trail:
                back = args.trail_len * stride
                j0 = max(0, i - back)
                frame_data.append(go.Scatter3d(
                    x=g["_lon_deg"].iloc[j0:i+1].to_list(),
                    y=g["_lat_deg"].iloc[j0:i+1].to_list(),
                    z=g["_h"].iloc[j0:i+1].to_list(),
                    mode="lines"
                ))
            frame_data.append(go.Scatter3d(
                x=[float(g["_lon_deg"].iloc[i])],
                y=[float(g["_lat_deg"].iloc[i])],
                z=[float(g["_h"].iloc[i])],
                mode="markers"
            ))

        fr = go.Frame(data=frame_data, name=str(fi))
        fr.traces = anim_trace_indices
        frames.append(fr)

    fig.frames = frames

    fig.update_layout(
        title=args.title,
        scene=dict(
            xaxis_title="Longitude (deg)",
            yaxis_title="Latitude (deg)",
            zaxis_title="Altitude (m)",
        ),
        legend=dict(itemsizing="constant"),
        updatemenus=[dict(
            type="buttons",
            showactive=False,
            buttons=[
                dict(label="Play", method="animate",
                     args=[None, {"frame": {"duration": 30, "redraw": True}, "fromcurrent": True}]),
                dict(label="Pause", method="animate",
                     args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]),
            ],
        )],
        sliders=[dict(
            steps=[dict(method="animate",
                        args=[[f.name], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}}],
                        label=f.name) for f in frames],
            currentvalue={"prefix": "frame idx: "},
        )],
    )

    fig.write_html(str(out), include_plotlyjs="cdn", validate=False)
    print(f"[OK] wrote animated html: {out}")
    print(f"[INFO] frames={len(frames)} downsample={args.downsample} frame_stride={args.frame_stride} max_frames={args.max_frames} trail={args.trail}")


if __name__ == "__main__":
    main()