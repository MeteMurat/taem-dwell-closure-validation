#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
audit_u3_envelope_selection.py

Purpose
-------
Post-process archived B5A/B5B/B5D/B5E/B5F CSV logs and audit whether the final
local validation envelope was frozen as a contiguous, stated support rather than
by deleting individual failed samples.

This script does NOT rerun dynamics/guidance. It reconstructs TAEM dwell success
from saved trajectory CSV files and groups the results by validation stage and by
membership in the final U3 envelope.

Typical PowerShell usage
------------------------
python .\audit_u3_envelope_selection.py `
  --root ".\store\data_saved" `
  --outdir ".\outputs\u3_envelope_audit" `
  --h-min 0 --h-max 500 `
  --v-min -10 --v-max 10 `
  --h-taem 25000 --v-taem 2000 --s-taem 50000 `
  --eps-h 3000 --eps-v 100 --eps-s 20000 `
  --n-dwell 3
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STAGE_ORDER = ["B5D", "B5A", "B5B", "B5C", "B5E", "B5F", "B4", "B3", "B2", "B1"]


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first matching column using case-insensitive matching."""
    low = {str(c).lower(): str(c) for c in df.columns}
    for cand in candidates:
        if cand.lower() in low:
            return low[cand.lower()]
    return None


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def bool_series(df: pd.DataFrame, col: str | None) -> pd.Series:
    if col is None or col not in df.columns:
        return pd.Series(False, index=df.index)
    s = df[col]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return safe_num(s).fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def stage_from_path(p: Path) -> str:
    text = str(p).replace("\\", "/").upper()
    for st in STAGE_ORDER:
        if st in text:
            return st
    # common folder names in this project
    if "TIGHT_LOCAL" in text or "LOCAL_ENVELOPE" in text:
        return "B5D"
    return "UNKNOWN"


def parse_pm_number(prefix: str, text: str) -> float | None:
    """
    Parse path tokens encoded as hp64p217, hm12p5, vp6p242, vm0p950.
    prefix must be 'h' or 'v'.
    """
    pat = rf"(?:^|[^A-Za-z0-9]){prefix}([pm])(\d+(?:p\d+)?)"
    m = re.search(pat, text, flags=re.IGNORECASE)
    if not m:
        return None
    sign = 1.0 if m.group(1).lower() == "p" else -1.0
    val = float(m.group(2).replace("p", "."))
    return sign * val


def parse_delta_from_columns(df: pd.DataFrame) -> tuple[float | None, float | None]:
    h_col = pick_col(df, [
        "delta_h0", "dh0", "Delta_h0", "dH0", "h_offset", "height_offset",
        "initial_height_offset", "case_delta_h", "case_h_offset", "hp", "hm"
    ])
    v_col = pick_col(df, [
        "delta_v0", "dv0", "Delta_v0", "dV0", "v_offset", "velocity_offset",
        "initial_velocity_offset", "case_delta_v", "case_v_offset", "vp", "vm"
    ])
    dh = None
    dv = None
    if h_col is not None:
        vals = safe_num(df[h_col]).dropna()
        if len(vals):
            dh = float(vals.iloc[0])
    if v_col is not None:
        vals = safe_num(df[v_col]).dropna()
        if len(vals):
            dv = float(vals.iloc[0])
    return dh, dv


def parse_delta_from_path(p: Path) -> tuple[float | None, float | None]:
    text = str(p).replace("\\", "/")
    return parse_pm_number("h", text), parse_pm_number("v", text)


def case_id_from_path(p: Path, df: pd.DataFrame, id_col: str | None) -> str:
    # If combined file contains multiple vehicles, use the file stem as case id.
    if id_col is not None:
        try:
            nveh = df[id_col].nunique(dropna=True)
            if nveh > 1:
                return p.stem
        except Exception:
            pass
    # Otherwise use the parent folder if meaningful.
    parent = p.parent.name
    return parent if parent else p.stem


def replay_dwell_success(g: pd.DataFrame, args: argparse.Namespace) -> dict[str, Any]:
    h_col = pick_col(g, ["height", "h", "altitude", "alt_m"])
    v_col = pick_col(g, ["velocity", "v", "vel", "speed"])
    s_col = pick_col(g, ["s_go", "sgo", "range_to_go", "range_to_go_m", "s"])

    if h_col is None or v_col is None or s_col is None:
        return {
            "schema_ok": False,
            "replayed_dwell": False,
            "terminal_reason_ok": False,
            "terminal_reason_available": False,
            "success_flag_any": False,
            "success_flag_available": False,
            "close_pass_any": False,
            "strict_success": False,
            "n_rows": int(len(g)),
            "notes": "missing required trajectory columns",
        }

    h = safe_num(g[h_col])
    v = safe_num(g[v_col])
    s = safe_num(g[s_col])

    in_box = (
        (h - float(args.h_taem)).abs().le(float(args.eps_h)) &
        (v - float(args.v_taem)).abs().le(float(args.eps_v)) &
        (s - float(args.s_taem)).abs().le(float(args.eps_s))
    ).fillna(False).to_numpy(dtype=bool)

    dwell = 0
    replayed = False
    first_conf_idx = None
    for idx, ok in enumerate(in_box):
        dwell = dwell + 1 if ok else 0
        if dwell >= int(args.n_dwell):
            replayed = True
            first_conf_idx = idx
            break

    reason_col = pick_col(g, ["end_reason", "terminal_reason"])
    terminal_reason_available = reason_col is not None
    if reason_col is not None:
        reason_values = g[reason_col].astype(str).str.strip()
        terminal_reason_ok = bool((reason_values == str(args.terminal_reason)).any())
    else:
        terminal_reason_ok = False

    success_col = pick_col(g, [
        "taem_success_latched", "success_latch", "taem_latched",
        "taem_event_latched", "taem_reached_ever", "taem_reached_event",
        "taem_reached", "reached", "taem_success"
    ])
    success_flag_available = success_col is not None
    success_flag_any = bool(bool_series(g, success_col).any()) if success_col else False

    close_col = pick_col(g, [
        "close_pass_escape", "close_pass_escape_latched", "close_pass",
        "escape", "closepass_escape"
    ])
    close_pass_any = bool(bool_series(g, close_col).any()) if close_col else False

    if terminal_reason_available:
        strict_success = bool(replayed and terminal_reason_ok and not close_pass_any)
    elif success_flag_available:
        strict_success = bool(replayed and success_flag_any and not close_pass_any)
    else:
        strict_success = bool(replayed and not close_pass_any)

    min_abs_h = float(np.nanmin(np.abs(h - float(args.h_taem)))) if len(h) and np.isfinite(h).any() else math.nan
    min_abs_v = float(np.nanmin(np.abs(v - float(args.v_taem)))) if len(v) and np.isfinite(v).any() else math.nan
    min_abs_s = float(np.nanmin(np.abs(s - float(args.s_taem)))) if len(s) and np.isfinite(s).any() else math.nan

    return {
        "schema_ok": True,
        "replayed_dwell": bool(replayed),
        "terminal_reason_ok": bool(terminal_reason_ok),
        "terminal_reason_available": bool(terminal_reason_available),
        "success_flag_any": bool(success_flag_any),
        "success_flag_available": bool(success_flag_available),
        "close_pass_any": bool(close_pass_any),
        "strict_success": bool(strict_success),
        "n_rows": int(len(g)),
        "first_confirm_index": None if first_conf_idx is None else int(first_conf_idx),
        "min_abs_h_error": min_abs_h,
        "min_abs_v_error": min_abs_v,
        "min_abs_s_error": min_abs_s,
        "notes": "",
    }


def is_probably_trajectory_csv(path: Path, header: str) -> bool:
    text = header.lower()
    required_any = ["height", "altitude", "velocity", "s_go", "sgo", "range_to_go"]
    if not any(x in text for x in required_any):
        return False

    name = path.name.lower()
    skip_names = [
        "summary_by_vehicle", "taem_compare_by_run", "logging_reliability_summary",
        "domain_selection_audit", "closest_approach_report", "u3_envelope_audit",
    ]
    if any(s in name for s in skip_names):
        return False
    return True


def audit_csv(path: Path, args: argparse.Namespace) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            header = f.readline()
        if not is_probably_trajectory_csv(path, header):
            return []
        df = pd.read_csv(path)
    except Exception as exc:
        return [{
            "source_csv": str(path),
            "stage": stage_from_path(path),
            "case_id": path.stem,
            "vehicle_id": "NA",
            "schema_ok": False,
            "strict_success": False,
            "notes": f"read failure: {exc}",
        }]

    id_col = pick_col(df, ["mis_id", "vehicle_id", "id", "missile_id"])
    if id_col is None:
        df["__vehicle_id__"] = 0
        id_col = "__vehicle_id__"

    dh_col, dv_col = parse_delta_from_columns(df)
    dh_path, dv_path = parse_delta_from_path(path)
    delta_h0 = dh_col if dh_col is not None else dh_path
    delta_v0 = dv_col if dv_col is not None else dv_path

    case_id = case_id_from_path(path, df, id_col)
    stage = stage_from_path(path)
    inside_u3 = None
    if delta_h0 is not None and delta_v0 is not None:
        inside_u3 = (
            float(args.h_min) <= float(delta_h0) <= float(args.h_max) and
            float(args.v_min) <= float(delta_v0) <= float(args.v_max)
        )

    rows = []
    for vid, g in df.groupby(id_col, dropna=False):
        res = replay_dwell_success(g.sort_index(), args)
        row = {
            "source_csv": str(path),
            "stage": stage,
            "case_id": case_id,
            "vehicle_id": str(vid),
            "delta_h0_m": delta_h0,
            "delta_v0_mps": delta_v0,
            "inside_u3": inside_u3,
            "combined_source": bool("combined" in path.name.lower()),
            "source_n_rows_total": int(len(df)),
        }
        row.update(res)
        rows.append(row)
    return rows


def summarize(vehicle_df: pd.DataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if vehicle_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {"error": "no auditable CSV rows"}

    d = vehicle_df.copy()
    # Prefer combined/high-row-count files when duplicates exist.
    d["source_rank"] = d["combined_source"].astype(int) * 1000000 + d["source_n_rows_total"].fillna(0).astype(int)
    d = d.sort_values("source_rank").drop_duplicates(
        subset=["stage", "case_id", "vehicle_id"], keep="last"
    ).drop(columns=["source_rank"])

    case_rows = []
    for (stage, case_id), g in d.groupby(["stage", "case_id"]):
        strict_all = bool(g["strict_success"].astype(bool).all())
        replayed_all = bool(g["replayed_dwell"].astype(bool).all()) if "replayed_dwell" in g.columns else False
        any_close = bool(g["close_pass_any"].astype(bool).any()) if "close_pass_any" in g.columns else False
        inside_vals = [x for x in g["inside_u3"].dropna().unique().tolist()] if "inside_u3" in g.columns else []
        inside_u3 = inside_vals[0] if len(inside_vals) == 1 else None
        dh_vals = g["delta_h0_m"].dropna().unique().tolist() if "delta_h0_m" in g.columns else []
        dv_vals = g["delta_v0_mps"].dropna().unique().tolist() if "delta_v0_mps" in g.columns else []
        case_rows.append({
            "stage": stage,
            "case_id": case_id,
            "n_vehicle_logs": int(len(g)),
            "case_strict_success": strict_all,
            "case_replayed_dwell_all": replayed_all,
            "case_any_close_pass": any_close,
            "inside_u3": inside_u3,
            "delta_h0_m": dh_vals[0] if len(dh_vals) == 1 else np.nan,
            "delta_v0_mps": dv_vals[0] if len(dv_vals) == 1 else np.nan,
        })
    case_df = pd.DataFrame(case_rows)

    stage_summary = []
    for stage, g in case_df.groupby("stage"):
        gv = d[d["stage"] == stage]
        stage_summary.append({
            "stage": stage,
            "n_cases": int(len(g)),
            "n_vehicle_logs": int(len(gv)),
            "case_strict_success": int(g["case_strict_success"].sum()),
            "case_strict_rate": float(g["case_strict_success"].mean()) if len(g) else math.nan,
            "vehicle_strict_success": int(gv["strict_success"].sum()),
            "vehicle_strict_rate": float(gv["strict_success"].mean()) if len(gv) else math.nan,
            "parseable_delta_cases": int(g["delta_h0_m"].notna().sum()) if "delta_h0_m" in g.columns else 0,
            "inside_u3_cases": int((g["inside_u3"] == True).sum()) if "inside_u3" in g.columns else 0,
            "outside_u3_cases": int((g["inside_u3"] == False).sum()) if "inside_u3" in g.columns else 0,
        })

    inside_summary = []
    if "inside_u3" in case_df.columns:
        valid_inside = case_df.dropna(subset=["inside_u3"])
        for inside_value, g in valid_inside.groupby("inside_u3"):
            keys = set(zip(g["stage"], g["case_id"]))
            mask = d.apply(lambda r: (r["stage"], r["case_id"]) in keys, axis=1)
            gv = d[mask]
            inside_summary.append({
                "inside_u3": bool(inside_value),
                "n_cases": int(len(g)),
                "case_strict_success": int(g["case_strict_success"].sum()),
                "case_strict_rate": float(g["case_strict_success"].mean()) if len(g) else math.nan,
                "n_vehicle_logs": int(len(gv)),
                "vehicle_strict_success": int(gv["strict_success"].sum()),
                "vehicle_strict_rate": float(gv["strict_success"].mean()) if len(gv) else math.nan,
            })

    final = {
        "u3_definition": {
            "delta_h0_m": [float(args.h_min), float(args.h_max)],
            "delta_v0_mps": [float(args.v_min), float(args.v_max)],
            "note": "Membership is evaluated only when delta metadata can be parsed from CSV columns or path names."
        },
        "stage_summary": stage_summary,
        "inside_outside_summary": inside_summary,
        "deduplicated_vehicle_rows": int(len(d)),
        "deduplicated_case_rows": int(len(case_df)),
        "audit_interpretation": {
            "not_dynamics_rerun": True,
            "purpose": "post-process archived logs to document that final U3 evidence is a frozen finite sampled support, not global U4 universality"
        }
    }
    return d, case_df, final


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="store/data_saved", help="Root folder containing archived CSV logs.")
    ap.add_argument("--outdir", required=True, help="Output directory.")
    ap.add_argument("--h-min", type=float, default=0.0)
    ap.add_argument("--h-max", type=float, default=500.0)
    ap.add_argument("--v-min", type=float, default=-10.0)
    ap.add_argument("--v-max", type=float, default=10.0)
    ap.add_argument("--h-taem", type=float, default=25000.0)
    ap.add_argument("--v-taem", type=float, default=2000.0)
    ap.add_argument("--s-taem", type=float, default=50000.0)
    ap.add_argument("--eps-h", type=float, default=3000.0)
    ap.add_argument("--eps-v", type=float, default=100.0)
    ap.add_argument("--eps-s", type=float, default=20000.0)
    ap.add_argument("--n-dwell", type=int, default=3)
    ap.add_argument("--terminal-reason", default="taem_dwell_reached")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not root.exists():
        raise SystemExit(f"[ERR] root folder not found: {root}")

    rows: list[dict[str, Any]] = []
    csv_paths = sorted([p for p in root.rglob("*.csv") if p.is_file() and p.stat().st_size > 0])

    for p in csv_paths:
        rows.extend(audit_csv(p, args))

    raw_df = pd.DataFrame(rows)
    raw_path = outdir / "u3_envelope_audit_raw_vehicle_rows.csv"
    raw_df.to_csv(raw_path, index=False)

    dedup_vehicle, case_df, summary = summarize(raw_df, args)
    vehicle_path = outdir / "u3_envelope_audit_vehicle.csv"
    case_path = outdir / "u3_envelope_audit_case.csv"
    summary_path = outdir / "u3_envelope_audit_summary.json"

    dedup_vehicle.to_csv(vehicle_path, index=False)
    case_df.to_csv(case_path, index=False)

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("[OK] U3 envelope-selection audit completed.")
    print(f"[OK] Raw vehicle rows: {raw_path}")
    print(f"[OK] Deduplicated vehicle audit: {vehicle_path}")
    print(f"[OK] Case audit: {case_path}")
    print(f"[OK] Summary JSON: {summary_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
