#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B1 checker for same-target multi-vehicle transfer.

B1 question
-----------
Does mis_id=1 preserve the V8.2 clean-latched TAEM success inside a 3-vehicle
multi-run environment?

This script is post-processing only. It does not modify guidance or dynamics.
It produces:
- phase2_B1_by_vehicle.csv
- phase2_B1_decision.txt
- phase2_B1_decision.json
- optional diagnostic PNG/PDF pages for the monitored vehicle
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


TRUE_STRINGS = {"1", "true", "t", "yes", "y", "on"}
FALSE_STRINGS = {"0", "false", "f", "no", "n", "off", "", "nan", "none"}


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return safe_num(s).fillna(0.0) > 0.5
    out = s.astype(str).str.strip().str.lower().map(lambda x: True if x in TRUE_STRINGS else False)
    return out.fillna(False)


def scalar(v: Any) -> Any:
    if isinstance(v, np.generic):
        return v.item()
    return v


def first_existing(df: pd.DataFrame, names: Iterable[str]) -> Optional[str]:
    for n in names:
        if n in df.columns:
            return n
    return None


def last_nonempty(g: pd.DataFrame, col: str) -> str:
    if col not in g.columns:
        return ""
    vals = g[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""]
    return vals.iloc[-1] if len(vals) else ""


def any_true(df: pd.DataFrame, names: Iterable[str]) -> bool:
    for n in names:
        if n in df.columns and bool(bool_series(df, n).any()):
            return True
    return False


def max_true_time(g: pd.DataFrame, tcol: str, names: Iterable[str]) -> float:
    for n in names:
        if n in g.columns:
            m = bool_series(g, n)
            if bool(m.any()):
                return float(safe_num(g.loc[m, tcol]).iloc[0])
    return math.nan


def dwell_from_in_box(g: pd.DataFrame, tcol: str, in_box_col: str) -> Dict[str, float]:
    t = safe_num(g[tcol]).to_numpy(dtype=float)
    in_box = bool_series(g, in_box_col).to_numpy(dtype=bool)
    if len(t) == 0:
        return {"dwell_total_s_computed": 0.0, "dwell_max_s_computed": 0.0}
    if len(t) == 1:
        dt = np.array([0.0])
    else:
        diffs = np.diff(t)
        med = float(np.nanmedian(diffs)) if np.isfinite(np.nanmedian(diffs)) else float(diffs[-1])
        dt = np.append(diffs, med)
    total = float(np.nansum(dt[in_box]))
    cur = 0.0
    mx = 0.0
    for flag, dti in zip(in_box, dt):
        if flag:
            cur += float(dti)
            mx = max(mx, cur)
        else:
            cur = 0.0
    return {"dwell_total_s_computed": total, "dwell_max_s_computed": mx}


def summarize_vehicle(g: pd.DataFrame, vehicle_id: int, tcol: str, args: argparse.Namespace) -> Dict[str, Any]:
    g = g.sort_values(tcol).reset_index(drop=True)
    row: Dict[str, Any] = {"vehicle_id": int(vehicle_id), "n_rows": int(len(g)), "time_col": tcol}
    row["t_start_s"] = float(safe_num(g[tcol]).iloc[0]) if len(g) else math.nan
    row["t_end_s"] = float(safe_num(g[tcol]).iloc[-1]) if len(g) else math.nan

    # Success flags, intentionally redundant to survive naming differences.
    success_flag_cols = [
        "taem_success_latched", "taem_reached_ever", "taem_reached_event", "taem_reached",
        "taem_in_box",
    ]
    row["any_taem_success_flag"] = any_true(g, success_flag_cols)
    row["first_success_t_s"] = max_true_time(g, tcol, success_flag_cols)

    for c in [
        "taem_success_latched", "taem_reached_ever", "taem_reached_event", "taem_reached",
        "taem_in_box", "end_guide", "close_pass_escape", "close_pass_escape_latched",
    ]:
        if c in g.columns:
            row[f"any_{c}"] = bool(bool_series(g, c).any())
            row[f"last_{c}"] = bool(bool_series(g, c).iloc[-1])

    row["end_reason_last"] = last_nonempty(g, "end_reason")
    row["guide_phase_last"] = last_nonempty(g, "guide_phase")

    # Dwell columns if logged
    for c in ["taem_dwell_s", "taem_dwell_time_s", "taem_dwell_count", "taem_dwell_steps"]:
        if c in g.columns:
            vals = safe_num(g[c])
            row[f"{c}_max_logged"] = float(np.nanmax(vals.to_numpy())) if np.isfinite(vals).any() else math.nan
            row[f"{c}_final_logged"] = float(vals.iloc[-1]) if len(vals) else math.nan

    if "taem_in_box" in g.columns:
        row.update(dwell_from_in_box(g, tcol, "taem_in_box"))

    # Error metrics
    error_aliases = {
        "taem_h_err": ["taem_h_err"],
        "taem_v_err": ["taem_v_err"],
        "taem_s_go_err": ["taem_s_go_err", "taem_sgo_err"],
        "taem_psi_err": ["taem_psi_err"],
        "taem_gamma_err": ["taem_gamma_err"],
    }
    for label, names in error_aliases.items():
        c = first_existing(g, names)
        if c:
            vals = safe_num(g[c])
            row[f"{label}_final"] = float(vals.iloc[-1]) if len(vals) else math.nan
            row[f"{label}_min_abs"] = float(np.nanmin(np.abs(vals.to_numpy()))) if np.isfinite(vals).any() else math.nan

    # Basic terminal/proximity metrics
    for label, names in {
        "height": ["height", "altitude", "h"],
        "velocity": ["velocity", "v"],
        "s_go": ["s_go"],
        "q": ["q", "q_inf"],
        "bank_angle": ["bank_angle"],
        "attack_angle": ["attack_angle"],
    }.items():
        c = first_existing(g, names)
        if c:
            vals = safe_num(g[c])
            row[f"{label}_final"] = float(vals.iloc[-1]) if len(vals) else math.nan
            if np.isfinite(vals).any():
                row[f"{label}_min"] = float(np.nanmin(vals.to_numpy()))
                row[f"{label}_max"] = float(np.nanmax(vals.to_numpy()))

    close_escape = bool(row.get("any_close_pass_escape", False) or row.get("any_close_pass_escape_latched", False))
    end_reason = str(row.get("end_reason_last", ""))
    reason_ok = (end_reason == "taem_dwell_reached")
    success = bool(row.get("any_taem_success_flag", False))

    row["b1_soft_pass"] = bool(success and not close_escape)
    row["b1_strict_pass"] = bool(success and reason_ok and not close_escape)

    if row["b1_strict_pass"]:
        row["b1_vehicle_decision"] = "PASS_STRICT"
    elif row["b1_soft_pass"]:
        row["b1_vehicle_decision"] = "PASS_WITH_WARNING_END_REASON_NOT_CONFIRMED"
    else:
        row["b1_vehicle_decision"] = "FAIL"

    return row


def choose_csv(path_arg: Optional[str]) -> Path:
    candidates = []
    if path_arg:
        candidates.append(Path(path_arg))
    candidates.extend([
        Path("store/data_saved/phase2_B1_same_target_multi_mis1_transfer.csv"),
        Path("store/data_saved/multiSimulation_case.csv"),
    ])
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("CSV bulunamadı. Denenen yollar: " + ", ".join(str(p) for p in candidates))


def plot_monitor_vehicle(df: pd.DataFrame, outdir: Path, idcol: str, tcol: str, target_id: int) -> None:
    g = df[df[idcol].astype(int) == int(target_id)].copy()
    if g.empty:
        return
    g = g.sort_values(tcol)
    vars_to_plot = [
        "height", "velocity", "s_go", "delta_psi", "bank_angle", "attack_angle",
        "taem_in_box", "taem_h_err", "taem_v_err", "taem_s_go_err", "taem_sgo_err",
        "taem_dwell_s", "taem_dwell_time_s", "taem_dwell_count", "box_score", "taem_close_score",
    ]
    vars_to_plot = [v for v in vars_to_plot if v in g.columns]
    if not vars_to_plot:
        return

    pdf_path = outdir / f"phase2_B1_mis{target_id}_diagnostics.pdf"
    with PdfPages(pdf_path) as pdf:
        for var in vars_to_plot:
            fig = plt.figure(figsize=(8, 4.8))
            ax = fig.add_subplot(1, 1, 1)
            ax.plot(safe_num(g[tcol]), safe_num(g[var]), label=f"mis_id={target_id}")
            # Mark first TAEM latch/reached if available
            tmark = max_true_time(g, tcol, ["taem_success_latched", "taem_reached_ever", "taem_reached_event", "taem_reached"])
            if np.isfinite(tmark):
                ax.axvline(tmark, linestyle="--", linewidth=1.0, label="first TAEM success flag")
            ax.set_xlabel(tcol)
            ax.set_ylabel(var)
            ax.set_title(f"B1 monitor mis_id={target_id}: {var}")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="best", fontsize=8)
            fig.tight_layout()
            png = outdir / f"phase2_B1_mis{target_id}_{var}_vs_{tcol}.png"
            fig.savefig(png, dpi=180, bbox_inches="tight")
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None, help="Simulation CSV. Default: B1 canonical path, then multiSimulation_case.csv")
    ap.add_argument("--outdir", default="store/data_saved/phase2_B1_report", help="Output report directory")
    ap.add_argument("--idcol", default="mis_id", help="Vehicle id column")
    ap.add_argument("--target-mis-id", type=int, default=1, help="B1 monitored vehicle id")
    ap.add_argument("--tol-h", type=float, default=3000.0, help="TAEM h tolerance for metadata only")
    ap.add_argument("--tol-v", type=float, default=150.0, help="TAEM v tolerance for metadata only")
    ap.add_argument("--tol-sgo", type=float, default=30000.0, help="TAEM s_go tolerance for metadata only")
    args = ap.parse_args()

    csv_path = choose_csv(args.csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    if args.idcol not in df.columns:
        if "mis_id" in df.columns:
            args.idcol = "mis_id"
        else:
            df["mis_id"] = 0
            args.idcol = "mis_id"

    tcol = first_existing(df, ["global_t", "t_local", "t"])
    if not tcol:
        tcol = "__row_index__"
        df[tcol] = np.arange(len(df), dtype=float)

    rows = []
    for vid, g in df.groupby(args.idcol):
        try:
            vid_i = int(vid)
        except Exception:
            continue
        rows.append(summarize_vehicle(g, vid_i, tcol, args))

    by_vehicle = pd.DataFrame(rows).sort_values("vehicle_id")
    by_vehicle_path = outdir / "phase2_B1_by_vehicle.csv"
    by_vehicle.to_csv(by_vehicle_path, index=False)

    target = by_vehicle[by_vehicle["vehicle_id"] == int(args.target_mis_id)]
    if target.empty:
        decision = "FAIL_NO_MIS1_ROWS"
        target_row: Dict[str, Any] = {}
    else:
        target_row = target.iloc[0].to_dict()
        decision = str(target_row.get("b1_vehicle_decision", "FAIL"))

    decision_obj = {
        "case": "PHASE2_B1_SAME_TARGET_MULTI_MIS1_TRANSFER",
        "csv": str(csv_path),
        "outdir": str(outdir),
        "target_mis_id": int(args.target_mis_id),
        "decision": decision,
        "strict_pass": bool(target_row.get("b1_strict_pass", False)) if target_row else False,
        "soft_pass": bool(target_row.get("b1_soft_pass", False)) if target_row else False,
        "tolerances_metadata": {
            "tol_h_m": float(args.tol_h),
            "tol_v_mps": float(args.tol_v),
            "tol_sgo_m": float(args.tol_sgo),
        },
        "target_row": {k: (None if pd.isna(v) else scalar(v)) for k, v in target_row.items()} if target_row else {},
        "interpretation": (
            "B1 PASS: mis1 preserved the V8.2 TAEM success in multi-run. Move to B2."
            if decision == "PASS_STRICT" else
            "B1 SOFT PASS: success flag exists, but final end_reason is missing/different. Inspect final-row logging before B2."
            if decision.startswith("PASS_WITH_WARNING") else
            "B1 FAIL: do not tune mis0/mis2 yet. First compare mis1 final-row flags, route bias, and logging against V8.2 single baseline."
        ),
    }

    (outdir / "phase2_B1_decision.json").write_text(json.dumps(decision_obj, indent=2, ensure_ascii=False), encoding="utf-8")

    txt_lines = [
        "PHASE 2 / B1 — SAME-TARGET MULTI-VEHICLE TRANSFER CHECK",
        "=" * 70,
        f"CSV          : {csv_path}",
        f"Target mis_id: {args.target_mis_id}",
        f"Decision     : {decision}",
        "",
        "B1 strict pass requires:",
        "  - a TAEM success/latch/reached flag for mis1,",
        "  - end_reason_last == 'taem_dwell_reached',",
        "  - no close_pass_escape flag.",
        "",
        "Target-row summary:",
    ]
    for k, v in decision_obj["target_row"].items():
        txt_lines.append(f"  {k}: {v}")
    txt_lines.extend(["", decision_obj["interpretation"], ""])
    (outdir / "phase2_B1_decision.txt").write_text("\n".join(txt_lines), encoding="utf-8")

    plot_monitor_vehicle(df, outdir, args.idcol, tcol, args.target_mis_id)

    print("[OK] B1 by-vehicle report:", by_vehicle_path)
    print("[OK] B1 decision txt:", outdir / "phase2_B1_decision.txt")
    print("[OK] B1 decision json:", outdir / "phase2_B1_decision.json")
    print("[B1_DECISION]", decision)
    print(decision_obj["interpretation"])


if __name__ == "__main__":
    main()
