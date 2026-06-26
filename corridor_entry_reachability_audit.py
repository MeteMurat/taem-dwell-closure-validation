
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Corridor-entry sonrası reachability analizi.

Amaç:
- Corridor giriş anını bulmak
- Girişten sonraki pencerede state/box yakınlaşmasını özetlemek
- Basit yerel lineer modellerle alpha/sigma otoritesini ölçmek
- "TAEM'e teknik olarak yaklaşım var mı, yoksa authority yetmiyor mu?" sorusuna veri hazırlamak

Çıktılar:
- corridor_entry_reachability_summary.csv
- corridor_entry_local_models.csv
- corridor_entry_window.csv
- corridor_entry_reachability_notes.md
"""
from __future__ import annotations
import argparse
from pathlib import Path
import math
import numpy as np
import pandas as pd

TAEM_H = 25000.0
TAEM_V = 2000.0
TAEM_SGO = 50000.0

def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)

def _pick_time_col(df: pd.DataFrame) -> str:
    for c in ("t_local", "global_t", "t"):
        if c in df.columns:
            return c
    return "__row__"

def _ensure_time(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    tcol = _pick_time_col(df)
    if tcol == "__row__":
        d = df.copy()
        d[tcol] = np.arange(len(d), dtype=float)
        return d, tcol
    return df, tcol

def _first_true_index(g: pd.DataFrame, col: str):
    if col not in g.columns:
        return None
    vals = g[col]
    if vals.dtype != bool:
        vals = vals.astype(str).str.lower().isin(["true","1","yes","y","t"])
    idx = g.index[vals]
    return idx[0] if len(idx) else None

def _fit_linear(y: np.ndarray, X: np.ndarray, names: list[str]):
    good = np.isfinite(y)
    for j in range(X.shape[1]):
        good &= np.isfinite(X[:, j])
    y = y[good]
    X = X[good]
    if len(y) < max(20, X.shape[1] + 5):
        return None
    X1 = np.column_stack([np.ones(len(y)), X])
    coef, *_ = np.linalg.lstsq(X1, y, rcond=None)
    yhat = X1 @ coef
    ss_res = float(np.sum((y - yhat)**2))
    ss_tot = float(np.sum((y - np.mean(y))**2))
    r2 = 1.0 - ss_res/ss_tot if ss_tot > 1e-12 else np.nan
    out = {"intercept": float(coef[0]), "r2": r2, "n": int(len(y))}
    for n, c in zip(names, coef[1:]):
        out[f"coef_{n}"] = float(c)
    return out

def summarize_one(csv_path: Path, window_s: float, near_box_quantile: float) -> tuple[pd.DataFrame, pd.DataFrame, dict, str]:
    df = pd.read_csv(csv_path, low_memory=False)
    df, tcol = _ensure_time(df)

    if "mis_id" not in df.columns:
        df["mis_id"] = 0

    all_windows = []
    model_rows = []
    summary_rows = []
    notes = []

    for vid, g in df.groupby("mis_id"):
        g = g.sort_values(tcol).reset_index(drop=True).copy()
        t = _safe_num(g[tcol])

        # corridor entry
        entry_idx = None
        if "terminal_supervisor_state" in g.columns:
            m = g["terminal_supervisor_state"].astype(str).eq("corridor_track")
            idx = g.index[m]
            if len(idx):
                entry_idx = int(idx[0])
        if entry_idx is None and "corridor_entry_t" in g.columns:
            ce = _safe_num(g["corridor_entry_t"]).dropna()
            if len(ce):
                t0 = float(ce.iloc[0])
                cand = g.index[t >= t0]
                if len(cand):
                    entry_idx = int(cand[0])

        if entry_idx is None:
            # fallback: first terminal authority active
            if "terminal_authority_active" in g.columns:
                vals = g["terminal_authority_active"]
                if vals.dtype != bool:
                    vals = vals.astype(str).str.lower().isin(["true","1","yes","y","t"])
                idx = g.index[vals]
                if len(idx):
                    entry_idx = int(idx[0])

        if entry_idx is None:
            entry_idx = 0

        entry_t = float(t.iloc[entry_idx])
        g["analysis_dt"] = t - entry_t
        w = g[g["analysis_dt"] >= 0].copy()
        if window_s > 0:
            w = w[w["analysis_dt"] <= window_s].copy()

        # ensure core channels
        for col in ("height","velocity","s_go","delta_psi","attack_angle","bank_angle"):
            if col not in w.columns:
                w[col] = np.nan
        for col in ("corridor_h_err","corridor_v_err","corridor_dsgo_err","box_score","dpsi_dt","dsgo_dt"):
            if col not in w.columns:
                w[col] = np.nan

        # derive if missing
        if w["corridor_h_err"].isna().all() and "corridor_h_ref" in w.columns:
            w["corridor_h_err"] = _safe_num(w["height"]) - _safe_num(w["corridor_h_ref"])
        if w["corridor_v_err"].isna().all() and "corridor_v_ref" in w.columns:
            w["corridor_v_err"] = _safe_num(w["velocity"]) - _safe_num(w["corridor_v_ref"])
        if w["corridor_dsgo_err"].isna().all() and "corridor_dsgo_ref" in w.columns and "dsgo_dt" in w.columns:
            w["corridor_dsgo_err"] = _safe_num(w["dsgo_dt"]) - _safe_num(w["corridor_dsgo_ref"])

        # true TAEM errors
        w["taem_h_err_abs"] = (_safe_num(w["height"]) - TAEM_H).abs()
        w["taem_v_err_abs"] = (_safe_num(w["velocity"]) - TAEM_V).abs()
        w["taem_sgo_err_abs"] = (_safe_num(w["s_go"]) - TAEM_SGO).abs()
        w["taem_joint_score"] = (
            0.35 * np.minimum(w["taem_h_err_abs"] / 2500.0, 1.0) +
            0.35 * np.minimum(w["taem_v_err_abs"] / 130.0, 1.0) +
            0.30 * np.minimum(w["taem_sgo_err_abs"] / 25000.0, 1.0)
        )

        # state markers
        if "terminal_supervisor_state" not in w.columns:
            w["terminal_supervisor_state"] = "unknown"
        if "end_reason" not in w.columns:
            w["end_reason"] = ""

        # best rows
        def _best_idx(col):
            s = _safe_num(w[col])
            return int(s.idxmin()) if np.isfinite(s).any() else None

        idx_h = _best_idx("taem_h_err_abs")
        idx_v = _best_idx("taem_v_err_abs")
        idx_s = _best_idx("taem_sgo_err_abs")
        idx_joint = _best_idx("taem_joint_score")

        entry = w.iloc[0]
        end = w.iloc[-1]

        row = {
            "run_id": csv_path.stem,
            "vehicle_id": vid,
            "entry_t": entry_t,
            "entry_h": float(_safe_num(pd.Series([entry["height"]])).iloc[0]),
            "entry_v": float(_safe_num(pd.Series([entry["velocity"]])).iloc[0]),
            "entry_sgo": float(_safe_num(pd.Series([entry["s_go"]])).iloc[0]),
            "entry_dpsi": float(_safe_num(pd.Series([entry["delta_psi"]])).iloc[0]),
            "entry_state": str(entry.get("terminal_supervisor_state","")),
            "window_end_t": float(_safe_num(pd.Series([end[tcol]])).iloc[0]),
            "window_end_h": float(_safe_num(pd.Series([end["height"]])).iloc[0]),
            "window_end_v": float(_safe_num(pd.Series([end["velocity"]])).iloc[0]),
            "window_end_sgo": float(_safe_num(pd.Series([end["s_go"]])).iloc[0]),
            "window_end_dpsi": float(_safe_num(pd.Series([end["delta_psi"]])).iloc[0]),
            "end_reason": str(end.get("end_reason","")),
            "n_window_rows": int(len(w)),
            "corridor_track_seen": bool(w["terminal_supervisor_state"].astype(str).eq("corridor_track").any()),
            "box_capture_seen": bool(w["terminal_supervisor_state"].astype(str).eq("box_capture").any()),
            "taem_in_box_any": bool(w.get("taem_in_box", pd.Series([False]*len(w))).astype(str).str.lower().isin(["true","1","yes","y","t"]).any()),
            "best_joint_score": float(_safe_num(w["taem_joint_score"]).min()) if len(w) else np.nan,
            "best_box_score": float(_safe_num(w["box_score"]).max()) if len(w) else np.nan,
        }

        for name, idx in [("h", idx_h), ("v", idx_v), ("sgo", idx_s), ("joint", idx_joint)]:
            if idx is None:
                continue
            rr = w.loc[idx]
            row[f"best_{name}_t"] = float(_safe_num(pd.Series([rr[tcol]])).iloc[0])
            row[f"best_{name}_analysis_dt"] = float(_safe_num(pd.Series([rr["analysis_dt"]])).iloc[0])
            row[f"best_{name}_state"] = str(rr.get("terminal_supervisor_state",""))
            row[f"best_{name}_h"] = float(_safe_num(pd.Series([rr["height"]])).iloc[0])
            row[f"best_{name}_v"] = float(_safe_num(pd.Series([rr["velocity"]])).iloc[0])
            row[f"best_{name}_sgo"] = float(_safe_num(pd.Series([rr["s_go"]])).iloc[0])
            row[f"best_{name}_dpsi"] = float(_safe_num(pd.Series([rr["delta_psi"]])).iloc[0])
            if name == "h":
                row["min_abs_taem_h_err"] = float(rr["taem_h_err_abs"])
            elif name == "v":
                row["min_abs_taem_v_err"] = float(rr["taem_v_err_abs"])
            elif name == "sgo":
                row["min_abs_taem_sgo_err"] = float(rr["taem_sgo_err_abs"])

        # local models in near-best-joint subset
        qs = _safe_num(w["taem_joint_score"])
        thr = float(qs.quantile(near_box_quantile)) if np.isfinite(qs).any() else np.nan
        near = w[qs <= thr].copy() if np.isfinite(thr) else w.iloc[0:0].copy()
        if len(near) < 25:
            near = w.copy()

        # model inputs
        X = np.column_stack([
            _safe_num(near["attack_angle"]).to_numpy(),
            _safe_num(near["bank_angle"]).to_numpy(),
            _safe_num(near["height"]).to_numpy(),
            _safe_num(near["velocity"]).to_numpy(),
            _safe_num(near["s_go"]).to_numpy(),
            _safe_num(near["delta_psi"]).to_numpy(),
        ])
        names = ["alpha","sigma","h","v","s_go","delta_psi"]

        for target in ["dpsi_dt","dsgo_dt","corridor_h_err","corridor_v_err"]:
            y = _safe_num(near[target]).to_numpy()
            mdl = _fit_linear(y, X, names)
            if mdl is None:
                continue
            mdl["run_id"] = csv_path.stem
            mdl["vehicle_id"] = vid
            mdl["target"] = target
            mdl["subset"] = "near_best_joint"
            mdl["subset_n"] = int(len(near))
            mdl["joint_thr"] = thr
            model_rows.append(mdl)

        all_windows.append(w.assign(run_id=csv_path.stem, vehicle_id=vid))
        summary_rows.append(row)

        notes.append(
            f"- vehicle {vid}: entry at t={entry_t:.1f}s, h={row['entry_h']:.1f} m, v={row['entry_v']:.1f} m/s, "
            f"s_go={row['entry_sgo']:.1f} m, dpsi={row['entry_dpsi']:.3f} rad; "
            f"best joint score={row['best_joint_score']:.4f}, best box_score={row['best_box_score']:.4f}, "
            f"end_reason={row['end_reason']}"
        )

    window_df = pd.concat(all_windows, ignore_index=True) if all_windows else pd.DataFrame()
    models_df = pd.DataFrame(model_rows)
    summary_df = pd.DataFrame(summary_rows)

    note_text = "\n".join([
        "# Corridor-entry reachability notes",
        "",
        f"Input run: {csv_path.name}",
        "",
        "## Summary",
        *notes,
        "",
        "## Reading hints",
        "- `best_joint_score` küçüldükçe eşzamanlı TAEM yakınlığı iyileşir.",
        "- `corridor_track_seen=False` ise regulator corridor'a hiç yerleşememiştir.",
        "- `box_capture_seen=False` ise terminal box safhası hiç başlamamıştır.",
        "- Local models içinde `coef_sigma` ve `coef_alpha` işaretleri, corridor sonrası hangi kontrol kanalının baskın olduğunu gösterir.",
    ])
    return summary_df, models_df, {"note_text": note_text}, window_df

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, help="Input CSV(s)")
    ap.add_argument("--outdir", required=True, help="Output folder")
    ap.add_argument("--window_s", type=float, default=500.0, help="Seconds after corridor entry to analyze; <=0 means full remainder")
    ap.add_argument("--near_box_quantile", type=float, default=0.25, help="Quantile for near-best-joint subset local model")
    return ap.parse_args()

def main():
    args = parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sum_frames = []
    model_frames = []
    win_frames = []
    notes_blocks = []

    for inp in args.inputs:
        p = Path(inp)
        if not p.exists():
            notes_blocks.append(f"# Missing input\n\n- {p}")
            continue
        sdf, mdf, meta, wdf = summarize_one(p, args.window_s, args.near_box_quantile)
        if len(sdf): sum_frames.append(sdf)
        if len(mdf): model_frames.append(mdf)
        if len(wdf): win_frames.append(wdf)
        notes_blocks.append(meta["note_text"])

    summary = pd.concat(sum_frames, ignore_index=True) if sum_frames else pd.DataFrame()
    models = pd.concat(model_frames, ignore_index=True) if model_frames else pd.DataFrame()
    windows = pd.concat(win_frames, ignore_index=True) if win_frames else pd.DataFrame()

    summary.to_csv(outdir / "corridor_entry_reachability_summary.csv", index=False)
    models.to_csv(outdir / "corridor_entry_reachability_local_models.csv", index=False)
    windows.to_csv(outdir / "corridor_entry_reachability_window.csv", index=False)

    (outdir / "corridor_entry_reachability_notes.md").write_text(
        "\n\n".join(notes_blocks) if notes_blocks else "# Corridor-entry reachability notes\n\nNo readable inputs.",
        encoding="utf-8"
    )

    print("[OK] Wrote:")
    print(f"  - {outdir / 'corridor_entry_reachability_summary.csv'}")
    print(f"  - {outdir / 'corridor_entry_reachability_local_models.csv'}")
    print(f"  - {outdir / 'corridor_entry_reachability_window.csv'}")
    print(f"  - {outdir / 'corridor_entry_reachability_notes.md'}")

if __name__ == "__main__":
    main()
