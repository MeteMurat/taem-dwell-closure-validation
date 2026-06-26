#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B2 exact-single sequential orchestration.

Runs the known V8.2 exact single-runner entry point sequentially for mis0, mis1,
and mis2, then combines the per-vehicle CSVs into one campaign CSV and applies
the existing B1/B2 event checker per vehicle.

This is not a guidance patch. It is the replacement experimental harness for
Phase 2 after B1E proved that exact-single orchestration is reliable while the
simultaneous MultiMissileSim adapter path is not.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _run(cmd: list[str], cwd: Path, log_path: Path, env: dict[str, str] | None = None) -> int:
    run_env = os.environ.copy()
    run_env.setdefault("PYTHONUTF8", "1")
    run_env.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        run_env.update(env)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as f:
        f.write("COMMAND:\n")
        f.write(" ".join(cmd) + "\n\n")
        f.flush()
        proc = subprocess.run(cmd, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, text=True, env=run_env)
        f.write(f"\nRETURN_CODE={proc.returncode}\n")
    return int(proc.returncode)


def _copy_multiset(src: Path, dst: Path, backup_dir: Path) -> Path | None:
    if not src.exists():
        raise FileNotFoundError(f"multiset source not found: {src}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if dst.exists():
        backup_path = backup_dir / f"multiset_BACKUP_before_B2_{_ts()}.py"
        shutil.copy2(dst, backup_path)
    shutil.copy2(src, dst)
    return backup_path


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _truth(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    try:
        return float(v) > 0.5
    except Exception:
        return str(v).strip().lower() in {"true", "1", "yes", "y", "t"}


def _float_or_none(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _classify(row: dict[str, Any], tol_h: float, tol_v: float, tol_sgo: float) -> str:
    if _truth(row.get("b1_strict_pass")) or str(row.get("b1_vehicle_decision", "")).upper() == "PASS_STRICT":
        return "Clean TAEM success"

    h_min = _float_or_none(row.get("taem_h_err_min_abs"))
    v_min = _float_or_none(row.get("taem_v_err_min_abs"))
    s_min = _float_or_none(row.get("taem_s_go_err_min_abs"))
    end_reason = str(row.get("end_reason_last", ""))
    close = _truth(row.get("any_close_pass_escape")) or _truth(row.get("last_close_pass_escape")) or end_reason == "close_pass_escape"
    in_box = _truth(row.get("any_taem_in_box"))

    h_ok = h_min is not None and h_min <= tol_h
    v_ok = v_min is not None and v_min <= tol_v
    s_ok = s_min is not None and s_min <= tol_sgo

    if in_box:
        return "Near-success / no dwell"
    if h_ok and v_ok and not s_ok and close:
        return "Close-pass escape / range-closure failure"
    if h_ok and v_ok and not s_ok:
        return "Range-closure failure"
    if (not h_ok) and v_ok and s_ok:
        return "Altitude closure failure"
    if h_ok and (not v_ok) and s_ok:
        return "Energy/speed closure failure"
    if close:
        return "Close-pass escape"
    return "Mixed geometry-energy failure"


def _add_mis_id(single_csv: Path, scaffold_csv: Path, mis_id: int) -> dict[str, Any]:
    if not single_csv.exists():
        raise FileNotFoundError(f"single-runner CSV not found for mis{mis_id}: {single_csv}")
    df = pd.read_csv(single_csv)
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])
    if "mis_id" in df.columns:
        df["mis_id"] = int(mis_id)
    else:
        df.insert(0, "mis_id", int(mis_id))
    scaffold_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(scaffold_csv, index=False)
    out: dict[str, Any] = {"mis_id": int(mis_id), "rows": int(len(df)), "cols": int(len(df.columns)), "csv": str(scaffold_csv)}
    for col in ["global_t", "height", "velocity", "s_go", "delta_psi", "taem_success_latched", "taem_reached", "taem_in_box", "end_reason"]:
        if col in df.columns and len(df):
            if col == "end_reason":
                out[f"{col}_last"] = str(df[col].iloc[-1])
            else:
                s = pd.to_numeric(df[col], errors="coerce")
                out[f"{col}_last"] = None if s.dropna().empty else float(s.iloc[-1])
                if col.startswith("taem"):
                    out[f"{col}_any"] = bool((s.fillna(0) > 0.5).any())
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="single_mis1_main_v8_2_final_success_flags.py")
    ap.add_argument("--vehicle-ids", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--multiset-source", default="multiset_phase2_B2_exact_single_role_specs.py")
    ap.add_argument("--no-copy-multiset", action="store_true")
    ap.add_argument("--check-script", default="phase2_B1_mis1_transfer_check.py")
    ap.add_argument("--outdir", default="store/data_saved/phase2_B2_exact_single_orchestrator")
    ap.add_argument("--run-dir", default="store/data_saved/phase2_B2_exact_single_runs")
    ap.add_argument("--combined-csv", default="store/data_saved/phase2_B2_exact_single_combined.csv")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B2_exact_single_report")
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=150.0)
    ap.add_argument("--tol-sgo", type=float, default=30000.0)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--continue-on-run-fail", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    outdir = root / args.outdir
    run_dir = root / args.run_dir
    report_dir = root / args.report_dir
    combined_csv = root / args.combined_csv
    outdir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    runner = root / args.runner
    check_script = root / args.check_script
    multiset_src = root / args.multiset_source
    multiset_dst = root / "multiset.py"

    _require_file(runner, "V8.2 exact single runner")
    _require_file(check_script, "TAEM checker script")

    manifest: dict[str, Any] = {
        "root": str(root),
        "runner": str(runner),
        "vehicle_ids": [int(x) for x in args.vehicle_ids],
        "multiset_source": str(multiset_src),
        "combined_csv": str(combined_csv),
        "report_dir": str(report_dir),
        "copied_multiset": False,
        "backup_multiset": None,
        "runs": [],
    }

    if not args.no_copy_multiset:
        backup = _copy_multiset(multiset_src, multiset_dst, outdir)
        manifest["copied_multiset"] = True
        manifest["backup_multiset"] = None if backup is None else str(backup)
        print(f"[B2] copied {_rel(multiset_src)} -> multiset.py")
        if backup:
            print(f"[B2] backup: {_rel(backup)}")
    else:
        print("[B2] --no-copy-multiset: using current multiset.py")

    # Clean old combined output. Keep old per-run logs unless overwritten by same names.
    if combined_csv.exists():
        combined_csv.unlink()

    scaffold_paths: list[Path] = []
    for mid in args.vehicle_ids:
        single_out = run_dir / f"phase2_B2_exact_single_runner_mis{mid}.csv"
        scaffold_out = run_dir / f"phase2_B2_exact_single_scaffold_mis{mid}.csv"
        log_path = outdir / f"single_runner_mis{mid}_stdout_stderr.txt"
        for p in [single_out, scaffold_out]:
            if p.exists():
                p.unlink()
        cmd = [args.python, str(runner), "--mis-index", str(mid), "--out", str(single_out)]
        print(f"[B2] running exact single runner for mis{mid}...")
        print("     " + " ".join(cmd))
        rc = _run(cmd, root, log_path)
        run_record: dict[str, Any] = {"mis_id": int(mid), "return_code": int(rc), "log": str(log_path), "single_csv": str(single_out)}
        if rc != 0:
            print(f"[B2][ERR] single runner failed for mis{mid}; see {_rel(log_path)}")
            run_record["status"] = "RUN_FAILED"
            manifest["runs"].append(run_record)
            if not args.continue_on_run_fail:
                (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                raise SystemExit(rc)
            continue
        scaffold_summary = _add_mis_id(single_out, scaffold_out, mid)
        run_record["status"] = "RUN_OK"
        run_record["scaffold_csv"] = str(scaffold_out)
        run_record["scaffold_summary"] = scaffold_summary
        scaffold_paths.append(scaffold_out)
        manifest["runs"].append(run_record)
        print(f"[B2] wrote scaffold CSV for mis{mid}: {_rel(scaffold_out)} rows={scaffold_summary['rows']}")

    if not scaffold_paths:
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise SystemExit("[B2][ERR] No successful vehicle CSVs were produced.")

    frames = [pd.read_csv(p) for p in scaffold_paths]
    combined = pd.concat(frames, ignore_index=True)
    if "mis_id" in combined.columns:
        tcol = "global_t" if "global_t" in combined.columns else ("t" if "t" in combined.columns else None)
        if tcol:
            combined = combined.sort_values(["mis_id", tcol], kind="mergesort").reset_index(drop=True)
    combined_csv.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(combined_csv, index=False)
    manifest["combined_rows"] = int(len(combined))
    manifest["combined_columns"] = list(combined.columns)
    print(f"[B2] wrote combined CSV: {_rel(combined_csv)} rows={len(combined)}")

    # Run checker per vehicle.
    b2_rows: list[dict[str, Any]] = []
    for mid in args.vehicle_ids:
        if mid not in set(pd.to_numeric(combined["mis_id"], errors="coerce").dropna().astype(int).tolist()):
            b2_rows.append({"vehicle_id": int(mid), "run_status": "MISSING_RUN", "b2_label": "Run failed / missing CSV"})
            continue
        vehicle_report = report_dir / f"mis{mid}"
        vehicle_report.mkdir(parents=True, exist_ok=True)
        log_path = outdir / f"checker_mis{mid}_stdout_stderr.txt"
        cmd_check = [
            args.python, str(check_script),
            "--csv", str(combined_csv),
            "--outdir", str(vehicle_report),
            "--target-mis-id", str(mid),
            "--tol-h", str(args.tol_h),
            "--tol-v", str(args.tol_v),
            "--tol-sgo", str(args.tol_sgo),
        ]
        print(f"[B2] running checker for mis{mid}...")
        rc = _run(cmd_check, root, log_path)
        dec_json = _read_json(vehicle_report / "phase2_B1_decision.json")
        target_row = (dec_json or {}).get("target_row", {}) if dec_json else {}
        row: dict[str, Any] = {"vehicle_id": int(mid), "checker_return_code": int(rc), "report_dir": str(vehicle_report)}
        row.update({
            "decision": (dec_json or {}).get("decision", "CHECKER_JSON_MISSING"),
            "strict_pass": bool((dec_json or {}).get("strict_pass", False)),
            "soft_pass": bool((dec_json or {}).get("soft_pass", False)),
        })
        for key in [
            "b1_vehicle_decision", "any_taem_success_latched", "last_taem_success_latched",
            "any_taem_reached_ever", "last_taem_reached_ever", "any_taem_reached_event",
            "last_taem_reached_event", "any_taem_reached", "last_taem_reached",
            "any_taem_in_box", "last_taem_in_box", "any_close_pass_escape", "last_close_pass_escape",
            "end_reason_last", "guide_phase_last", "taem_dwell_s_max_logged", "taem_dwell_count_max_logged",
            "dwell_max_s_computed", "taem_h_err_final", "taem_h_err_min_abs", "taem_v_err_final",
            "taem_v_err_min_abs", "taem_s_go_err_final", "taem_s_go_err_min_abs", "height_final",
            "velocity_final", "s_go_final", "bank_angle_final", "attack_angle_final",
        ]:
            row[key] = target_row.get(key)
        row["b2_label"] = _classify(target_row, args.tol_h, args.tol_v, args.tol_sgo)
        b2_rows.append(row)

    by_vehicle = pd.DataFrame(b2_rows).sort_values("vehicle_id")
    by_vehicle_path = report_dir / "phase2_B2_by_vehicle.csv"
    by_vehicle.to_csv(by_vehicle_path, index=False)

    n = len(by_vehicle)
    n_strict = int(by_vehicle["strict_pass"].fillna(False).astype(bool).sum()) if n else 0
    summary = {
        "case": "PHASE2_B2_EXACT_SINGLE_SEQUENTIAL_CLASSIFICATION",
        "combined_csv": str(combined_csv),
        "vehicle_ids": [int(x) for x in args.vehicle_ids],
        "n_vehicles": int(n),
        "n_strict_pass": int(n_strict),
        "strict_pass_rate": float(n_strict / n) if n else None,
        "by_vehicle_csv": str(by_vehicle_path),
        "labels": by_vehicle[["vehicle_id", "decision", "b2_label"]].to_dict(orient="records"),
    }
    summary_path = report_dir / "phase2_B2_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    txt_path = report_dir / "phase2_B2_summary.txt"
    lines = [
        "PHASE 2 / B2 — EXACT-SINGLE SEQUENTIAL CLASSIFICATION",
        "=" * 72,
        f"combined_csv      : {combined_csv}",
        f"n_vehicles        : {n}",
        f"n_strict_pass     : {n_strict}",
        f"strict_pass_rate  : {summary['strict_pass_rate']}",
        "",
        "Vehicle classification:",
    ]
    for _, r in by_vehicle.iterrows():
        lines.append(
            f"  mis{int(r['vehicle_id'])}: decision={r.get('decision')} | label={r.get('b2_label')} | "
            f"end_reason={r.get('end_reason_last')} | dwell={r.get('taem_dwell_s_max_logged')} | "
            f"sgo_min_abs={r.get('taem_s_go_err_min_abs')}"
        )
    lines.extend([
        "",
        "Decision rule:",
        "  - Do not tune during B2. This run is classification only.",
        "  - mis1 should remain PASS_STRICT as the B1E control case.",
        "  - mis0/mis2 labels determine whether B3 uses role-specific recovery or route-layer redesign.",
    ])
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    manifest["by_vehicle_csv"] = str(by_vehicle_path)
    manifest["summary_json"] = str(summary_path)
    manifest["summary_txt"] = str(txt_path)
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n" + txt_path.read_text(encoding="utf-8", errors="replace"))
    print("\n[B2] outputs:")
    print("  -", _rel(combined_csv))
    print("  -", _rel(by_vehicle_path))
    print("  -", _rel(summary_path))
    print("  -", _rel(txt_path))


if __name__ == "__main__":
    main()
