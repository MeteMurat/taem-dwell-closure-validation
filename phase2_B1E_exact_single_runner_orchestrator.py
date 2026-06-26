#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B1E exact-single-runner orchestrator.

Purpose
-------
Stop using the multi-adapter path for the B1 gate. The audit showed that the
single V8.2 baseline succeeds while the adapter fails despite matching initial
state and target. This script therefore runs the known V8.2 single-runner entry
point exactly, then adds a mis_id column and runs the B1 checker on that output.

Typical PowerShell usage
------------------------
python .\phase2_B1E_exact_single_runner_orchestrator.py

It expects these files in the project root:
  - single_mis1_main_v8_2_final_success_flags.py
  - multiset_phase2_B1R_from_success_csv_plus_pathspec.py
  - phase2_B1_mis1_transfer_check.py

It copies multiset_phase2_B1R_from_success_csv_plus_pathspec.py to multiset.py
unless --no-copy-multiset is provided.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd()))
    except Exception:
        return str(p)


def _require_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")


def _run(cmd: list[str], cwd: Path, log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8", errors="replace") as f:
        f.write("COMMAND:\n")
        f.write(" ".join(cmd) + "\n\n")
        f.flush()
        proc = subprocess.run(cmd, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, text=True)
        f.write(f"\nRETURN_CODE={proc.returncode}\n")
    return int(proc.returncode)


def _copy_multiset(src: Path, dst: Path, backup_dir: Path) -> Path | None:
    if not src.exists():
        raise FileNotFoundError(f"multiset source not found: {src}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if dst.exists():
        backup_path = backup_dir / f"multiset_BACKUP_before_B1E_{_ts()}.py"
        shutil.copy2(dst, backup_path)
    shutil.copy2(src, dst)
    return backup_path


def _make_scaffold_csv(single_csv: Path, scaffold_csv: Path, mis_id: int) -> dict:
    _require_file(single_csv, "single-runner output CSV")
    df = pd.read_csv(single_csv)
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])
    if "mis_id" in df.columns:
        df["mis_id"] = int(mis_id)
    else:
        df.insert(0, "mis_id", int(mis_id))
    scaffold_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(scaffold_csv, index=False)

    summary = {
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "mis_id_unique": sorted([int(x) for x in pd.to_numeric(df["mis_id"], errors="coerce").dropna().unique().tolist()]),
        "columns": list(df.columns),
    }
    for col in [
        "global_t", "t", "height", "velocity", "s_go", "delta_psi",
        "taem_success_latched", "taem_reached_ever", "taem_reached_event",
        "taem_reached", "taem_in_box", "end_reason", "close_pass_escape",
    ]:
        if col in df.columns:
            if col == "end_reason":
                summary[f"{col}_last"] = str(df[col].iloc[-1])
            elif df[col].dtype == object:
                summary[f"{col}_last"] = str(df[col].iloc[-1])
            else:
                s = pd.to_numeric(df[col], errors="coerce")
                summary[f"{col}_last"] = None if s.dropna().empty else float(s.iloc[-1])
                if col.startswith("taem") or col in ["close_pass_escape"]:
                    summary[f"{col}_any"] = bool((s.fillna(0) > 0.5).any())
    return summary


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="single_mis1_main_v8_2_final_success_flags.py")
    ap.add_argument("--mis-index", type=int, default=1)
    ap.add_argument("--multiset-source", default="multiset_phase2_B1R_from_success_csv_plus_pathspec.py")
    ap.add_argument("--no-copy-multiset", action="store_true")
    ap.add_argument("--single-out", default="store/data_saved/phase2_B1E_exact_single_runner_mis1.csv")
    ap.add_argument("--scaffold-out", default="store/data_saved/phase2_B1E_exact_single_scaffold_mis1.csv")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B1E_exact_single_report")
    ap.add_argument("--check-script", default="phase2_B1_mis1_transfer_check.py")
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=150.0)
    ap.add_argument("--tol-sgo", type=float, default=30000.0)
    ap.add_argument("--python", default=sys.executable)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    outdir = root / "store" / "data_saved" / "phase2_B1E_exact_single_orchestrator"
    outdir.mkdir(parents=True, exist_ok=True)

    runner = root / args.runner
    multiset_src = root / args.multiset_source
    multiset_dst = root / "multiset.py"
    single_out = root / args.single_out
    scaffold_out = root / args.scaffold_out
    check_script = root / args.check_script
    report_dir = root / args.report_dir

    _require_file(runner, "V8.2 exact single runner")
    _require_file(check_script, "B1 checker script")

    manifest: dict = {
        "root": str(root),
        "runner": str(runner),
        "mis_index": int(args.mis_index),
        "multiset_source": str(multiset_src),
        "single_out": str(single_out),
        "scaffold_out": str(scaffold_out),
        "report_dir": str(report_dir),
        "copied_multiset": False,
        "backup_multiset": None,
    }

    if not args.no_copy_multiset:
        backup = _copy_multiset(multiset_src, multiset_dst, outdir)
        manifest["copied_multiset"] = True
        manifest["backup_multiset"] = None if backup is None else str(backup)
        print(f"[B1E] copied {_rel(multiset_src)} -> multiset.py")
        if backup:
            print(f"[B1E] backup: {_rel(backup)}")
    else:
        print("[B1E] --no-copy-multiset: using current multiset.py")

    # Clean old outputs to avoid stale decision.
    for p in [single_out, scaffold_out]:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

    # The inspected runner uses args.mis_index and args.out; therefore use --mis-index and --out.
    cmd = [args.python, str(runner), "--mis-index", str(args.mis_index), "--out", str(single_out)]
    log_single = outdir / "single_runner_stdout_stderr.txt"
    print("[B1E] running exact single runner...")
    print("       " + " ".join(cmd))
    rc = _run(cmd, root, log_single)
    manifest["single_runner_return_code"] = int(rc)
    manifest["single_runner_log"] = str(log_single)
    if rc != 0:
        print(f"[B1E][ERR] single runner failed, see: {_rel(log_single)}")
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise SystemExit(rc)

    scaffold_summary = _make_scaffold_csv(single_out, scaffold_out, args.mis_index)
    manifest["scaffold_summary"] = scaffold_summary
    print(f"[B1E] wrote scaffold CSV: {_rel(scaffold_out)} rows={scaffold_summary['rows']}")

    report_dir.mkdir(parents=True, exist_ok=True)
    cmd_check = [
        args.python, str(check_script),
        "--csv", str(scaffold_out),
        "--outdir", str(report_dir),
        "--target-mis-id", str(args.mis_index),
        "--tol-h", str(args.tol_h),
        "--tol-v", str(args.tol_v),
        "--tol-sgo", str(args.tol_sgo),
    ]
    log_check = outdir / "checker_stdout_stderr.txt"
    print("[B1E] running B1 checker...")
    rc2 = _run(cmd_check, root, log_check)
    manifest["checker_return_code"] = int(rc2)
    manifest["checker_log"] = str(log_check)
    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    decision = report_dir / "phase2_B1_decision.txt"
    print("[B1E] manifest:", _rel(manifest_path))
    print("[B1E] decision:", _rel(decision))
    if decision.exists():
        print("\n" + decision.read_text(encoding="utf-8", errors="replace"))
    if rc2 != 0:
        raise SystemExit(rc2)


if __name__ == "__main__":
    main()
