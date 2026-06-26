# -*- coding: utf-8 -*-
"""
collect_threshold_sensitivity_results.py

Collect multiple taem_threshold_sensitivity_summary.csv files into one compact
threshold-sensitivity table.

Example PowerShell usage:
python .\collect_threshold_sensitivity_results.py --inputs `
  .\store\data_saved\v8_2_post_sgo30\taem_threshold_sensitivity_summary.csv `
  .\store\data_saved\v8_2_post_sgo20\taem_threshold_sensitivity_summary.csv `
  .\store\data_saved\v8_2_post_h2000\taem_threshold_sensitivity_summary.csv `
  .\store\data_saved\v8_2_post_h3000\taem_threshold_sensitivity_summary.csv `
  .\store\data_saved\v8_2_post_v100\taem_threshold_sensitivity_summary.csv `
  .\store\data_saved\v8_2_post_v150\taem_threshold_sensitivity_summary.csv `
  --out .\store\data_saved\v8_2_threshold_sensitivity_table.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def _safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except FileNotFoundError:
        print(f"[WARN] Missing file skipped: {path}")
        return pd.DataFrame()
    except Exception as exc:
        print(f"[WARN] Could not read {path}: {exc}")
        return pd.DataFrame()


def _safe_bool(x) -> bool:
    if pd.isna(x):
        return False
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x) > 0.5
    return str(x).strip().lower() in {"1", "true", "yes", "y", "t"}


def _first_existing(row: pd.Series, names: list[str], default=np.nan):
    for name in names:
        if name in row.index:
            return row[name]
    return default


def _classify(tag: str) -> tuple[str, str]:
    t = str(tag).lower()
    if "sgo" in t:
        return "s_go tolerance", t.replace("_post", "")
    if "h" in t and "post" in t:
        return "height tolerance", t.replace("_post", "")
    if "v" in t and "post" in t:
        return "velocity tolerance", t.replace("_post", "")
    return "other", str(tag)


def collect(inputs: list[str]) -> pd.DataFrame:
    rows = []
    for inp in inputs:
        p = Path(inp)
        df = _safe_read_csv(p)
        if df.empty:
            continue
        # Most summary files have one row, but keep all if there are more.
        for _, r in df.iterrows():
            tag = str(_first_existing(r, ["tag", "run_id", "case", "name"], p.parent.name))
            group, setting = _classify(tag)
            strict_reached = _safe_bool(_first_existing(r, ["strict_reached", "taem_reached", "reached"], False))
            out = {
                "source_file": str(p),
                "tag": tag,
                "group": group,
                "setting": setting,
                "strict_reached": strict_reached,
                "strict_first_in_box_t": _first_existing(r, ["strict_first_in_box_t", "first_in_box_t"], np.nan),
                "strict_first_reached_t": _first_existing(r, ["strict_first_reached_t", "first_reached_t"], np.nan),
                "strict_dwell_count_max": _first_existing(r, ["strict_dwell_count_max", "dwell_count_max"], np.nan),
                "strict_dwell_s_max": _first_existing(r, ["strict_dwell_s_max", "dwell_s_max"], np.nan),
                "n_strict_in_box_samples": _first_existing(r, ["n_strict_in_box_samples", "n_in_box_samples"], np.nan),
                "final_h_err_m": _first_existing(r, ["final_h_err", "taem_h_err", "h_err_final"], np.nan),
                "final_v_err_mps": _first_existing(r, ["final_v_err", "taem_v_err", "v_err_final"], np.nan),
                "final_sgo_err_m": _first_existing(r, ["final_sgo_err", "taem_s_go_err", "sgo_err_final"], np.nan),
                "min_abs_h_err_m": _first_existing(r, ["min_abs_h_err", "min_abs_taem_h_err"], np.nan),
                "min_abs_v_err_mps": _first_existing(r, ["min_abs_v_err", "min_abs_taem_v_err"], np.nan),
                "min_abs_sgo_err_m": _first_existing(r, ["min_abs_sgo_err", "min_abs_taem_s_go_err"], np.nan),
            }
            rows.append(out)
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    # Useful deterministic ordering.
    group_order = {"s_go tolerance": 0, "height tolerance": 1, "velocity tolerance": 2, "other": 9}
    result["_group_order"] = result["group"].map(group_order).fillna(9)
    result = result.sort_values(["_group_order", "tag"]).drop(columns=["_group_order"]).reset_index(drop=True)
    return result


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, help="Input taem_threshold_sensitivity_summary.csv files")
    ap.add_argument("--out", required=True, help="Output combined CSV path")
    return ap.parse_args()


def main():
    args = parse_args()
    table = collect(args.inputs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if table.empty:
        print("[ERR] No valid input rows were collected.")
        sys.exit(2)
    table.to_csv(out, index=False)
    print(f"[OK] Wrote: {out}")
    print(table[["tag", "group", "strict_reached", "strict_dwell_count_max", "strict_dwell_s_max"]].to_string(index=False))


if __name__ == "__main__":
    main()
