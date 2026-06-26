#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze terminal reduced-order datasets.

Inputs:
- terminal_reduced_order_dataset.csv produced by terminal_reduced_order_builder.py

Outputs:
- terminal_control_effectiveness_summary.csv
- terminal_control_effectiveness_local_models.csv
- terminal_control_effectiveness_notes.md

Focus:
- control-effectiveness correlations
- split by terminal_supervisor_state
- simple local linear models around terminal-authority-active samples
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd


STATE_COLS = ["h", "v", "s_go", "delta_psi"]
CONTROL_COLS = ["alpha", "sigma"]
DERIV_COLS = ["dh_dt", "dv_dt", "dsgo_dt", "dpsi_dt"]


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


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


def corr_pair(df: pd.DataFrame, x: str, y: str) -> float:
    d = df[[x, y]].dropna()
    if len(d) < 3:
        return np.nan
    return float(d[x].corr(d[y]))


def ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = 1e-6) -> np.ndarray:
    # beta = (X'X + lam I)^-1 X'y
    p = X.shape[1]
    return np.linalg.solve(X.T @ X + lam * np.eye(p), X.T @ y)


def standardize_fit(df: pd.DataFrame, feature_cols: list[str], target_col: str, lam: float = 1e-4):
    d = df[feature_cols + [target_col]].dropna().copy()
    if len(d) < max(10, len(feature_cols) + 3):
        return None

    X = d[feature_cols].to_numpy(dtype=float)
    y = d[target_col].to_numpy(dtype=float)

    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-12] = 1.0
    Xn = (X - mu) / sd

    # add intercept
    Xd = np.column_stack([np.ones(len(Xn)), Xn])
    beta = ridge_fit(Xd, y, lam=lam)
    yhat = Xd @ beta
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = np.nan if ss_tot <= 0 else float(1.0 - ss_res / ss_tot)

    return {
        "n_samples": int(len(d)),
        "intercept": float(beta[0]),
        "coef_map": {c: float(b) for c, b in zip(feature_cols, beta[1:])},
        "x_mean_map": {c: float(m) for c, m in zip(feature_cols, mu)},
        "x_std_map": {c: float(s) for c, s in zip(feature_cols, sd)},
        "r2": r2,
    }


def summarize_one(csv_path: Path):
    df = pd.read_csv(csv_path, low_memory=False)
    for c in STATE_COLS + CONTROL_COLS + DERIV_COLS:
        if c in df.columns:
            df[c] = _safe_num(df[c])

    run_id = csv_path.stem
    state_col = "terminal_supervisor_state" if "terminal_supervisor_state" in df.columns else None
    active_mask = None
    if "terminal_authority_active" in df.columns:
        a = df["terminal_authority_active"]
        if a.dtype == bool:
            active_mask = a
        else:
            active_mask = a.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])
    else:
        active_mask = pd.Series([True] * len(df), index=df.index)

    # overall correlations
    rows = []
    pairs = [("alpha", "dh_dt"), ("alpha", "dv_dt"), ("alpha", "dsgo_dt"), ("alpha", "dpsi_dt"),
             ("sigma", "dh_dt"), ("sigma", "dv_dt"), ("sigma", "dsgo_dt"), ("sigma", "dpsi_dt")]
    for x, y in pairs:
        if x in df.columns and y in df.columns:
            rows.append({
                "run_id": run_id,
                "slice": "overall",
                "metric": f"corr({x},{y})",
                "value": corr_pair(df, x, y),
            })
            rows.append({
                "run_id": run_id,
                "slice": "authority_active",
                "metric": f"corr({x},{y})",
                "value": corr_pair(df.loc[active_mask], x, y),
            })

    # per supervisor state correlations
    if state_col:
        for st, g in df.groupby(state_col):
            for x, y in pairs:
                if x in g.columns and y in g.columns:
                    rows.append({
                        "run_id": run_id,
                        "slice": f"state:{st}",
                        "metric": f"corr({x},{y})",
                        "value": corr_pair(g, x, y),
                    })

    summary = pd.DataFrame(rows)

    # Local linear models around authority-active and best-box neighborhoods
    local_rows = []
    work = df.loc[active_mask].copy()
    if len(work) == 0:
        work = df.copy()

    # neighborhood around top quartile box_score if available
    if "box_score" in work.columns:
        work["box_score"] = _safe_num(work["box_score"])
        q = work["box_score"].quantile(0.75)
        near_box = work.loc[work["box_score"] >= q].copy()
    else:
        near_box = work.copy()

    model_specs = [
        ("dpsi_dt", ["delta_psi", "sigma", "s_go", "v"]),
        ("dsgo_dt", ["s_go", "sigma", "delta_psi", "v"]),
        ("dh_dt", ["h", "alpha", "v"]),
        ("dv_dt", ["v", "alpha", "h"]),
    ]

    for label, frame in [("authority_active", work), ("near_best_box", near_box)]:
        for target, feats in model_specs:
            feats = [c for c in feats if c in frame.columns]
            if target not in frame.columns or len(feats) == 0:
                continue
            fit = standardize_fit(frame, feats, target)
            if fit is None:
                continue
            row = {
                "run_id": run_id,
                "slice": label,
                "target": target,
                "n_samples": fit["n_samples"],
                "r2": fit["r2"],
                "intercept": fit["intercept"],
            }
            for c in feats:
                row[f"coef_{c}"] = fit["coef_map"][c]
                row[f"xmean_{c}"] = fit["x_mean_map"][c]
                row[f"xstd_{c}"] = fit["x_std_map"][c]
            local_rows.append(row)

    local_models = pd.DataFrame(local_rows)

    # Notes
    notes = []
    notes.append(f"# Control effectiveness notes for {run_id}")
    notes.append("")
    notes.append("## Overall active-region correlations")
    for pair in [("alpha", "dh_dt"), ("alpha", "dv_dt"), ("sigma", "dsgo_dt"), ("sigma", "dpsi_dt")]:
        metric = f"corr({pair[0]},{pair[1]})"
        vals = summary[(summary["slice"] == "authority_active") & (summary["metric"] == metric)]["value"]
        if len(vals):
            notes.append(f"- {metric} = {vals.iloc[0]:.4f}")
    notes.append("")
    notes.append("## Interpretation hints")
    notes.append("- Strong |corr(sigma,dpsi_dt)| means bank is materially steering heading geometry.")
    notes.append("- Strong |corr(sigma,dsgo_dt)| means bank is materially affecting range-rate closure.")
    notes.append("- Strong |corr(alpha,dh_dt)| and |corr(alpha,dv_dt)| means alpha is materially shaping vertical/energy motion.")
    notes.append("- If a local model around near-best-box has poor R^2, the regulator is likely operating in a highly nonlinear or mode-mixed region.")
    notes.append("")
    notes.append("## Recommended next step")
    notes.append("- Use the dpsi_dt and dsgo_dt local models to redesign the bank channel with an explicit heading-priority gate.")
    notes.append("- Use the dh_dt and dv_dt local models to redesign the alpha channel around corridor-tracking rather than fixed TAEM-state capture.")

    return summary, local_models, "\n".join(notes) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=[], help="Explicit list of terminal_reduced_order_dataset.csv files")
    ap.add_argument("--glob", default=None, help="Glob pattern for terminal_reduced_order_dataset.csv files")
    ap.add_argument("--outdir", required=True, help="Output directory")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    run_paths = _read_many(args.inputs, args.glob)
    if not run_paths:
        raise SystemExit("[ERR] No inputs found. Use --inputs or --glob.")

    all_summary = []
    all_models = []
    notes_blobs = []
    for p in run_paths:
        summ, models, notes = summarize_one(p)
        all_summary.append(summ)
        all_models.append(models)
        notes_blobs.append(notes)

    summary = pd.concat(all_summary, ignore_index=True) if all_summary else pd.DataFrame()
    models = pd.concat(all_models, ignore_index=True) if all_models else pd.DataFrame()

    summary.to_csv(outdir / "terminal_control_effectiveness_summary.csv", index=False)
    models.to_csv(outdir / "terminal_control_effectiveness_local_models.csv", index=False)
    (outdir / "terminal_control_effectiveness_notes.md").write_text("\n\n".join(notes_blobs), encoding="utf-8")

    print("[OK] Wrote:")
    print(f"  - {outdir / 'terminal_control_effectiveness_summary.csv'}")
    print(f"  - {outdir / 'terminal_control_effectiveness_local_models.csv'}")
    print(f"  - {outdir / 'terminal_control_effectiveness_notes.md'}")


if __name__ == "__main__":
    main()
