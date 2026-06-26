# -*- coding: utf-8 -*-
"""
Collect perturbation run summaries for V8.2 mis1 TAEM success campaign.

Usage example (PowerShell):
python .\collect_perturbation_results.py --inputs `
  .\store\data_saved\mis1_state_first_v8_2_final_success_flags.csv `
  .\store\data_saved\mis1_state_first_v8_2_pert_heading_p1deg.csv `
  --out .\store\data_saved\v8_2_perturbation_summary.csv
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def _safe_num(x: Any, default: float = np.nan) -> float:
    try:
        if x is None:
            return float(default)
        if isinstance(x, str) and x.strip() == "":
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def _bool_val(x: Any) -> bool:
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, float, np.integer, np.floating)):
        try:
            return float(x) > 0.5
        except Exception:
            return False
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "t"}


def _find_col(df: pd.DataFrame, names: List[str]) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for name in names:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _pick_time_col(df: pd.DataFrame) -> str | None:
    return _find_col(df, ["t_local", "t", "global_t", "time"])


def _last_relevant_row(df: pd.DataFrame) -> pd.Series:
    """Prefer first end_guide row if available; otherwise last row."""
    if "end_guide" in df.columns:
        mask = df["end_guide"].map(_bool_val)
        if mask.any():
            return df.loc[mask].iloc[-1]
    return df.iloc[-1]


def _parse_run_label(path: Path) -> Dict[str, Any]:
    stem = path.stem
    out: Dict[str, Any] = {
        "run_id": stem,
        "perturb_type": "baseline",
        "perturb_value": 0.0,
        "perturb_unit": "",
    }

    # Patterns used in generated filenames.
    patterns = [
        (r"heading_([pm])(\d+(?:\.\d+)?)deg", "heading", "deg"),
        (r"velocity_([pm])(\d+(?:\.\d+)?)", "velocity", "m/s"),
        (r"height_([pm])(\d+(?:\.\d+)?)", "height", "m"),
    ]
    for pat, typ, unit in patterns:
        m = re.search(pat, stem, flags=re.IGNORECASE)
        if m:
            sign = 1.0 if m.group(1).lower() == "p" else -1.0
            out["perturb_type"] = typ
            out["perturb_value"] = sign * float(m.group(2))
            out["perturb_unit"] = unit
            break
    return out


def summarize_one(path: Path) -> Dict[str, Any]:
    df = pd.read_csv(path, low_memory=False)
    if len(df) == 0:
        raise ValueError(f"Empty CSV: {path}")

    row = _last_relevant_row(df)
    meta = _parse_run_label(path)
    tcol = _pick_time_col(df)

    # Pull explicit perturbation columns when present, overriding filename parse.
    explicit_specs = [
        ("perturb_heading_deg", "heading", "deg"),
        ("perturb_velocity_mps", "velocity", "m/s"),
        ("perturb_height_m", "height", "m"),
    ]
    for col, typ, unit in explicit_specs:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) and abs(float(vals.iloc[-1])) > 1e-12:
                meta["perturb_type"] = typ
                meta["perturb_value"] = float(vals.iloc[-1])
                meta["perturb_unit"] = unit
                break

    def val(*names: str, default: float = np.nan) -> float:
        col = _find_col(df, list(names))
        return _safe_num(row[col], default) if col is not None else float(default)

    def bval(*names: str) -> bool:
        col = _find_col(df, list(names))
        return _bool_val(row[col]) if col is not None else False

    # Dwell max across file, not only final row.
    dwell_col = _find_col(df, ["taem_dwell_s", "taem_dwell_time_s"])
    dwell_count_col = _find_col(df, ["taem_dwell_count"])
    dwell_max = float(pd.to_numeric(df[dwell_col], errors="coerce").max()) if dwell_col else np.nan
    dwell_count_max = float(pd.to_numeric(df[dwell_count_col], errors="coerce").max()) if dwell_count_col else np.nan

    # Minimum absolute errors over run.
    def min_abs(*names: str) -> float:
        col = _find_col(df, list(names))
        if col is None:
            return np.nan
        s = pd.to_numeric(df[col], errors="coerce").abs().dropna()
        return float(s.min()) if len(s) else np.nan

    out: Dict[str, Any] = {
        **meta,
        "csv": str(path),
        "vehicle_id": row.get("mis_id", row.get("vehicle_id", 1)),
        "t_end": val("t_local", "t", "global_t"),
        "time_col": tcol or "",
        "height_end_m": val("height"),
        "velocity_end_mps": val("velocity"),
        "s_go_end_m": val("s_go"),
        "delta_psi_end_rad": val("delta_psi", "taem_psi_err"),
        "taem_h_err_end_m": val("taem_h_err", "taem_err_h"),
        "taem_v_err_end_mps": val("taem_v_err", "taem_err_v"),
        "taem_s_go_err_end_m": val("taem_s_go_err", "taem_err_sgo"),
        "taem_in_box_final": bval("taem_in_box"),
        "taem_reached_final": bval("taem_reached"),
        "taem_reached_event_final": bval("taem_reached_event"),
        "taem_reached_ever_final": bval("taem_reached_ever"),
        "taem_success_latched_final": bval("taem_success_latched"),
        "close_pass_escape_final": bval("close_pass_escape"),
        "end_guide_final": bval("end_guide"),
        "end_reason": str(row.get("end_reason", "")),
        "taem_dwell_s_final": val("taem_dwell_s", "taem_dwell_time_s"),
        "taem_dwell_count_final": val("taem_dwell_count"),
        "taem_dwell_s_max": dwell_max,
        "taem_dwell_count_max": dwell_count_max,
        "min_abs_taem_h_err_m": min_abs("taem_h_err", "taem_err_h"),
        "min_abs_taem_v_err_mps": min_abs("taem_v_err", "taem_err_v"),
        "min_abs_taem_s_go_err_m": min_abs("taem_s_go_err", "taem_err_sgo"),
    }

    # Unified pass flag useful for summary tables.
    out["success"] = bool(
        out["taem_reached_final"]
        or out["taem_reached_ever_final"]
        or out["taem_success_latched_final"]
        or str(out["end_reason"]) == "taem_dwell_reached"
    )
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, help="CSV files to summarize")
    ap.add_argument("--out", required=True, help="Output summary CSV")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    for pstr in args.inputs:
        p = Path(pstr)
        if not p.exists():
            missing.append(str(p))
            continue
        try:
            rows.append(summarize_one(p))
        except Exception as exc:
            rows.append({"run_id": p.stem, "csv": str(p), "error": repr(exc), "success": False})

    if not rows:
        raise SystemExit("[ERR] No valid input CSV files were found.")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)

    # Friendly ordering.
    order_cols = ["perturb_type", "perturb_value", "run_id"]
    existing = [c for c in order_cols if c in df.columns]
    if existing:
        df = df.sort_values(existing, kind="stable")
    df.to_csv(out, index=False)

    if missing:
        miss_path = out.with_suffix(".missing.txt")
        miss_path.write_text("\n".join(missing), encoding="utf-8")
        print(f"[WARN] Missing {len(missing)} input(s); wrote {miss_path}")

    n_success = int(df.get("success", pd.Series(dtype=bool)).astype(bool).sum())
    print(f"[OK] Wrote {out}")
    print(f"[OK] Runs: {len(df)} | Success: {n_success} | Failure: {len(df) - n_success}")


if __name__ == "__main__":
    main()
