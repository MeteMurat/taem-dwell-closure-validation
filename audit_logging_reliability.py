#!/usr/bin/env python3
"""
Audit logging reliability for dwell-confirmed TAEM closure CSV logs.

This script is intentionally independent of the simulator. It reads saved CSV logs,
replays the TAEM in-box and dwell decisions from stored state/error channels, and
checks whether terminal/debug fields such as end_reason are consistent with the
replayed dwell evidence.

Example PowerShell usage from the EntryGuidance-master directory:

    python audit_logging_reliability.py --input "outputs\\B5D\\*.csv" --outdir "outputs\\B5D_audit"

or for one file:

    python audit_logging_reliability.py --input "store\\data_saved\\multiSimulation_case.csv" --outdir "audit_out"
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


DEFAULTS = {
    "h_taem": 25000.0,
    "v_taem": 2000.0,
    "s_taem": 50000.0,
    "eps_h": 3000.0,
    "eps_v": 100.0,
    "eps_s": 20000.0,
    "n_dwell": 3,
    "terminal_reason": "taem_dwell_reached",
}

# Column aliases used by different versions of the project logs.
ALIASES = {
    "vehicle_id": ["mis_id", "vehicle_id", "id", "missile_id"],
    "time": ["global_t", "t", "time", "local_t"],
    "height": ["height", "h", "altitude", "alt_m"],
    "velocity": ["velocity", "v", "vel", "speed"],
    "s_go": ["s_go", "sgo", "range_to_go", "range_to_go_m", "s"],
    "h_err": ["e_h", "eh", "h_err", "height_error", "taem_h_error"],
    "v_err": ["e_v", "ev", "v_err", "velocity_error", "taem_v_error"],
    "s_err": ["e_s", "es", "s_err", "sgo_error", "range_error", "taem_s_error"],
    "in_box": ["in_box", "taem_in_box", "inbox", "is_in_box"],
    "end_guide": ["end_guide", "guide_end", "ended"],
    "guide_process": ["guide_process"],
    "end_reason": ["end_reason", "terminal_reason"],
    "guide_phase": ["guide_phase", "phase"],
    "close_pass": ["close_pass_escape", "close_pass_escape_latched", "close_pass", "escape", "closepass_escape"],
    "success_latch": [
        "taem_success_latched", "success_latch", "taem_latched", "taem_event_latched",
        "taem_reached_ever", "taem_reached_event", "taem_reached", "reached", "taem_success",
    ],
}


def first_col(df: pd.DataFrame, key: str) -> Optional[str]:
    for col in ALIASES[key]:
        if col in df.columns:
            return col
    return None


def bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.fillna(False)
    if np.issubdtype(s.dtype, np.number):
        return s.fillna(0).astype(float) != 0.0
    return s.fillna("").astype(str).str.lower().isin(["1", "true", "t", "yes", "y"])


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def reconstruct_errors(g: pd.DataFrame, args: argparse.Namespace) -> Tuple[pd.Series, pd.Series, pd.Series, List[str]]:
    h_err_col = first_col(g, "h_err")
    v_err_col = first_col(g, "v_err")
    s_err_col = first_col(g, "s_err")
    used: List[str] = []

    if h_err_col and v_err_col and s_err_col:
        used = [h_err_col, v_err_col, s_err_col]
        return to_num(g[h_err_col]), to_num(g[v_err_col]), to_num(g[s_err_col]), used

    h_col = first_col(g, "height")
    v_col = first_col(g, "velocity")
    s_col = first_col(g, "s_go")
    missing = [name for name, col in [("height", h_col), ("velocity", v_col), ("s_go", s_col)] if col is None]
    if missing:
        raise ValueError(f"Cannot reconstruct TAEM errors; missing columns: {missing}")
    used = [h_col, v_col, s_col]  # type: ignore[list-item]
    return (
        to_num(g[h_col]) - float(args.h_taem),  # type: ignore[index]
        to_num(g[v_col]) - float(args.v_taem),  # type: ignore[index]
        to_num(g[s_col]) - float(args.s_taem),  # type: ignore[index]
        used,
    )


def dwell_replay(in_box: Iterable[bool], n_dwell: int) -> Tuple[bool, Optional[int], Optional[int], int]:
    dwell = 0
    max_dwell = 0
    confirm_idx: Optional[int] = None
    entry_idx: Optional[int] = None
    for idx, ok in enumerate(in_box):
        if bool(ok):
            dwell += 1
        else:
            dwell = 0
        max_dwell = max(max_dwell, dwell)
        if dwell >= n_dwell and confirm_idx is None:
            confirm_idx = idx
            entry_idx = idx - n_dwell + 1
    return confirm_idx is not None, entry_idx, confirm_idx, max_dwell


def any_flag(g: pd.DataFrame, key: str) -> Tuple[bool, List[str]]:
    cols = [c for c in ALIASES[key] if c in g.columns]
    if not cols:
        return False, []
    val = False
    for c in cols:
        val = val or bool(bool_series(g[c]).any())
    return val, cols


def audit_one_vehicle(g: pd.DataFrame, file_path: Path, vehicle_id: Any, args: argparse.Namespace) -> Dict[str, Any]:
    time_col = first_col(g, "time")
    end_guide_col = first_col(g, "end_guide")
    end_reason_col = first_col(g, "end_reason")

    schema_ok = True
    schema_errors: List[str] = []
    if time_col is None:
        schema_ok = False
        schema_errors.append("missing time column")
    if end_reason_col is None:
        schema_ok = False
        schema_errors.append("missing end_reason column")
    if end_guide_col is None:
        schema_errors.append("missing end_guide column")

    if time_col is not None:
        g = g.sort_values(time_col).reset_index(drop=True)
        time_values = to_num(g[time_col])
        time_ok = bool(time_values.notna().all() and (time_values.diff().dropna() >= -float(args.time_tol)).all())
    else:
        g = g.reset_index(drop=True)
        time_values = pd.Series([np.nan] * len(g))
        time_ok = False

    try:
        eh, ev, es, error_source_cols = reconstruct_errors(g, args)
        finite_state_ok = bool(np.isfinite(eh).all() and np.isfinite(ev).all() and np.isfinite(es).all())
        in_box = (eh.abs() <= float(args.eps_h)) & (ev.abs() <= float(args.eps_v)) & (es.abs() <= float(args.eps_s))
        replay_dwell, entry_idx, confirm_idx, max_dwell = dwell_replay(in_box.fillna(False).tolist(), int(args.n_dwell))
        replay_error = ""
    except Exception as exc:  # noqa: BLE001
        finite_state_ok = False
        in_box = pd.Series([False] * len(g))
        replay_dwell, entry_idx, confirm_idx, max_dwell = False, None, None, 0
        error_source_cols = []
        replay_error = str(exc)

    final_row = g.iloc[-1] if len(g) else pd.Series(dtype=object)
    end_reason_final = str(final_row.get(end_reason_col, "")) if end_reason_col else ""
    terminal_reason_ok = end_reason_final == args.terminal_reason

    if end_guide_col is not None:
        end_guide_series = bool_series(g[end_guide_col])
        final_row_ok = bool((not end_guide_series.any()) or bool(end_guide_series.iloc[-1]))
        end_guide_any = bool(end_guide_series.any())
        end_guide_final = bool(end_guide_series.iloc[-1])
    else:
        final_row_ok = False
        end_guide_any = False
        end_guide_final = False

    success_flag_any, success_cols = any_flag(g, "success_latch")
    close_pass_any, close_cols = any_flag(g, "close_pass")

    # Consistency logic: terminal reason or success flags cannot appear without replayed dwell.
    reason_consistent = not (terminal_reason_ok and not replay_dwell)
    success_flag_consistent = not (success_flag_any and not replay_dwell)
    close_pass_consistent = not (close_pass_any and terminal_reason_ok)

    logging_audit_pass = all([
        schema_ok,
        time_ok,
        finite_state_ok,
        final_row_ok,
        reason_consistent,
        success_flag_consistent,
        close_pass_consistent,
    ])

    replayed_strict = bool(replay_dwell and terminal_reason_ok and (not close_pass_any) and logging_audit_pass)

    notes = []
    notes.extend(schema_errors)
    if replay_error:
        notes.append(replay_error)
    if not time_ok:
        notes.append("time ordering or finite-time check failed")
    if not final_row_ok:
        notes.append("final-row preservation check failed")
    if not reason_consistent:
        notes.append("end_reason reports terminal success without replayed dwell")
    if not success_flag_consistent:
        notes.append("success/latch flag appears without replayed dwell")
    if not close_pass_consistent:
        notes.append("terminal reason conflicts with close-pass escape flag")

    return {
        "file": str(file_path),
        "vehicle_id": vehicle_id,
        "n_rows": int(len(g)),
        "time_col": time_col or "",
        "error_source_cols": ";".join(error_source_cols),
        "schema_ok": schema_ok,
        "time_ok": time_ok,
        "finite_state_ok": finite_state_ok,
        "end_guide_any": end_guide_any,
        "end_guide_final": end_guide_final,
        "final_row_ok": final_row_ok,
        "end_reason_final": end_reason_final,
        "terminal_reason_ok": terminal_reason_ok,
        "success_flag_any": success_flag_any,
        "success_cols": ";".join(success_cols),
        "close_pass_any": close_pass_any,
        "close_cols": ";".join(close_cols),
        "replayed_dwell": replay_dwell,
        "dwell_entry_idx": entry_idx if entry_idx is not None else "",
        "dwell_confirm_idx": confirm_idx if confirm_idx is not None else "",
        "max_replayed_dwell_count": int(max_dwell),
        "logging_audit_pass": logging_audit_pass,
        "replayed_strict_success": replayed_strict,
        "notes": " | ".join(notes),
    }


def expand_inputs(patterns: List[str]) -> List[Path]:
    paths: List[Path] = []
    for pat in patterns:
        matches = glob.glob(pat, recursive=True)
        if not matches and Path(pat).exists():
            matches = [pat]
        paths.extend(Path(m) for m in matches if Path(m).is_file())
    # stable unique order
    seen = set()
    unique: List[Path] = []
    for p in sorted(paths):
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def audit_files(paths: List[Path], args: argparse.Namespace) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for p in paths:
        df = pd.read_csv(p)
        vehicle_col = first_col(df, "vehicle_id")
        if vehicle_col is None:
            # Treat whole file as one vehicle if no id column exists.
            rows.append(audit_one_vehicle(df, p, "single", args))
        else:
            for vid, g in df.groupby(vehicle_col, dropna=False):
                rows.append(audit_one_vehicle(g.copy(), p, vid, args))
    result = pd.DataFrame(rows)
    summary = {
        "n_files": len(paths),
        "n_vehicle_logs": int(len(result)),
        "logging_audit_pass": int(result["logging_audit_pass"].sum()) if len(result) else 0,
        "logging_audit_fail": int((~result["logging_audit_pass"].astype(bool)).sum()) if len(result) else 0,
        "replayed_strict_success": int(result["replayed_strict_success"].sum()) if len(result) else 0,
        "terminal_reason_ok": int(result["terminal_reason_ok"].sum()) if len(result) else 0,
        "end_reason_without_replayed_dwell": int(((result["terminal_reason_ok"]) & (~result["replayed_dwell"])).sum()) if len(result) else 0,
        "success_flag_without_replayed_dwell": int(((result["success_flag_any"]) & (~result["replayed_dwell"])).sum()) if len(result) else 0,
        "close_pass_conflicts": int(((result["close_pass_any"]) & (result["terminal_reason_ok"])).sum()) if len(result) else 0,
        "parameters": {
            "h_taem": args.h_taem,
            "v_taem": args.v_taem,
            "s_taem": args.s_taem,
            "eps_h": args.eps_h,
            "eps_v": args.eps_v,
            "eps_s": args.eps_s,
            "n_dwell": args.n_dwell,
            "terminal_reason": args.terminal_reason,
        },
    }
    return result, summary


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Audit TAEM logging reliability from saved CSV logs.")
    ap.add_argument("--input", nargs="+", required=True, help="CSV file(s) or glob(s), e.g. outputs/B5D/**/*.csv")
    ap.add_argument("--outdir", default="logging_audit", help="Output directory for audit CSV/JSON.")
    ap.add_argument("--h-taem", type=float, default=DEFAULTS["h_taem"])
    ap.add_argument("--v-taem", type=float, default=DEFAULTS["v_taem"])
    ap.add_argument("--s-taem", type=float, default=DEFAULTS["s_taem"])
    ap.add_argument("--eps-h", type=float, default=DEFAULTS["eps_h"])
    ap.add_argument("--eps-v", type=float, default=DEFAULTS["eps_v"])
    ap.add_argument("--eps-s", type=float, default=DEFAULTS["eps_s"])
    ap.add_argument("--n-dwell", type=int, default=DEFAULTS["n_dwell"])
    ap.add_argument("--terminal-reason", default=DEFAULTS["terminal_reason"])
    ap.add_argument("--time-tol", type=float, default=1e-9, help="Allowed negative time jitter before time ordering fails.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    paths = expand_inputs(args.input)
    if not paths:
        raise SystemExit("No input CSV files found.")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    vehicle_audit, summary = audit_files(paths, args)
    vehicle_csv = outdir / "logging_reliability_vehicle_audit.csv"
    summary_json = outdir / "logging_reliability_summary.json"
    vehicle_audit.to_csv(vehicle_csv, index=False)
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote: {vehicle_csv}")
    print(f"Wrote: {summary_json}")


if __name__ == "__main__":
    main()
