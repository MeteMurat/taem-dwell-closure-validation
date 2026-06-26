# -*- coding: utf-8 -*-
"""taem_compare_runs.py

Compare multiple simulation runs using TAEM-related CSV columns.

This script is *post-processing only*: it does not run any dynamics or guidance.

Priority order for TAEM detection
--------------------------------
1) Use logged boolean columns if present:
   - taem_in_box
   - taem_reached
2) Else compute from logged error columns if present:
   - taem_h_err, taem_v_err, taem_s_go_err, taem_psi_err
3) Else derive errors from the user's current raw CSV convention:
   - taem_h_err   = height        - HTAEM
   - taem_v_err   = velocity      - VTAEM
   - taem_s_go_err= s_go          - STAEM
   - taem_psi_err = wrap(heading_angle - psiTAEM)

Outputs (in --outdir)
---------------------
- taem_compare_by_vehicle.csv : one row per (run, vehicle)
- taem_compare_by_run.csv     : aggregated metrics per run
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


BOOL_TRUE = {"1", "true", "yes", "y", "t"}


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def _ensure_idcol(df: pd.DataFrame, idcol: str | None) -> tuple[pd.DataFrame, str]:
    if idcol and idcol in df.columns:
        return df, idcol
    if "mis_id" in df.columns:
        return df, "mis_id"
    d = df.copy()
    d["mis_id"] = 0
    return d, "mis_id"


def _good_col(df: pd.DataFrame, name: str) -> pd.Series | None:
    if name not in df.columns:
        return None
    s = _safe_num(df[name])
    return s if s.notna().any() else None


def _ensure_time_axes(df: pd.DataFrame, idcol: str) -> pd.DataFrame:
    out = df.copy()

    base = _good_col(out, "global_t")
    if base is None:
        base = _good_col(out, "t")
    if base is None:
        base = pd.Series(np.arange(len(out), dtype=float), index=out.index)
    out["global_t"] = base

    t_local = _good_col(out, "t_local")
    if t_local is not None:
        out["t_local"] = t_local
    else:
        launch = _good_col(out, "launch_time")
        if launch is not None:
            out["t_local"] = out["global_t"] - launch.fillna(0.0)
        else:
            out["t_local"] = out["global_t"] - out.groupby(idcol)["global_t"].transform("min")

    out["t"] = _safe_num(out["global_t"])
    return out


def _pick_time_col(df: pd.DataFrame) -> str:
    for c in ("global_t", "t_local", "t"):
        if c in df.columns and _safe_num(df[c]).notna().any():
            return c
    return "__row_index__"


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    s = df[col]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return _safe_num(s).fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(BOOL_TRUE)


def _wrap_angle_rad(x: pd.Series | np.ndarray) -> pd.Series:
    arr = np.asarray(x, dtype=float)
    wrapped = (arr + np.pi) % (2.0 * np.pi) - np.pi
    return pd.Series(wrapped, index=getattr(x, "index", None))


def _derive_error_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], str]:
    """Ensure taem_*_err columns exist whenever possible.

    Returns
    -------
    df_out, err_cols, source_label
    """
    out = df.copy()
    sources = []

    # h error
    if "taem_h_err" not in out.columns and {"height", "HTAEM"}.issubset(out.columns):
        out["taem_h_err"] = _safe_num(out["height"]) - _safe_num(out["HTAEM"])
        sources.append("derived_h")
    elif "taem_h_err" in out.columns:
        out["taem_h_err"] = _safe_num(out["taem_h_err"])

    # v error
    if "taem_v_err" not in out.columns and {"velocity", "VTAEM"}.issubset(out.columns):
        out["taem_v_err"] = _safe_num(out["velocity"]) - _safe_num(out["VTAEM"])
        sources.append("derived_v")
    elif "taem_v_err" in out.columns:
        out["taem_v_err"] = _safe_num(out["taem_v_err"])

    # s_go error
    if "taem_s_go_err" not in out.columns and {"s_go", "STAEM"}.issubset(out.columns):
        out["taem_s_go_err"] = _safe_num(out["s_go"]) - _safe_num(out["STAEM"])
        sources.append("derived_sgo")
    elif "taem_s_go_err" in out.columns:
        out["taem_s_go_err"] = _safe_num(out["taem_s_go_err"])

    # psi error (optional)
    if "taem_psi_err" not in out.columns and {"heading_angle", "psiTAEM"}.issubset(out.columns):
        psi = _safe_num(out["heading_angle"])
        psi_ref = _safe_num(out["psiTAEM"])
        out["taem_psi_err"] = _wrap_angle_rad(psi - psi_ref)
        sources.append("derived_psi")
    elif "taem_psi_err" in out.columns:
        out["taem_psi_err"] = _safe_num(out["taem_psi_err"])

    err_cols = [c for c in ("taem_h_err", "taem_v_err", "taem_s_go_err", "taem_psi_err") if c in out.columns]
    source_label = "derived_from_raw" if any(s.startswith("derived_") for s in sources) else ("logged_err_cols" if err_cols else "none")
    return out, err_cols, source_label


def _compute_in_box(
    df: pd.DataFrame,
    tol_h: float | None,
    tol_v: float | None,
    tol_sgo: float | None,
    tol_psi: float | None,
) -> tuple[pd.Series | None, list[str]]:
    checks: list[str] = []
    have_any = any(c in df.columns for c in ("taem_h_err", "taem_v_err", "taem_s_go_err", "taem_psi_err"))
    have_tols = any(x is not None for x in (tol_h, tol_v, tol_sgo, tol_psi))
    if not (have_any and have_tols):
        return None, checks

    in_box = pd.Series([True] * len(df), index=df.index)
    used = False

    if "taem_h_err" in df.columns and tol_h is not None:
        in_box &= (_safe_num(df["taem_h_err"]).abs() <= float(tol_h))
        checks.append(f"|h|<={float(tol_h):g}")
        used = True
    if "taem_v_err" in df.columns and tol_v is not None:
        in_box &= (_safe_num(df["taem_v_err"]).abs() <= float(tol_v))
        checks.append(f"|v|<={float(tol_v):g}")
        used = True
    if "taem_s_go_err" in df.columns and tol_sgo is not None:
        in_box &= (_safe_num(df["taem_s_go_err"]).abs() <= float(tol_sgo))
        checks.append(f"|sgo|<={float(tol_sgo):g}")
        used = True
    if "taem_psi_err" in df.columns and tol_psi is not None:
        in_box &= (_safe_num(df["taem_psi_err"]).abs() <= float(tol_psi))
        checks.append(f"|psi|<={float(tol_psi):g}")
        used = True

    return (in_box if used else None), checks


def _event_time_from_logged(g: pd.DataFrame, tcol: str) -> float | None:
    pref = []
    if tcol == "global_t" and "taem_t_global" in g.columns:
        pref.append("taem_t_global")
    if tcol == "t_local" and "taem_t_local" in g.columns:
        pref.append("taem_t_local")
    pref.extend([c for c in ("taem_t_global", "taem_t_local", "taem_entry_t") if c in g.columns and c not in pref])
    for c in pref:
        vals = _safe_num(g[c]).dropna()
        if len(vals):
            return float(vals.iloc[0])
    return None


def _segment_dwell(t: np.ndarray, in_box: np.ndarray, dwell_min_s: float = 0.0) -> tuple[float, float, float | None, bool]:
    """Return (dwell_total, dwell_max, t_first_reached, reached).

    If dwell_min_s <= 0, any in-box segment counts as reached.
    If dwell_min_s > 0, reached only after a contiguous segment exceeds dwell_min_s.
    """
    t = np.asarray(t, dtype=float)
    in_box = np.asarray(in_box, dtype=bool)
    mask = np.isfinite(t)
    t = t[mask]
    in_box = in_box[mask]
    n = len(t)
    if n == 0:
        return (0.0, 0.0, None, False)

    order = np.argsort(t, kind="mergesort")
    t = t[order]
    in_box = in_box[order]

    dt = np.diff(t)
    dt = np.where(np.isfinite(dt) & (dt > 0.0), dt, 0.0)
    if len(dt) == 0:
        dt = np.array([0.0])
    else:
        finite_dt = dt[np.isfinite(dt) & (dt >= 0.0)]
        last = float(np.nanmedian(finite_dt)) if len(finite_dt) else 0.0
        dt = np.append(dt, last)

    dwell_total = float(np.nansum(dt[in_box]))
    dwell_max = 0.0
    cur = 0.0
    t_first = None
    reached = False
    thr = max(0.0, float(dwell_min_s))

    for i in range(n):
        if in_box[i]:
            cur += float(dt[i])
            dwell_max = max(dwell_max, cur)
            if not reached:
                if thr <= 0.0:
                    reached = True
                    t_first = float(t[i])
                elif cur >= thr:
                    reached = True
                    t_first = float(t[i])
        else:
            cur = 0.0
    return (float(dwell_total), float(dwell_max), t_first, reached)


def _read_many(inputs: list[str], glob_pat: str | None) -> list[Path]:
    paths = [Path(p) for p in inputs]
    if glob_pat:
        paths.extend(sorted(Path().glob(glob_pat)))
    seen = set()
    out = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=[], help="Explicit list of run CSVs")
    ap.add_argument("--glob", default=None, help="Glob pattern for run CSVs")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--idcol", default=None, help="Vehicle id column (default: mis_id if present)")
    ap.add_argument("--run_id", default=None, help="Optional explicit run_id label (only valid if one input)")
    ap.add_argument("--tol_h", type=float, default=None, help="TAEM |h_err| tolerance (meters)")
    ap.add_argument("--tol_v", type=float, default=None, help="TAEM |v_err| tolerance")
    ap.add_argument("--tol_sgo", type=float, default=None, help="TAEM |s_go_err| tolerance (meters)")
    ap.add_argument("--tol_psi", type=float, default=None, help="TAEM |psi_err| tolerance (radians)")
    ap.add_argument("--dwell_min_s", type=float, default=0.0, help="Minimum contiguous in-box dwell required for TAEM reached")
    return ap.parse_args()


def main():
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    run_paths = _read_many(args.inputs, args.glob)
    if not run_paths:
        raise SystemExit("[ERR] No inputs found. Use --inputs or --glob.")

    rows = []
    for p in run_paths:
        df = pd.read_csv(p)
        df, idcol = _ensure_idcol(df, args.idcol)
        df = _ensure_time_axes(df, idcol)
        df, err_cols, err_source = _derive_error_columns(df)
        tcol = _pick_time_col(df)
        if tcol == "__row_index__":
            df[tcol] = np.arange(len(df), dtype=float)

        run_label = args.run_id if (args.run_id and len(run_paths) == 1) else p.stem

        detect_mode = "none"
        checks = []
        if "taem_in_box" in df.columns:
            in_box_ser = _bool_col(df, "taem_in_box")
            detect_mode = "logged_taem_in_box"
        elif "taem_reached" in df.columns:
            in_box_ser = _bool_col(df, "taem_reached")
            detect_mode = "logged_taem_reached"
        else:
            in_box_ser, checks = _compute_in_box(df, args.tol_h, args.tol_v, args.tol_sgo, args.tol_psi)
            if in_box_ser is None:
                in_box_ser = pd.Series([False] * len(df), index=df.index)
                detect_mode = f"no_detection_cols_err_source={err_source}"
            else:
                detect_mode = f"derived_from_errors_err_source={err_source}"

        reached_ser = _bool_col(df, "taem_reached") if "taem_reached" in df.columns else in_box_ser

        for vid, g in df.groupby(idcol):
            g = g.sort_values(tcol)
            t = _safe_num(g[tcol]).to_numpy()
            in_box = in_box_ser.loc[g.index].to_numpy(dtype=bool)
            reached_logged = reached_ser.loc[g.index].to_numpy(dtype=bool)

            dwell_total, dwell_max, t_first_seg, reached_seg = _segment_dwell(t, in_box, dwell_min_s=args.dwell_min_s)
            reached_any = bool(np.any(in_box))
            reached = bool(np.any(reached_logged)) if "taem_reached" in g.columns else bool(reached_seg)
            t_first_logged = _event_time_from_logged(g, tcol)
            t_first = t_first_logged if t_first_logged is not None else (float(t_first_seg) if t_first_seg is not None else np.nan)

            r = {
                "run_id": run_label,
                "csv": str(p),
                "vehicle_id": vid,
                "time_col": tcol,
                "detect_mode": detect_mode,
                "detect_checks": " & ".join(checks),
                "dwell_min_s": float(args.dwell_min_s),
                "t_start": float(np.nanmin(t)) if len(t) and np.isfinite(t).any() else np.nan,
                "t_end": float(np.nanmax(t)) if len(t) and np.isfinite(t).any() else np.nan,
                "taem_reached_any": reached_any,
                "taem_reached": reached,
                "taem_t_first_reached": t_first,
                "taem_dwell_s": float(dwell_total),
                "taem_dwell_max_s": float(dwell_max),
            }

            # Persist last-known error values plus min-abs values for diagnosis.
            for ec in err_cols:
                vals = _safe_num(g[ec]).dropna()
                r[f"{ec}_last"] = float(vals.iloc[-1]) if len(vals) else np.nan
                r[f"{ec}_minabs"] = float(vals.abs().min()) if len(vals) else np.nan

            # Persist last TAEM refs if present.
            for refc in ("HTAEM", "VTAEM", "STAEM", "psiTAEM", "ETAEM", "TTAEM"):
                if refc in g.columns:
                    vals = _safe_num(g[refc]).dropna()
                    r[refc] = float(vals.iloc[-1]) if len(vals) else np.nan

            for diagc in ("height", "velocity", "s_go", "heading_angle", "touchdown", "end_guide", "end_reason", "guide_phase"):
                if diagc in g.columns:
                    if diagc in ("end_reason", "guide_phase"):
                        x = g[diagc].dropna()
                        r[f"{diagc}_last"] = str(x.iloc[-1]) if len(x) else ""
                    elif diagc in ("touchdown", "end_guide"):
                        r[f"{diagc}_any"] = bool(_bool_col(g, diagc).any())
                    else:
                        vals = _safe_num(g[diagc]).dropna()
                        r[f"{diagc}_last"] = float(vals.iloc[-1]) if len(vals) else np.nan

            rows.append(r)

    by_vehicle = pd.DataFrame(rows)
    by_vehicle.to_csv(outdir / "taem_compare_by_vehicle.csv", index=False)

    agg_rows = []
    for run_id, g in by_vehicle.groupby("run_id"):
        n = len(g)
        agg_rows.append({
            "run_id": run_id,
            "n_vehicles": int(n),
            "detect_mode": str(g["detect_mode"].iloc[0]) if n else "",
            "detect_checks": str(g["detect_checks"].iloc[0]) if n else "",
            "dwell_min_s": float(g["dwell_min_s"].iloc[0]) if n else np.nan,
            "reached_any_rate": float(np.mean(g["taem_reached_any"].astype(float))) if n else np.nan,
            "reached_rate": float(np.mean(g["taem_reached"].astype(float))) if n else np.nan,
            "avg_dwell_s": float(np.nanmean(g["taem_dwell_s"].to_numpy())) if n else np.nan,
            "avg_dwell_max_s": float(np.nanmean(g["taem_dwell_max_s"].to_numpy())) if n else np.nan,
            "median_t_first_reached": float(np.nanmedian(g["taem_t_first_reached"].to_numpy())) if n else np.nan,
        })

    by_run = pd.DataFrame(agg_rows).sort_values("run_id")
    by_run.to_csv(outdir / "taem_compare_by_run.csv", index=False)

    print("[OK] Wrote:")
    print(f"  - {outdir / 'taem_compare_by_vehicle.csv'}")
    print(f"  - {outdir / 'taem_compare_by_run.csv'}")


if __name__ == "__main__":
    main()
