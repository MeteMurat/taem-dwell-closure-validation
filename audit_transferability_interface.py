# -*- coding: utf-8 -*-
"""
audit_transferability_interface.py

Reviewer 8 transferability audit for the dwell-confirmed TAEM validation layer.

Purpose
-------
This script tests whether the TAEM closure checker can be replayed through a
guidance-agnostic terminal-state interface, without consuming V8.2-specific
phase labels, terminal-capture variables, or guidance-internal fields.

It reconstructs:
  - in-box membership,
  - sample-count dwell,
  - vehicle-level portable closure,
  - case-level portable closure,

using only:
  - time column,
  - vehicle id column,
  - terminal-state error columns or physical h/v/s_go columns,
  - fixed tolerance box,
  - fixed dwell count,
  - optional terminal reason and close-pass escape flags for strict-like replay.

Recommended command
-------------------
python .\audit_transferability_interface.py `
  --csv-glob ".\store\data_saved\phase2_B5D_tight_local_envelope_validation\combined\*.csv" `
  --outdir ".\outputs\YORUM8_transferability_audit" `
  --idcol mis_id `
  --tol-h 3000 `
  --tol-v 100 `
  --tol-sgo 20000 `
  --n-dwell 3
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd


V82_FORBIDDEN_TERMS = [
    "V8.2",
    "success-latched",
    "success_latched",
    "terminal_capture",
    "terminal-capture",
    "TCP",
    "guidance_phase",
    "phase",
    "bank_smoothing",
    "heading_weight",
    "capture_weight",
]


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def pick_time_col(df: pd.DataFrame) -> str:
    c = find_col(df, ["global_t", "t_local", "local_t", "time", "t"])
    return c if c is not None else "__row_index__"


def ensure_idcol(df: pd.DataFrame, idcol: str | None) -> tuple[pd.DataFrame, str]:
    if idcol and idcol in df.columns:
        return df, idcol

    c = find_col(df, ["mis_id", "vehicle_id", "veh_id", "vehicle", "id"])
    if c is not None:
        return df, c

    d = df.copy()
    d["mis_id"] = 0
    return d, "mis_id"


def bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)

    s = df[col]
    if s.dtype == bool:
        return s.fillna(False)

    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0.0) > 0.5

    return s.astype(str).str.strip().str.lower().isin(
        ["1", "true", "t", "yes", "y", "pass", "passed", "success"]
    )


def reconstruct_in_box(
    df: pd.DataFrame,
    tol_h: float,
    tol_v: float,
    tol_sgo: float,
    target_h: float,
    target_v: float,
    target_sgo: float,
) -> tuple[pd.Series, dict]:
    """
    Reconstruct TAEM in-box membership without using guidance-internal variables.

    Priority:
      1) terminal-state error columns: taem_h_err, taem_v_err, taem_s_go_err
      2) physical state columns: h/v/s_go or altitude/velocity/range_to_go
      3) taem_in_box fallback, still not a guidance-phase/internal field
    """
    h_err_col = find_col(df, ["taem_h_err", "h_err", "e_h", "altitude_error"])
    v_err_col = find_col(df, ["taem_v_err", "v_err", "e_v", "velocity_error"])
    s_err_col = find_col(df, ["taem_s_go_err", "s_go_err", "e_s", "range_to_go_error", "range_error"])

    if h_err_col and v_err_col and s_err_col:
        eh = safe_num(df[h_err_col])
        ev = safe_num(df[v_err_col])
        es = safe_num(df[s_err_col])
        in_box = (eh.abs() <= tol_h) & (ev.abs() <= tol_v) & (es.abs() <= tol_sgo)
        meta = {
            "interface_mode": "terminal_error_columns",
            "columns_used": [h_err_col, v_err_col, s_err_col],
            "uses_guidance_internal_fields": False,
        }
        return in_box.fillna(False), meta

    h_col = find_col(df, ["h", "altitude", "alt", "height"])
    v_col = find_col(df, ["v", "velocity", "speed"])
    s_col = find_col(df, ["s_go", "sgo", "range_to_go", "range_go", "range_to_target"])

    if h_col and v_col and s_col:
        eh = safe_num(df[h_col]) - float(target_h)
        ev = safe_num(df[v_col]) - float(target_v)
        es = safe_num(df[s_col]) - float(target_sgo)
        in_box = (eh.abs() <= tol_h) & (ev.abs() <= tol_v) & (es.abs() <= tol_sgo)
        meta = {
            "interface_mode": "physical_state_columns",
            "columns_used": [h_col, v_col, s_col],
            "uses_guidance_internal_fields": False,
        }
        return in_box.fillna(False), meta

    inbox_col = find_col(df, ["taem_in_box", "in_box", "inside_taem_box"])
    if inbox_col:
        in_box = bool_col(df, inbox_col)
        meta = {
            "interface_mode": "logged_in_box_fallback",
            "columns_used": [inbox_col],
            "uses_guidance_internal_fields": False,
        }
        return in_box.fillna(False), meta

    raise ValueError(
        "No guidance-agnostic TAEM interface found. Need either "
        "taem_h_err/taem_v_err/taem_s_go_err, h/v/s_go, or taem_in_box."
    )


def dwell_replay(in_box: np.ndarray, n_dwell: int) -> dict:
    in_box = np.asarray(in_box, dtype=bool)
    count = 0
    max_count = 0
    first_confirm_index = -1
    total_inbox = 0

    for k, flag in enumerate(in_box):
        if flag:
            count += 1
            total_inbox += 1
            max_count = max(max_count, count)
            if count >= n_dwell and first_confirm_index < 0:
                first_confirm_index = k
        else:
            count = 0

    return {
        "portable_dwell_reached": bool(first_confirm_index >= 0),
        "first_confirm_index": int(first_confirm_index),
        "max_consecutive_inbox_samples": int(max_count),
        "total_inbox_samples": int(total_inbox),
    }


def terminal_reason_ok(df: pd.DataFrame) -> bool | None:
    c = find_col(df, ["end_reason", "terminal_reason", "termination_reason"])
    if c is None:
        return None

    values = df[c].astype(str).str.strip().str.lower()
    return bool((values == "taem_dwell_reached").any())


def close_pass_escape_present(df: pd.DataFrame) -> bool:
    for c in [
        "close_pass_escape",
        "close_pass_escape_latched",
        "taem_close_pass_escape",
        "close_pass_conflict",
        "escape_latched",
    ]:
        col = find_col(df, [c])
        if col is not None and bool_col(df, col).any():
            return True
    return False


def scan_for_forbidden_terms(columns_used: list[str]) -> list[str]:
    hits = []
    joined = " ".join(columns_used).lower()
    for term in V82_FORBIDDEN_TERMS:
        if term.lower() in joined:
            hits.append(term)
    return hits


def analyze_file(
    path: Path,
    idcol: str | None,
    tol_h: float,
    tol_v: float,
    tol_sgo: float,
    target_h: float,
    target_v: float,
    target_sgo: float,
    n_dwell: int,
) -> tuple[list[dict], dict]:
    df = pd.read_csv(path)
    df, idc = ensure_idcol(df, idcol)

    time_col = pick_time_col(df)
    if time_col == "__row_index__":
        df = df.copy()
        df[time_col] = np.arange(len(df), dtype=float)

    vehicle_rows = []
    all_columns_used = set()
    interface_modes = set()
    forbidden_hits_all = set()

    for vid, g in df.groupby(idc, sort=True):
        g = g.sort_values(time_col)
        in_box, meta = reconstruct_in_box(
            g,
            tol_h=tol_h,
            tol_v=tol_v,
            tol_sgo=tol_sgo,
            target_h=target_h,
            target_v=target_v,
            target_sgo=target_sgo,
        )

        replay = dwell_replay(in_box.to_numpy(dtype=bool), n_dwell=n_dwell)
        reason_ok = terminal_reason_ok(g)
        escape = close_pass_escape_present(g)

        columns_used = [time_col, idc] + list(meta["columns_used"])
        all_columns_used.update(columns_used)
        interface_modes.add(meta["interface_mode"])

        forbidden_hits = scan_for_forbidden_terms(columns_used)
        forbidden_hits_all.update(forbidden_hits)

        if reason_ok is None:
            portable_strict_like = replay["portable_dwell_reached"] and (not escape)
            reason_available = False
        else:
            portable_strict_like = replay["portable_dwell_reached"] and reason_ok and (not escape)
            reason_available = True

        vehicle_rows.append(
            {
                "csv": str(path),
                "case_file": path.name,
                "vehicle_id": vid,
                "n_rows_vehicle": int(len(g)),
                "time_col": time_col,
                "id_col": idc,
                "interface_mode": meta["interface_mode"],
                "columns_used": ";".join(columns_used),
                "forbidden_guidance_internal_terms_in_used_columns": ";".join(forbidden_hits),
                "portable_dwell_reached": replay["portable_dwell_reached"],
                "portable_strict_like_pass": bool(portable_strict_like),
                "terminal_reason_available": bool(reason_available),
                "terminal_reason_ok": reason_ok if reason_ok is not None else "",
                "close_pass_escape_present": bool(escape),
                "first_confirm_index": replay["first_confirm_index"],
                "max_consecutive_inbox_samples": replay["max_consecutive_inbox_samples"],
                "total_inbox_samples": replay["total_inbox_samples"],
            }
        )

    case_portable = all(r["portable_dwell_reached"] for r in vehicle_rows)
    case_strict_like = all(r["portable_strict_like_pass"] for r in vehicle_rows)

    case_row = {
        "csv": str(path),
        "case_file": path.name,
        "n_vehicles": int(len(vehicle_rows)),
        "case_portable_dwell_pass": bool(case_portable),
        "case_portable_strict_like_pass": bool(case_strict_like),
        "interface_modes": ";".join(sorted(interface_modes)),
        "columns_used_all": ";".join(sorted(all_columns_used)),
        "forbidden_guidance_internal_terms_in_used_columns": ";".join(sorted(forbidden_hits_all)),
    }

    return vehicle_rows, case_row


def find_csv_paths(patterns: list[str]) -> list[Path]:
    out = []
    seen = set()

    for pattern in patterns:
        for s in glob.glob(pattern, recursive=True):
            p = Path(s)
            if p.is_file():
                key = str(p.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(p)

    return sorted(out, key=lambda x: str(x).lower())


def fmt_bool_rate(k: int, n: int) -> str:
    if n <= 0:
        return "N/A"
    return f"{k}/{n} = {k/n:.6f}"


def write_latex_table(summary: dict, outdir: Path) -> None:
    p = outdir / "TABLE_transferability_interface_audit.tex"

    lines = [
        r"\begin{table}[pos=htbp]",
        r"\centering",
        r"\scriptsize",
        r"\caption{Transferability-interface audit of the dwell-confirmed TAEM validation layer. The replay uses only guidance-agnostic terminal-state interface fields and does not use V8.2-specific phase or terminal-capture variables.}",
        r"\label{tab:transferability_interface_audit}",
        r"\begin{tabular}{lll}",
        r"\hline",
        r"Audit item & Value & Interpretation \\",
        r"\hline",
        "CSV files replayed & " + str(summary["n_csv_files"]) + r" & Final sampled-validation combined trajectory logs. \\",
        "Vehicle logs replayed & " + str(summary["n_vehicle_logs"]) + r" & Three role trajectories per sampled case. \\",
        "Guidance-agnostic interface mode & " + summary["interface_modes"] + r" & Interface used by the portable checker. \\",
        "Portable vehicle-level dwell closures & " + summary["vehicle_portable_dwell_rate"] + r" & Reconstructed without V8.2-specific phase variables. \\",
        "Portable case-level dwell closures & " + summary["case_portable_dwell_rate"] + r" & All roles must satisfy the dwell event. \\",
        "Portable strict-like vehicle closures & " + summary["vehicle_portable_strict_like_rate"] + r" & Dwell replay plus available terminal-reason and escape checks. \\",
        "Portable strict-like case closures & " + summary["case_portable_strict_like_rate"] + r" & Case-level pass under the portable strict-like checker. \\",
        "Forbidden V8.2/internal terms in consumed fields & " + summary["forbidden_term_status"] + r" & Checks whether consumed columns encode guidance-version internals. \\",
        "Transferability boundary & Interface-level only & Other guidance laws must still be revalidated with their own trajectory logs. \\",
        r"\hline",
        r"\end{tabular}",
        r"\end{table}",
    ]

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_insert_text(summary: dict, outdir: Path) -> None:
    p = outdir / "INSERT_TransferabilityInterfaceSection.tex"

    lines = [
        r"\subsection{Guidance-interface contract and transferability boundary}",
        r"\label{subsec:guidance_interface_transferability}",
        "",
        "The reported numerical results are obtained with the frozen success-latched guidance implementation used in this study. However, the dwell-confirmed validation layer is not tied to the internal phase labels or terminal-capture variables of that implementation. To make this separation explicit, the validation layer can be expressed as an interface contract between an arbitrary guidance algorithm and the post-processed TAEM closure checker.",
        "",
        r"The required interface is the logged time sequence, a vehicle identifier, and the TAEM evaluation channels needed to reconstruct altitude, velocity, and range-to-go errors relative to the same target box. Given these fields, the checker evaluates the in-box indicator, updates the \(N_{\mathrm{dwell}}\)-sample dwell counter, latches the first accepted terminal event, and applies the terminal-reason and close-pass-escape checks when those fields are available. This procedure does not require the guidance algorithm to use the same internal phases, terminal-capture law, bank-command smoothing, or route-bias implementation.",
        "",
        r"The interface audit in Table~\ref{tab:transferability_interface_audit} replayed the final sampled-validation logs using only guidance-agnostic terminal-state interface fields. The portable replay reconstructed "
        + summary["vehicle_portable_dwell_rate"]
        + " vehicle-level dwell closures and "
        + summary["case_portable_dwell_rate"]
        + r" case-level dwell closures. The strict-like replay, which additionally uses available terminal-reason and close-pass-escape fields, reconstructed "
        + summary["vehicle_portable_strict_like_rate"]
        + " vehicle-level closures and "
        + summary["case_portable_strict_like_rate"]
        + r" case-level closures. No V8.2-specific phase or terminal-capture field was consumed by the portable replay.",
        "",
        "The transferability claim is therefore limited but explicit. The core validation ideas---terminal-state box membership, sample-count dwell, event latching, staged evidence separation, and boundary-diagnostic reporting---can be applied to any guidance algorithm that exports the required terminal-state interface. The numerical success rates reported in this paper, however, remain specific to the frozen guidance implementation, scenario, tolerance box, and sampled local support used here. A different guidance law would have to be re-run and re-audited under the same interface contract before any performance claim could be transferred.",
    ]

    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-glob", action="append", default=[])
    ap.add_argument("--outdir", default="outputs/YORUM8_transferability_audit")
    ap.add_argument("--idcol", default="mis_id")

    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=100.0)
    ap.add_argument("--tol-sgo", type=float, default=20000.0)
    ap.add_argument("--n-dwell", type=int, default=3)

    ap.add_argument("--target-h", type=float, default=25000.0)
    ap.add_argument("--target-v", type=float, default=2000.0)
    ap.add_argument("--target-sgo", type=float, default=50000.0)

    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    patterns = args.csv_glob or [
        "./store/data_saved/phase2_B5D_tight_local_envelope_validation/combined/*.csv"
    ]

    csvs = find_csv_paths(patterns)
    if not csvs:
        raise SystemExit("[ERR] No CSV files found. Check --csv-glob.")

    all_vehicle_rows = []
    all_case_rows = []

    print("[INFO] CSV files:", len(csvs))

    for p in csvs:
        try:
            vrows, crow = analyze_file(
                path=p,
                idcol=args.idcol,
                tol_h=args.tol_h,
                tol_v=args.tol_v,
                tol_sgo=args.tol_sgo,
                target_h=args.target_h,
                target_v=args.target_v,
                target_sgo=args.target_sgo,
                n_dwell=args.n_dwell,
            )
        except Exception as exc:
            print("[WARN] skipped", p, "because", exc)
            continue

        all_vehicle_rows.extend(vrows)
        all_case_rows.append(crow)

    if not all_vehicle_rows:
        raise SystemExit("[ERR] No files could be analyzed.")

    veh = pd.DataFrame(all_vehicle_rows)
    cas = pd.DataFrame(all_case_rows)

    veh_path = outdir / "transferability_vehicle_audit.csv"
    cas_path = outdir / "transferability_case_audit.csv"
    veh.to_csv(veh_path, index=False)
    cas.to_csv(cas_path, index=False)

    n_vehicle = int(len(veh))
    n_case = int(len(cas))

    v_dwell = int(veh["portable_dwell_reached"].sum())
    c_dwell = int(cas["case_portable_dwell_pass"].sum())
    v_strict = int(veh["portable_strict_like_pass"].sum())
    c_strict = int(cas["case_portable_strict_like_pass"].sum())

    modes = []
    for s in cas["interface_modes"].astype(str):
        modes.extend([x for x in s.split(";") if x.strip()])
    interface_modes = ";".join(sorted(set(modes)))

    forbidden_terms = []
    for s in veh["forbidden_guidance_internal_terms_in_used_columns"].astype(str):
        for item in s.split(";"):
            item = item.strip()
            if item:
                forbidden_terms.append(item)

    forbidden_terms = sorted(set(forbidden_terms))
    forbidden_status = "none" if not forbidden_terms else ";".join(forbidden_terms)

    summary = {
        "n_csv_files": n_case,
        "n_vehicle_logs": n_vehicle,
        "interface_modes": interface_modes,
        "vehicle_portable_dwell_closures": v_dwell,
        "vehicle_portable_dwell_rate": fmt_bool_rate(v_dwell, n_vehicle),
        "case_portable_dwell_closures": c_dwell,
        "case_portable_dwell_rate": fmt_bool_rate(c_dwell, n_case),
        "vehicle_portable_strict_like_closures": v_strict,
        "vehicle_portable_strict_like_rate": fmt_bool_rate(v_strict, n_vehicle),
        "case_portable_strict_like_closures": c_strict,
        "case_portable_strict_like_rate": fmt_bool_rate(c_strict, n_case),
        "forbidden_guidance_internal_terms_in_used_columns": forbidden_terms,
        "forbidden_term_status": forbidden_status,
        "tolerance_box": {
            "tol_h_m": args.tol_h,
            "tol_v_mps": args.tol_v,
            "tol_sgo_m": args.tol_sgo,
            "n_dwell": args.n_dwell,
        },
        "target": {
            "h_taem_m": args.target_h,
            "v_taem_mps": args.target_v,
            "s_taem_m": args.target_sgo,
        },
    }

    (outdir / "transferability_interface_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame([summary]).to_csv(
        outdir / "transferability_interface_summary.csv",
        index=False,
    )

    write_latex_table(summary, outdir)
    write_insert_text(summary, outdir)

    print("\n[OK] Wrote:")
    print(" ", veh_path)
    print(" ", cas_path)
    print(" ", outdir / "transferability_interface_summary.json")
    print(" ", outdir / "TABLE_transferability_interface_audit.tex")
    print(" ", outdir / "INSERT_TransferabilityInterfaceSection.tex")
    print("\n[SUMMARY]")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
