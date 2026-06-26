#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


CANDIDATE_TIME_COLS = ["global_t", "t_local", "t"]
CANDIDATE_VEHICLE_COLS = ["mis_id", "vehicle_id"]
EARLY_NUMERIC_COLS = [
    "height",
    "velocity",
    "s_go",
    "q",
    "L12D",
    "bank_angle",
    "attack_angle",
    "path_angle",
    "heading_angle",
    "sigma_max",
    "longitude_deg",
    "latitude_deg",
    "delta_psi",
    "taem_h_err",
    "taem_v_err",
    "taem_s_go_err",
    "taem_psi_err",
    "taem_close_score",
    "box_score",
]


def _safe_read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def _load_params(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_vehicle_config(params: dict, vid: int) -> dict:
    out = {
        "vehicle_id": int(vid),
        "is_mis0": int(vid == 0),
        "is_mis1": int(vid == 1),
        "is_mis2": int(vid == 2),
    }
    for k, v in params.items():
        if isinstance(v, (int, float, bool, str)):
            out[f"cfg_{k}"] = v
    prefixes = {0: "mis0_", 1: "mis1_", 2: "mis2_"}
    pfx = prefixes.get(int(vid), f"mis{vid}_")
    for k, v in params.items():
        if str(k).startswith(pfx):
            out[f"own_{str(k)[len(pfx):]}"] = v
    return out


def _pick_first_existing(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _safe_stat(series: pd.Series, fn, default=np.nan):
    s = _to_numeric(series)
    s = s[np.isfinite(s)]
    if len(s) == 0:
        return default
    return float(fn(s))


def _compute_window_features(dfv: pd.DataFrame, time_col: str, early_frac: float, min_rows: int) -> dict:
    out: dict[str, float | int] = {}
    if dfv.empty:
        return out

    d = dfv.copy()
    d[time_col] = _to_numeric(d[time_col])
    d = d[np.isfinite(d[time_col])].sort_values(time_col).drop_duplicates(subset=[time_col], keep="last")
    if d.empty:
        return out

    t0 = float(d[time_col].iloc[0])
    t1 = float(d[time_col].iloc[-1])
    dt_total = max(t1 - t0, 0.0)
    early_t_end = t0 + early_frac * dt_total
    early = d[d[time_col] <= early_t_end].copy()

    if len(early) < min_rows:
        n_fallback = min(max(min_rows, 1), len(d))
        early = d.head(n_fallback).copy()

    if early.empty:
        return out

    out["early_t0"] = t0
    out["early_t1"] = float(early[time_col].iloc[-1])
    out["early_t_total"] = t1
    out["early_dt"] = max(float(early[time_col].iloc[-1] - early[time_col].iloc[0]), 0.0)
    out["early_frac_used"] = early_frac
    out["early_n_rows"] = int(len(early))
    out["total_n_rows"] = int(len(d))
    out["early_row_fraction"] = float(len(early) / max(len(d), 1))
    out["early_time_fraction_realized"] = float((float(early[time_col].iloc[-1]) - t0) / dt_total) if dt_total > 0 else 1.0

    for col in EARLY_NUMERIC_COLS:
        if col not in early.columns:
            continue
        s = _to_numeric(early[col])
        mask = np.isfinite(s)
        if mask.sum() == 0:
            continue
        s = s[mask]
        t = _to_numeric(early.loc[mask, time_col])
        start = float(s.iloc[0])
        end = float(s.iloc[-1])
        mean = float(s.mean())
        std = float(s.std(ddof=0)) if len(s) > 1 else 0.0
        minv = float(s.min())
        maxv = float(s.max())
        abs_mean = float(np.abs(s).mean())
        abs_max = float(np.abs(s).max())
        dt = float(t.iloc[-1] - t.iloc[0]) if len(t) > 1 else 0.0
        slope = float((end - start) / dt) if dt > 0 else 0.0
        out[f"early_{col}_start"] = start
        out[f"early_{col}_end"] = end
        out[f"early_{col}_mean"] = mean
        out[f"early_{col}_std"] = std
        out[f"early_{col}_min"] = minv
        out[f"early_{col}_max"] = maxv
        out[f"early_{col}_abs_mean"] = abs_mean
        out[f"early_{col}_abs_max"] = abs_max
        out[f"early_{col}_slope"] = slope

    # Convenience derived features for key states
    def _maybe(col: str, suffix: str):
        return out.get(f"early_{col}_{suffix}", np.nan)

    for col in ["height", "velocity", "s_go", "q", "bank_angle", "attack_angle", "path_angle", "heading_angle"]:
        start = _maybe(col, "start")
        end = _maybe(col, "end")
        if np.isfinite(start) and np.isfinite(end):
            out[f"early_{col}_delta"] = float(end - start)
            out[f"early_{col}_drop"] = float(start - end)

    return out


def main():
    ap = argparse.ArgumentParser(description="Build early-phase-only TAEM ML dataset from sweep run folders.")
    ap.add_argument("--runs-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--early-frac", type=float, default=0.30, help="Fraction of each vehicle time history used as early phase.")
    ap.add_argument("--min-rows", type=int, default=20, help="Minimum early rows per vehicle.")
    args = ap.parse_args()

    rows = []
    run_dirs = sorted([p for p in args.runs_root.iterdir() if p.is_dir()])
    for run_dir in run_dirs:
        params_path = run_dir / "run_params.json"
        q1_path = run_dir / "q1_vehicle_metrics.csv"
        failure_path = run_dir / "q1_failure_modes.csv"
        raw_path = run_dir / "multiSimulation_case.csv"
        taem_path = run_dir / "taem_compare_by_vehicle.csv"
        if not all(p.exists() for p in [params_path, q1_path, failure_path, raw_path]):
            continue

        params = _load_params(params_path)
        q1 = _safe_read_csv(q1_path).rename(columns={
            "t_end": "q1_t_end",
            "q_max": "q1_q_max",
            "end_reason": "q1_end_reason",
            "guide_phase_last": "q1_guide_phase_last",
        })
        failure = _safe_read_csv(failure_path).rename(columns={
            "end_reason": "failure_end_reason",
            "guide_phase_last": "failure_guide_phase_last",
        })
        raw = _safe_read_csv(raw_path)
        taem = _safe_read_csv(taem_path) if taem_path.exists() else pd.DataFrame()

        vehicle_col = _pick_first_existing(raw, CANDIDATE_VEHICLE_COLS)
        time_col = _pick_first_existing(raw, CANDIDATE_TIME_COLS)
        if vehicle_col is None or time_col is None:
            continue

        merged = q1.merge(failure[["vehicle_id", "failure_mode"]], on="vehicle_id", how="left")
        if not taem.empty and "vehicle_id" in taem.columns:
            merged = merged.merge(
                taem[[c for c in [
                    "vehicle_id", "taem_h_err_last", "taem_h_err_minabs", "taem_v_err_last", "taem_v_err_minabs",
                    "taem_s_go_err_last", "taem_s_go_err_minabs", "taem_psi_err_last", "taem_psi_err_minabs",
                    "taem_dwell_s", "taem_dwell_max_s", "height_last", "velocity_last", "s_go_last", "end_reason_last"
                ] if c in taem.columns]],
                on="vehicle_id",
                how="left",
            )

        for _, row in merged.iterrows():
            vid = int(row["vehicle_id"])
            dfv = raw[raw[vehicle_col] == vid].copy()
            early_features = _compute_window_features(dfv, time_col=time_col, early_frac=float(args.early_frac), min_rows=int(args.min_rows))
            if not early_features:
                continue

            rec = {
                "run_name": params.get("run_name", run_dir.name),
                "group_run_name": params.get("run_name", run_dir.name),
                "early_source_time_col": time_col,
            }
            rec.update(_extract_vehicle_config(params, vid))
            rec.update(early_features)

            # canonical target / labels
            rec["taem_lb_score"] = row.get("taem_lb_score", np.nan)
            rec["taem_end_score"] = row.get("taem_end_score", np.nan)
            rec["taem_reached"] = bool(row.get("taem_reached", False))
            rec["failure_mode"] = row.get("failure_mode", "")
            rec["end_reason"] = row.get("q1_end_reason", row.get("failure_end_reason", row.get("end_reason_last", "")))
            rec["guide_phase_last"] = row.get("q1_guide_phase_last", row.get("failure_guide_phase_last", ""))

            # keep a few target-side diagnostics for later analysis (not used as early features)
            for col in [
                "s_go_last_m", "lon_end_deg", "lat_end_deg", "h_err_minabs_m", "v_err_minabs_mps",
                "s_go_err_minabs_m", "psi_err_minabs_rad", "q1_t_end", "q1_q_max", "dwell_max_s",
                "taem_h_err_last", "taem_h_err_minabs", "taem_v_err_last", "taem_v_err_minabs",
                "taem_s_go_err_last", "taem_s_go_err_minabs", "taem_psi_err_last", "taem_psi_err_minabs",
                "taem_dwell_s", "taem_dwell_max_s", "height_last", "velocity_last", "s_go_last",
            ]:
                rec[col] = row.get(col, np.nan)

            rows.append(rec)

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit("No valid run folders found; early dataset is empty.")

    for c in df.columns:
        if df[c].dtype == bool:
            df[c] = df[c].astype(int)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"[OK] Wrote early-phase ML dataset: {args.out}")
    print(df.head())
    print(f"[INFO] n_rows={len(df)} n_runs={df['run_name'].nunique()} n_cols={len(df.columns)} early_frac={args.early_frac}")


if __name__ == "__main__":
    main()
