# -*- coding: utf-8 -*-
"""
benchmark_realtime_taem.py

Purpose
-------
Reviewer 7 computational-burden / real-time-performance audit for the
dwell-confirmed TAEM closure manuscript.

This script measures:
1) Existing-log post-processing burden:
   - CSV reading time
   - TAEM in-box reconstruction / dwell replay time
   - rows processed per second
   - microseconds per logged row
   - vehicle-level event replay counts

2) Optional end-to-end simulation burden:
   - wall-clock time for an existing command, typically:
       python multi_main.py
   - generated CSV row count
   - simulated-time span
   - real-time factor = simulated_time_span / wall_clock_time
   - wall-clock milliseconds per logged sample

Outputs
-------
In --outdir:
- realtime_benchmark_summary.csv
- postprocess_benchmark_by_file.csv
- simulation_timing.csv, if --run-main is used
- realtime_benchmark_summary.json
- TABLE_computational_burden.tex
- INSERT_ComputationalBurdenSection.tex

Recommended first run
---------------------
python .\\benchmark_realtime_taem.py ^
  --csv-glob ".\\store\\data_saved\\phase2_B5D_tight_local_envelope_validation\\combined\\*.csv" ^
  --outdir ".\\outputs\\YORUM7_realtime_benchmark" ^
  --idcol mis_id ^
  --tol-h 3000 ^
  --tol-v 100 ^
  --tol-sgo 20000

Optional simulation timing run
------------------------------
python .\\benchmark_realtime_taem.py ^
  --run-main ^
  --reps 3 ^
  --main-cmd "python multi_main.py" ^
  --csv-glob ".\\store\\data_saved\\phase2_B5D_tight_local_envelope_validation\\combined\\*.csv" ^
  --outdir ".\\outputs\\YORUM7_realtime_benchmark_runmain" ^
  --idcol mis_id ^
  --tol-h 3000 ^
  --tol-v 100 ^
  --tol-sgo 20000
"""

from __future__ import annotations

import argparse
import csv
import gc
import glob
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean, median

import numpy as np
import pandas as pd


def now_perf() -> float:
    return time.perf_counter()


def safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype(float)


def bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)

    s = df[col]

    if s.dtype == bool:
        return s.fillna(False)

    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0.0) > 0.5

    return s.astype(str).str.strip().str.lower().isin(
        ["1", "true", "t", "yes", "y", "pass", "pass_strict", "reached"]
    )


def pick_time_col(df: pd.DataFrame) -> str:
    for c in ["global_t", "t_local", "t"]:
        if c in df.columns:
            return c
    return "__row_index__"


def ensure_idcol(df: pd.DataFrame, idcol: str | None) -> tuple[pd.DataFrame, str]:
    if idcol and idcol in df.columns:
        return df, idcol
    if "mis_id" in df.columns:
        return df, "mis_id"

    d = df.copy()
    d["mis_id"] = 0
    return d, "mis_id"


def compute_in_box(
    df: pd.DataFrame,
    tol_h: float | None,
    tol_v: float | None,
    tol_sgo: float | None,
) -> pd.Series:
    """
    Priority order:
    1) taem_in_box, if present.
    2) Reconstruct from taem_h_err, taem_v_err, taem_s_go_err.
    3) taem_reached as weaker fallback.
    4) all False.
    """
    if "taem_in_box" in df.columns:
        return bool_col(df, "taem_in_box")

    has_err = all(c in df.columns for c in ["taem_h_err", "taem_v_err", "taem_s_go_err"])
    has_tol = tol_h is not None and tol_v is not None and tol_sgo is not None

    if has_err and has_tol:
        h_ok = safe_num(df["taem_h_err"]).abs() <= float(tol_h)
        v_ok = safe_num(df["taem_v_err"]).abs() <= float(tol_v)
        s_ok = safe_num(df["taem_s_go_err"]).abs() <= float(tol_sgo)
        return h_ok & v_ok & s_ok

    if "taem_reached" in df.columns:
        return bool_col(df, "taem_reached")

    return pd.Series([False] * len(df), index=df.index)


def dwell_replay_numpy(in_box: np.ndarray, n_dwell: int) -> tuple[bool, int, int, int]:
    """
    Fast sample-count dwell replay.
    Returns:
      reached, first_confirm_index, max_consecutive, total_in_box_samples
    """
    in_box = np.asarray(in_box, dtype=bool)
    c = 0
    max_c = 0
    first_confirm = -1
    total = 0

    for i, flag in enumerate(in_box):
        if flag:
            c += 1
            total += 1
            if c > max_c:
                max_c = c
            if c >= n_dwell and first_confirm < 0:
                first_confirm = i
        else:
            c = 0

    return first_confirm >= 0, first_confirm, max_c, total


def summarize_csv_timing(
    csv_path: Path,
    idcol: str | None,
    n_dwell: int,
    tol_h: float | None,
    tol_v: float | None,
    tol_sgo: float | None,
) -> dict:
    t0 = now_perf()
    df = pd.read_csv(csv_path)
    t1 = now_perf()

    df, idc = ensure_idcol(df, idcol)

    time_col = pick_time_col(df)
    if time_col == "__row_index__":
        df = df.copy()
        df[time_col] = np.arange(len(df), dtype=float)

    t2 = now_perf()
    in_box = compute_in_box(df, tol_h, tol_v, tol_sgo)
    t3 = now_perf()

    replay_rows = []
    replay_t0 = now_perf()

    for vid, g in df.groupby(idc, sort=True):
        idx = g.index
        tvals = safe_num(g[time_col]).to_numpy(dtype=float)
        inbox_vals = in_box.loc[idx].to_numpy(dtype=bool)

        reached, first_idx, max_consecutive, total_inbox = dwell_replay_numpy(inbox_vals, n_dwell)

        if len(tvals):
            sim_start = float(np.nanmin(tvals))
            sim_end = float(np.nanmax(tvals))
            sim_span = sim_end - sim_start
        else:
            sim_start = np.nan
            sim_end = np.nan
            sim_span = np.nan

        replay_rows.append(
            {
                "vehicle_id": vid,
                "n_rows_vehicle": int(len(g)),
                "sim_start_s": sim_start,
                "sim_end_s": sim_end,
                "sim_span_s": sim_span,
                "dwell_reached": bool(reached),
                "first_confirm_index": int(first_idx),
                "max_consecutive_inbox_samples": int(max_consecutive),
                "total_inbox_samples": int(total_inbox),
            }
        )

    replay_t1 = now_perf()

    n_rows = int(len(df))
    n_vehicles = int(df[idc].nunique()) if idc in df.columns else 1
    spans = [r["sim_span_s"] for r in replay_rows if np.isfinite(r["sim_span_s"])]
    sim_span_max = float(max(spans)) if spans else np.nan

    read_s = t1 - t0
    prep_s = t2 - t1
    inbox_s = t3 - t2
    replay_s = replay_t1 - replay_t0
    processing_s = inbox_s + replay_s
    total_s = replay_t1 - t0

    return {
        "csv": str(csv_path),
        "file_name": csv_path.name,
        "n_rows": n_rows,
        "n_vehicles": n_vehicles,
        "time_col": time_col,
        "sim_span_max_s": sim_span_max,
        "csv_read_s": read_s,
        "prep_s": prep_s,
        "inbox_reconstruct_s": inbox_s,
        "dwell_replay_s": replay_s,
        "processing_excluding_io_s": processing_s,
        "total_including_io_s": total_s,
        "rows_per_s_excluding_io": n_rows / processing_s if processing_s > 0 else np.nan,
        "us_per_row_excluding_io": 1.0e6 * processing_s / n_rows if n_rows > 0 else np.nan,
        "rows_per_s_including_io": n_rows / total_s if total_s > 0 else np.nan,
        "us_per_row_including_io": 1.0e6 * total_s / n_rows if n_rows > 0 else np.nan,
        "vehicle_replay": replay_rows,
    }


def find_csv_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen = set()

    for pat in patterns:
        for s in glob.glob(pat, recursive=True):
            p = Path(s)
            if p.is_file():
                rp = str(p.resolve())
                if rp not in seen:
                    seen.add(rp)
                    paths.append(p)

    return sorted(paths, key=lambda p: str(p).lower())


def snapshot_csv_files(root: Path) -> dict[str, float]:
    out = {}
    for p in root.rglob("*.csv"):
        try:
            out[str(p.resolve())] = p.stat().st_mtime
        except OSError:
            pass
    return out


def newest_changed_csvs(before: dict[str, float], root: Path, after_time: float) -> list[Path]:
    changed = []
    for p in root.rglob("*.csv"):
        try:
            rp = str(p.resolve())
            mt = p.stat().st_mtime
        except OSError:
            continue

        old = before.get(rp)
        if old is None and mt >= after_time - 5.0:
            changed.append(p)
        elif old is not None and mt > old + 1e-6:
            changed.append(p)

    return sorted(changed, key=lambda x: x.stat().st_mtime, reverse=True)


def run_main_command(command: str, cwd: Path, rep: int, outdir: Path) -> dict:
    before = snapshot_csv_files(cwd)

    log_path = outdir / f"simulation_run_rep{rep:02d}.log"
    err_path = outdir / f"simulation_run_rep{rep:02d}.err"

    cmd = shlex.split(command, posix=False) if os.name == "nt" else shlex.split(command)

    t0 = now_perf()
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        shell=False,
    )
    t1 = now_perf()

    log_path.write_text(completed.stdout or "", encoding="utf-8", errors="replace")
    err_path.write_text(completed.stderr or "", encoding="utf-8", errors="replace")

    changed = newest_changed_csvs(before, cwd, time.time())
    changed_csv = str(changed[0]) if changed else ""

    row_count = np.nan
    n_vehicles = np.nan
    sim_span = np.nan

    if changed:
        try:
            df = pd.read_csv(changed[0])
            row_count = int(len(df))
            if "mis_id" in df.columns:
                n_vehicles = int(df["mis_id"].nunique())
            else:
                n_vehicles = 1

            tcol = pick_time_col(df)
            if tcol != "__row_index__":
                sim_span = float(pd.to_numeric(df[tcol], errors="coerce").max() - pd.to_numeric(df[tcol], errors="coerce").min())
        except Exception:
            pass

    wall_s = t1 - t0

    return {
        "rep": int(rep),
        "command": command,
        "return_code": int(completed.returncode),
        "wall_s": float(wall_s),
        "changed_csv": changed_csv,
        "row_count": row_count,
        "n_vehicles": n_vehicles,
        "sim_span_max_s": sim_span,
        "real_time_factor": float(sim_span / wall_s) if np.isfinite(sim_span) and wall_s > 0 else np.nan,
        "ms_per_logged_row": float(1000.0 * wall_s / row_count) if np.isfinite(row_count) and row_count > 0 else np.nan,
        "stdout_log": str(log_path),
        "stderr_log": str(err_path),
    }


def fmt_float(x, nd=3):
    try:
        if x is None or not np.isfinite(float(x)):
            return "N/A"
        return f"{float(x):.{nd}f}"
    except Exception:
        return "N/A"



def write_latex_and_text(summary: dict, outdir: Path):
    table_path = outdir / "TABLE_computational_burden.tex"
    text_path = outdir / "INSERT_ComputationalBurdenSection.tex"

    sim = summary.get("simulation", {})
    post = summary.get("postprocess", {})

    sim_wall_med = sim.get("wall_s_median", np.nan)
    sim_rtf_med = sim.get("real_time_factor_median", np.nan)
    sim_ms_row_med = sim.get("ms_per_logged_row_median", np.nan)
    sim_rows_med = sim.get("row_count_median", np.nan)
    sim_span_med = sim.get("sim_span_max_s_median", np.nan)

    post_files = post.get("n_files", np.nan)
    post_rows = post.get("n_rows_total", np.nan)
    post_proc_s = post.get("processing_excluding_io_s_total", np.nan)
    post_us_row = post.get("us_per_row_excluding_io_weighted", np.nan)
    post_rows_per_s = post.get("rows_per_s_excluding_io_weighted", np.nan)
    post_total_s = post.get("total_including_io_s_total", np.nan)

    table_lines = []
    table_lines.append(r"\begin{table}[pos=htbp]")
    table_lines.append(r"\centering")
    table_lines.append(r"\scriptsize")
    table_lines.append(r"\caption{Computational-burden audit for the guidance--logging--TAEM event-detection workflow. The timing values are hardware- and implementation-dependent and are reported as a reproducibility audit rather than as embedded-flight certification.}")
    table_lines.append(r"\label{tab:computational_burden_audit}")
    table_lines.append(r"\begin{tabular}{lll}")
    table_lines.append(r"\hline")
    table_lines.append(r"Audit item & Measured value & Interpretation \\")
    table_lines.append(r"\hline")
    table_lines.append("End-to-end three-role simulation wall time & " + fmt_float(sim_wall_med, 3) + r" s & Median wall-clock time for the timed execution command. \\")
    table_lines.append("Simulated trajectory time span & " + fmt_float(sim_span_med, 3) + r" s & Maximum logged simulated-time span in the generated run. \\")
    table_lines.append("Real-time factor & " + fmt_float(sim_rtf_med, 2) + r" & Simulated-time span divided by wall-clock time. \\")
    table_lines.append("Logged samples per timed simulation & " + fmt_float(sim_rows_med, 0) + r" & Number of saved trajectory rows in the timed output. \\")
    table_lines.append("Wall time per logged sample & " + fmt_float(sim_ms_row_med, 4) + r" ms & End-to-end simulation wall time normalized by saved rows. \\")
    table_lines.append("CSV files replayed for event audit & " + fmt_float(post_files, 0) + r" & Existing final-campaign logs used for event-detection timing. \\")
    table_lines.append("Logged rows replayed for event audit & " + fmt_float(post_rows, 0) + r" & Total rows processed by the dwell/event replay audit. \\")
    table_lines.append("Dwell/event replay time excluding CSV I/O & " + fmt_float(post_proc_s, 6) + r" s & Time for in-box reconstruction and dwell replay only. \\")
    table_lines.append("Dwell/event replay cost per row & " + fmt_float(post_us_row, 3) + r" $\mu$s/row & Per-row post-processing overhead of the event detector. \\")
    table_lines.append("Dwell/event replay throughput & " + fmt_float(post_rows_per_s, 0) + r" rows/s & Logged-row processing throughput excluding CSV I/O. \\")
    table_lines.append("Total replay time including CSV I/O & " + fmt_float(post_total_s, 3) + r" s & End-to-end log-reading plus event-replay time. \\")
    table_lines.append(r"\hline")
    table_lines.append(r"\end{tabular}")
    table_lines.append(r"\end{table}")
    table = "\n".join(table_lines)

    text_lines = []
    text_lines.append(r"\subsection{Computational-burden and real-time audit}")
    text_lines.append(r"\label{subsec:computational_burden_audit}")
    text_lines.append("")
    text_lines.append("Because the proposed validation layer is intended for online entry-guidance assessment, the computational burden of the guidance--logging--event-detection workflow was audited in addition to the closure statistics. The audit separates two costs. The first is the end-to-end wall-clock time required to execute the three-role guidance and propagation workflow. The second is the cost of reconstructing TAEM box membership and replaying the dwell-confirmed event detector from saved trajectory logs. The latter is the computational overhead added by the proposed validation logic and is distinct from the trajectory propagation itself.")
    text_lines.append("")
    text_lines.append(r"For a run with wall-clock time \(t_{\mathrm{wall}}\), logged simulated-time span \(T_{\mathrm{sim}}\), and \(N_{\mathrm{row}}\) saved trajectory samples, the real-time factor is computed as")
    text_lines.append(r"\[")
    text_lines.append(r"\chi_{\mathrm{RT}}=\frac{T_{\mathrm{sim}}}{t_{\mathrm{wall}}},")
    text_lines.append(r"\]")
    text_lines.append(r"and the end-to-end logged-sample cost is \(1000\,t_{\mathrm{wall}}/N_{\mathrm{row}}\) ms per saved row. For the event-replay audit, the per-row dwell-detection cost is computed from the time required to reconstruct the in-box sequence and update the sample-count dwell latch over all logged rows. The dwell/event replay is a linear pass over the logged samples, with \(O(N_vK)\) complexity for \(N_v\) vehicle roles and \(K\) samples per role; it does not require optimization, root finding, or trajectory repropagation.")
    text_lines.append("")
    text_lines.append("The measured values are summarized in Table~\\ref{tab:computational_burden_audit}. On the tested software and hardware configuration, the timed three-role execution required a median wall-clock time of " + fmt_float(sim_wall_med, 3) + "~s for a logged simulated-time span of " + fmt_float(sim_span_med, 3) + "~s, corresponding to a real-time factor of " + fmt_float(sim_rtf_med, 2) + ". The dwell/event replay over " + fmt_float(post_rows, 0) + " logged rows required " + fmt_float(post_proc_s, 6) + "~s excluding CSV input/output, corresponding to " + fmt_float(post_us_row, 3) + "~\\(\\mu\\)s per row. Thus, the event-detection layer is negligible relative to the trajectory propagation and guidance computation in the present implementation.")
    text_lines.append("")
    text_lines.append("These timings should be interpreted as an implementation-level reproducibility audit, not as certification of a flight processor or hard real-time avionics implementation. The code used in this study is a Python research implementation with CSV logging and diagnostic bookkeeping retained for auditability. Nevertheless, the measured event-detection cost shows that the dwell-confirmed TAEM closure logic itself is computationally light: it requires only component-wise tolerance checks, an integer dwell counter, and a latch update at each logged sample.")
    text = "\n".join(text_lines)

    table_path.write_text(table + "\n", encoding="utf-8")
    text_path.write_text(text + "\n", encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--csv-glob", action="append", default=[], help="Glob pattern for existing trajectory CSV files.")
    ap.add_argument("--outdir", default="outputs/YORUM7_realtime_benchmark", help="Output directory.")
    ap.add_argument("--idcol", default="mis_id", help="Vehicle id column.")
    ap.add_argument("--n-dwell", type=int, default=3, help="Required consecutive in-box samples.")
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=100.0)
    ap.add_argument("--tol-sgo", type=float, default=20000.0)

    ap.add_argument("--run-main", action="store_true", help="Also time an end-to-end simulation command.")
    ap.add_argument("--main-cmd", default="python multi_main.py", help="Command to time if --run-main is used.")
    ap.add_argument("--reps", type=int, default=1, help="Number of simulation timing repetitions.")

    args = ap.parse_args()

    root = Path.cwd()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    print("[INFO] Root:", root)
    print("[INFO] Outdir:", outdir)

    env_info = {
        "python": sys.version.replace("\n", " "),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "cwd": str(root),
    }

    # ------------------------------------------------------------
    # Existing CSV post-processing benchmark
    # ------------------------------------------------------------
    patterns = args.csv_glob
    if not patterns:
        patterns = [
            "./store/data_saved/phase2_B5D_tight_local_envelope_validation/combined/*.csv",
            "./store/data_saved/phase2_B5D_tight_local_envelope_validation_report/combined/*.csv",
            "./outputs/**/*.csv",
        ]

    csv_paths = find_csv_paths(patterns)

    if not csv_paths:
        raise SystemExit("[ERR] No CSV files found. Provide --csv-glob.")

    print(f"[INFO] CSV files found for replay: {len(csv_paths)}")

    by_file_rows = []
    vehicle_rows = []

    gc.collect()
    gc.disable()
    try:
        for p in csv_paths:
            try:
                r = summarize_csv_timing(
                    csv_path=p,
                    idcol=args.idcol,
                    n_dwell=args.n_dwell,
                    tol_h=args.tol_h,
                    tol_v=args.tol_v,
                    tol_sgo=args.tol_sgo,
                )
            except Exception as exc:
                print(f"[WARN] Skipping {p}: {exc}")
                continue

            vrows = r.pop("vehicle_replay")
            by_file_rows.append(r)

            for vr in vrows:
                vr["csv"] = str(p)
                vr["file_name"] = p.name
                vehicle_rows.append(vr)
    finally:
        gc.enable()

    by_file = pd.DataFrame(by_file_rows)
    by_vehicle = pd.DataFrame(vehicle_rows)

    if by_file.empty:
        raise SystemExit("[ERR] No CSV files could be processed.")

    by_file_path = outdir / "postprocess_benchmark_by_file.csv"
    by_vehicle_path = outdir / "postprocess_benchmark_by_vehicle.csv"

    by_file.to_csv(by_file_path, index=False)
    by_vehicle.to_csv(by_vehicle_path, index=False)

    total_rows = int(by_file["n_rows"].sum())
    total_processing = float(by_file["processing_excluding_io_s"].sum())
    total_including_io = float(by_file["total_including_io_s"].sum())

    post_summary = {
        "n_files": int(len(by_file)),
        "n_rows_total": total_rows,
        "n_vehicles_total_rows": int(len(by_vehicle)),
        "processing_excluding_io_s_total": total_processing,
        "total_including_io_s_total": total_including_io,
        "rows_per_s_excluding_io_weighted": total_rows / total_processing if total_processing > 0 else np.nan,
        "us_per_row_excluding_io_weighted": 1.0e6 * total_processing / total_rows if total_rows > 0 else np.nan,
        "rows_per_s_including_io_weighted": total_rows / total_including_io if total_including_io > 0 else np.nan,
        "us_per_row_including_io_weighted": 1.0e6 * total_including_io / total_rows if total_rows > 0 else np.nan,
        "median_file_processing_excluding_io_s": float(by_file["processing_excluding_io_s"].median()),
        "median_file_total_including_io_s": float(by_file["total_including_io_s"].median()),
    }

    # ------------------------------------------------------------
    # Optional simulation wall-clock benchmark
    # ------------------------------------------------------------
    sim_rows = []
    sim_summary = {
        "run_main_used": bool(args.run_main),
        "wall_s_median": np.nan,
        "real_time_factor_median": np.nan,
        "ms_per_logged_row_median": np.nan,
        "row_count_median": np.nan,
        "sim_span_max_s_median": np.nan,
    }

    if args.run_main:
        print(f"[INFO] Timing simulation command: {args.main_cmd}")
        for rep in range(1, args.reps + 1):
            print(f"[INFO] Simulation timing repetition {rep}/{args.reps}")
            r = run_main_command(args.main_cmd, cwd=root, rep=rep, outdir=outdir)
            sim_rows.append(r)
            print("[INFO] return_code:", r["return_code"], "wall_s:", r["wall_s"], "RTF:", r["real_time_factor"])

        sim_df = pd.DataFrame(sim_rows)
        sim_df.to_csv(outdir / "simulation_timing.csv", index=False)

        ok = sim_df[sim_df["return_code"] == 0].copy()
        if not ok.empty:
            sim_summary = {
                "run_main_used": True,
                "n_reps": int(len(ok)),
                "wall_s_median": float(ok["wall_s"].median()),
                "wall_s_min": float(ok["wall_s"].min()),
                "wall_s_max": float(ok["wall_s"].max()),
                "real_time_factor_median": float(ok["real_time_factor"].median()) if "real_time_factor" in ok else np.nan,
                "ms_per_logged_row_median": float(ok["ms_per_logged_row"].median()) if "ms_per_logged_row" in ok else np.nan,
                "row_count_median": float(ok["row_count"].median()) if "row_count" in ok else np.nan,
                "sim_span_max_s_median": float(ok["sim_span_max_s"].median()) if "sim_span_max_s" in ok else np.nan,
            }

    # ------------------------------------------------------------
    # Output summary
    # ------------------------------------------------------------
    summary = {
        "environment": env_info,
        "postprocess": post_summary,
        "simulation": sim_summary,
        "csv_patterns": patterns,
    }

    summary_json = outdir / "realtime_benchmark_summary.json"
    summary_csv = outdir / "realtime_benchmark_summary.csv"

    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    flat = {}
    for group, d in summary.items():
        if isinstance(d, dict):
            for k, v in d.items():
                flat[f"{group}.{k}"] = v
        else:
            flat[group] = str(d)

    pd.DataFrame([flat]).to_csv(summary_csv, index=False)

    write_latex_and_text(summary, outdir)

    print("\n[OK] Wrote:")
    print(" ", by_file_path)
    print(" ", by_vehicle_path)
    print(" ", summary_csv)
    print(" ", summary_json)
    print(" ", outdir / "TABLE_computational_burden.tex")
    print(" ", outdir / "INSERT_ComputationalBurdenSection.tex")

    print("\n[SUMMARY]")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()