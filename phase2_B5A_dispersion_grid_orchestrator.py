#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B5A deterministic dispersion-grid orchestration.

This is a U3 pre-Monte-Carlo robustness step:
- exact-single sequential runner,
- role-distinct headings [-spread, 0, +spread],
- common initial height and velocity perturbations,
- existing B1/B2R/B3A TAEM checker protocol.

Default grid:
    height_delta_m      = [-500, 0, +500]
    velocity_delta_mps  = [-50, 0, +50]
    heading_spread_deg  = 2
    vehicles            = 0,1,2
Total runs = 9 cases x 3 vehicles = 27 exact-single runs.
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

import numpy as np
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
        backup_path = backup_dir / f"multiset_BACKUP_before_B5A_{_ts()}.py"
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


def _role_meta(spread: float, mid: int) -> dict[str, Any]:
    if mid == 0:
        return {
            "phase2_role": "B5A_MIS0_LEFT_HEADING_PROBE",
            "role_name": "B5A_mis0_left_heading_probe",
            "role_heading_delta_deg": -float(spread),
            "pathspec_name": "B5A_mis0_left_fixed_anchor_probe",
            "psi_bias_deg": -9.0,
            "terminal_alpha_boost_deg": 0.75,
            "policy_family": "mis0_fixed_anchor",
        }
    if mid == 1:
        return {
            "phase2_role": "B5A_MIS1_B1E_CONTROL",
            "role_name": "B5A_mis1_nominal_B1E_control",
            "role_heading_delta_deg": 0.0,
            "pathspec_name": "B5A_mis1_v8_2_validated_nominal",
            "psi_bias_deg": -2.0,
            "terminal_alpha_boost_deg": 2.25,
            "policy_family": "merged_winner_case4_case2",
        }
    return {
        "phase2_role": "B5A_MIS2_RIGHT_HEADING_PROBE",
        "role_name": "B5A_mis2_right_heading_probe",
        "role_heading_delta_deg": float(spread),
        "pathspec_name": "B5A_mis2_right_case2_probe",
        "psi_bias_deg": -0.5,
        "terminal_alpha_boost_deg": 0.25,
        "policy_family": "merged_winner_case4_case2",
    }


def _add_mis_id_and_meta(single_csv: Path, scaffold_csv: Path, mis_id: int, role_meta: dict[str, Any]) -> dict[str, Any]:
    if not single_csv.exists():
        raise FileNotFoundError(f"single-runner CSV not found for mis{mis_id}: {single_csv}")
    df = pd.read_csv(single_csv)
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=["Unnamed: 0"])
    if "mis_id" in df.columns:
        df["mis_id"] = int(mis_id)
    else:
        df.insert(0, "mis_id", int(mis_id))
    for key, val in role_meta.items():
        df[key] = val
    scaffold_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(scaffold_csv, index=False)
    return {"mis_id": int(mis_id), "rows": int(len(df)), "csv": str(scaffold_csv), **role_meta}


def _to_numeric_safe(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype(float)
    if s.dtype == object:
        lower = s.astype(str).str.strip().str.lower()
        mapped = lower.map({"true": 1.0, "false": 0.0, "yes": 1.0, "no": 0.0, "1": 1.0, "0": 0.0})
        numeric = pd.to_numeric(s, errors="coerce")
        return numeric.where(numeric.notna(), mapped).astype(float)
    return pd.to_numeric(s, errors="coerce").astype(float)


def _trajectory_diff_audit(combined: pd.DataFrame, outdir: Path, prefix: str) -> dict[str, Any]:
    dyn_cols = [
        "global_t", "longitude", "latitude", "height", "velocity", "path_angle", "heading_angle",
        "s_go", "delta_psi", "bank_angle", "attack_angle", "E", "taem_h_err", "taem_v_err",
        "taem_s_go_err", "taem_in_box", "taem_reached", "taem_success_latched",
    ]
    dyn_cols = [c for c in dyn_cols if c in combined.columns]
    groups = {int(k): v.reset_index(drop=True) for k, v in combined.groupby("mis_id")}
    mids = sorted(groups.keys())
    rows = []
    lines = [f"PHASE 2 / B5A NUMERIC DIFFERENCE AUDIT — {prefix}", "=" * 72, f"mis_ids: {mids}"]
    any_dynamic_difference = False
    max_dynamic_diff_seen = 0.0
    for i in range(len(mids)):
        for j in range(i + 1, len(mids)):
            a, b = mids[i], mids[j]
            ga, gb = groups[a], groups[b]
            lines.append("")
            lines.append(f"--- mis{a} vs mis{b} ---")
            lines.append(f"same_shape: {ga.shape == gb.shape}")
            for c in dyn_cols:
                xa = _to_numeric_safe(ga[c])
                xb = _to_numeric_safe(gb[c])
                n = min(len(xa), len(xb))
                d = xa.iloc[:n].to_numpy(dtype=float) - xb.iloc[:n].to_numpy(dtype=float)
                finite = np.isfinite(d)
                if finite.any():
                    max_abs = float(np.nanmax(np.abs(d[finite])))
                    mean_abs = float(np.nanmean(np.abs(d[finite])))
                else:
                    max_abs = float("nan")
                    mean_abs = float("nan")
                if c in {"longitude", "latitude", "height", "velocity", "path_angle", "heading_angle", "s_go", "delta_psi", "bank_angle", "attack_angle", "E"}:
                    if np.isfinite(max_abs) and max_abs > 1e-9:
                        any_dynamic_difference = True
                        max_dynamic_diff_seen = max(max_dynamic_diff_seen, max_abs)
                rows.append({"pair": f"mis{a}_vs_mis{b}", "column": c, "max_abs_diff": max_abs, "mean_abs_diff": mean_abs})
                lines.append(f"{c:24s} max_abs_diff={max_abs:.12g} mean_abs_diff={mean_abs:.12g}")
    outdir.mkdir(parents=True, exist_ok=True)
    diff_csv = outdir / f"{prefix}_numeric_diff_by_pair.csv"
    diff_txt = outdir / f"{prefix}_numeric_diff_audit.txt"
    pd.DataFrame(rows).to_csv(diff_csv, index=False)
    diff_txt.write_text("\n".join(lines), encoding="utf-8")
    return {
        "any_dynamic_difference": bool(any_dynamic_difference),
        "max_dynamic_diff_seen": float(max_dynamic_diff_seen),
        "diff_csv": str(diff_csv),
        "diff_txt": str(diff_txt),
    }


def _case_label(h_delta: float, v_delta: float, spread: float) -> str:
    def fmt(x: float, unit: str) -> str:
        s = ("%g" % abs(float(x))).replace(".", "p")
        prefix = "p" if float(x) > 0 else ("m" if float(x) < 0 else "z")
        return f"{prefix}{s}{unit}"
    return f"h{fmt(h_delta, 'm')}_v{fmt(v_delta, 'mps')}_sp{('%g' % spread).replace('.', 'p')}deg"


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="single_mis1_main_v8_2_final_success_flags.py")
    ap.add_argument("--vehicle-ids", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--heading-spread", type=float, default=2.0)
    ap.add_argument("--height-deltas", nargs="*", type=float, default=[-500.0, 0.0, 500.0])
    ap.add_argument("--velocity-deltas", nargs="*", type=float, default=[-50.0, 0.0, 50.0])
    ap.add_argument("--multiset-source", default="multiset_phase2_B5A_dispersion_grid_specs.py")
    ap.add_argument("--no-copy-multiset", action="store_true")
    ap.add_argument("--check-script", default="phase2_B1_mis1_transfer_check.py")
    ap.add_argument("--outdir", default="store/data_saved/phase2_B5A_dispersion_grid_orchestrator")
    ap.add_argument("--run-dir", default="store/data_saved/phase2_B5A_dispersion_grid_runs")
    ap.add_argument("--combined-csv", default="store/data_saved/phase2_B5A_dispersion_grid_combined_all.csv")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B5A_dispersion_grid_report")
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
    combined_all_csv = root / args.combined_csv
    outdir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    runner = root / args.runner
    check_script = root / args.check_script
    multiset_src = root / args.multiset_source
    multiset_dst = root / "multiset.py"
    _require_file(runner, "V8.2 exact single runner")
    _require_file(check_script, "TAEM checker script")

    grid_cases = [(float(h), float(v)) for h in args.height_deltas for v in args.velocity_deltas]

    manifest = {
        "root": str(root),
        "runner": str(runner),
        "vehicle_ids": [int(x) for x in args.vehicle_ids],
        "heading_spread_deg": float(args.heading_spread),
        "height_deltas_m": [float(x) for x in args.height_deltas],
        "velocity_deltas_mps": [float(x) for x in args.velocity_deltas],
        "multiset_source": str(multiset_src),
        "report_dir": str(report_dir),
        "runs": [],
    }

    if not args.no_copy_multiset:
        backup = _copy_multiset(multiset_src, multiset_dst, outdir)
        manifest["copied_multiset"] = True
        manifest["backup_multiset"] = None if backup is None else str(backup)
        print(f"[B5A] copied {_rel(multiset_src)} -> multiset.py")
        if backup:
            print(f"[B5A] backup: {_rel(backup)}")
    else:
        print("[B5A] --no-copy-multiset: using current multiset.py")

    all_frames = []
    all_vehicle_rows = []
    case_rows = []

    for h_delta, v_delta in grid_cases:
        label = _case_label(h_delta, v_delta, args.heading_spread)
        print(f"\n[B5A] === case {label}: h_delta={h_delta:g} m, v_delta={v_delta:g} m/s, spread={args.heading_spread:g} deg ===")
        case_run_dir = run_dir / label
        case_report_dir = report_dir / label
        case_orch_dir = outdir / label
        case_run_dir.mkdir(parents=True, exist_ok=True)
        case_report_dir.mkdir(parents=True, exist_ok=True)
        case_orch_dir.mkdir(parents=True, exist_ok=True)

        env = {
            "B5A_HEADING_SPREAD_DEG": str(float(args.heading_spread)),
            "B5A_HEIGHT_DELTA_M": str(float(h_delta)),
            "B5A_VELOCITY_DELTA_MPS": str(float(v_delta)),
            "B5A_CASE_LABEL": label,
        }

        scaffold_paths = []
        for mid in args.vehicle_ids:
            role_meta = _role_meta(float(args.heading_spread), int(mid))
            role_meta.update({
                "b5a_case_label": label,
                "b5a_height_delta_m": float(h_delta),
                "b5a_velocity_delta_mps": float(v_delta),
                "b5a_heading_spread_deg": float(args.heading_spread),
            })
            single_out = case_run_dir / f"phase2_B5A_{label}_single_runner_mis{mid}.csv"
            scaffold_out = case_run_dir / f"phase2_B5A_{label}_scaffold_mis{mid}.csv"
            log_path = case_orch_dir / f"single_runner_mis{mid}_stdout_stderr.txt"
            for p in [single_out, scaffold_out]:
                if p.exists():
                    p.unlink()
            cmd = [args.python, str(runner), "--mis-index", str(mid), "--out", str(single_out)]
            print(f"[B5A] running {label} mis{mid}...")
            rc = _run(cmd, root, log_path, env=env)
            run_record = {"case_label": label, "height_delta_m": h_delta, "velocity_delta_mps": v_delta, "mis_id": int(mid), "return_code": int(rc), "log": str(log_path), "single_csv": str(single_out)}
            if rc != 0:
                print(f"[B5A][ERR] runner failed for {label} mis{mid}; see {_rel(log_path)}")
                run_record["status"] = "RUN_FAILED"
                manifest["runs"].append(run_record)
                if not args.continue_on_run_fail:
                    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise SystemExit(rc)
                continue
            scaffold_summary = _add_mis_id_and_meta(single_out, scaffold_out, int(mid), role_meta)
            run_record["status"] = "RUN_OK"
            run_record["scaffold_csv"] = str(scaffold_out)
            run_record["scaffold_summary"] = scaffold_summary
            scaffold_paths.append(scaffold_out)
            manifest["runs"].append(run_record)
            print(f"[B5A] wrote scaffold: {_rel(scaffold_out)} rows={scaffold_summary['rows']}")

        if not scaffold_paths:
            case_rows.append({"case_label": label, "height_delta_m": h_delta, "velocity_delta_mps": v_delta, "decision": "B5A_RUN_FAILED", "n_vehicles": 0, "n_strict_pass": 0, "strict_pass_rate": 0.0, "role_distinct_ok": False})
            continue

        frames = [pd.read_csv(p) for p in scaffold_paths]
        combined = pd.concat(frames, ignore_index=True)
        combined["b5a_case_label"] = label
        combined["b5a_height_delta_m"] = float(h_delta)
        combined["b5a_velocity_delta_mps"] = float(v_delta)
        combined["b5a_heading_spread_deg"] = float(args.heading_spread)
        tcol = "global_t" if "global_t" in combined.columns else ("t" if "t" in combined.columns else None)
        if tcol:
            combined = combined.sort_values(["b5a_case_label", "mis_id", tcol], kind="mergesort").reset_index(drop=True)
        case_combined_csv = report_dir / f"phase2_B5A_{label}_combined.csv"
        combined.to_csv(case_combined_csv, index=False)
        all_frames.append(combined)

        check_rows = []
        for mid in args.vehicle_ids:
            vid_report = case_report_dir / f"mis{mid}"
            vid_report.mkdir(parents=True, exist_ok=True)
            cmd = [
                args.python, str(check_script),
                "--csv", str(case_combined_csv),
                "--outdir", str(vid_report),
                "--target-mis-id", str(mid),
                "--tol-h", str(args.tol_h),
                "--tol-v", str(args.tol_v),
                "--tol-sgo", str(args.tol_sgo),
            ]
            log_path = case_orch_dir / f"checker_mis{mid}_stdout_stderr.txt"
            print(f"[B5A] checking {label} mis{mid}...")
            rc = _run(cmd, root, log_path)
            decision_json = vid_report / "phase2_B1_decision.json"
            decision_txt = vid_report / "phase2_B1_decision.txt"
            data = _read_json(decision_json) or {}
            target_row = data.get("target_row", {}) if isinstance(data.get("target_row", {}), dict) else {}
            role_meta = _role_meta(float(args.heading_spread), int(mid))
            row = {
                "case_label": label,
                "height_delta_m": float(h_delta),
                "velocity_delta_mps": float(v_delta),
                "heading_spread_deg": float(args.heading_spread),
                "mis_id": int(mid),
                "checker_return_code": int(rc),
                "checker_log": str(log_path),
                **role_meta,
                "decision": data.get("decision", "CHECK_FAILED" if rc else "UNKNOWN"),
                "strict_pass": bool(data.get("strict_pass", False)),
                "soft_pass": bool(data.get("soft_pass", False)),
                "decision_txt": str(decision_txt) if decision_txt.exists() else None,
            }
            for key in [
                "end_reason_last", "guide_phase_last", "taem_dwell_s_final_logged", "taem_dwell_count_final_logged",
                "taem_h_err_final", "taem_v_err_final", "taem_s_go_err_final", "taem_s_go_err_min_abs",
                "s_go_final", "s_go_min", "height_final", "velocity_final", "delta_psi_final",
                "any_close_pass_escape", "last_close_pass_escape",
            ]:
                row[key] = target_row.get(key)
            row["label"] = _classify(target_row, args.tol_h, args.tol_v, args.tol_sgo)
            check_rows.append(row)
            all_vehicle_rows.append(row)

        by_vehicle = pd.DataFrame(check_rows).sort_values("mis_id")
        by_vehicle_path = case_report_dir / f"phase2_B5A_{label}_by_vehicle.csv"
        by_vehicle.to_csv(by_vehicle_path, index=False)
        diff_summary = _trajectory_diff_audit(combined, case_report_dir, label)

        n = len(by_vehicle)
        n_pass = int(by_vehicle["strict_pass"].astype(bool).sum()) if n else 0
        pass_rate = float(n_pass / n) if n else float("nan")
        role_distinct_ok = bool(diff_summary.get("any_dynamic_difference", False))
        decision = "B5A_CASE_PASS_ROLE_DISTINCT" if (n_pass == n and role_distinct_ok) else ("B5A_CASE_PASS_REPLICATED" if n_pass == n else "B5A_CASE_HAS_FAILURES")
        case_row = {
            "case_label": label,
            "height_delta_m": float(h_delta),
            "velocity_delta_mps": float(v_delta),
            "heading_spread_deg": float(args.heading_spread),
            "n_vehicles": n,
            "n_strict_pass": n_pass,
            "strict_pass_rate": pass_rate,
            "role_distinct_ok": role_distinct_ok,
            "max_dynamic_diff": float(diff_summary.get("max_dynamic_diff_seen", float("nan"))),
            "decision": decision,
            "combined_csv": str(case_combined_csv),
            "by_vehicle_csv": str(by_vehicle_path),
            "diff_txt": diff_summary.get("diff_txt"),
        }
        case_rows.append(case_row)

        case_lines = [
            f"PHASE 2 / B5A — DISPERSION GRID CASE {label}",
            "=" * 72,
            f"decision          : {decision}",
            f"height_delta_m    : {h_delta}",
            f"velocity_delta_mps: {v_delta}",
            f"n_strict_pass     : {n_pass}/{n}",
            f"role_distinct_ok  : {role_distinct_ok}",
            f"max_dynamic_diff  : {diff_summary.get('max_dynamic_diff_seen')}",
            "",
        ]
        for _, r in by_vehicle.iterrows():
            case_lines.append(
                f"mis{int(r['mis_id'])}: decision={r.get('decision')} | role={r.get('phase2_role')} | "
                f"heading_delta={r.get('role_heading_delta_deg')} | end_reason={r.get('end_reason_last')} | "
                f"dwell={r.get('taem_dwell_s_final_logged')} | sgo_min_abs={r.get('taem_s_go_err_min_abs')}"
            )
        (case_report_dir / f"phase2_B5A_{label}_summary.txt").write_text("\n".join(case_lines), encoding="utf-8")
        print("\n".join(case_lines))

    if all_frames:
        combined_all = pd.concat(all_frames, ignore_index=True)
        combined_all.to_csv(combined_all_csv, index=False)

    by_vehicle_all = pd.DataFrame(all_vehicle_rows)
    by_vehicle_all_path = report_dir / "phase2_B5A_by_vehicle_all.csv"
    by_vehicle_all.to_csv(by_vehicle_all_path, index=False)

    by_case = pd.DataFrame(case_rows).sort_values(["height_delta_m", "velocity_delta_mps"])
    by_case_path = report_dir / "phase2_B5A_by_case.csv"
    by_case.to_csv(by_case_path, index=False)

    total_cases = len(by_case)
    pass_cases = int((by_case["decision"] == "B5A_CASE_PASS_ROLE_DISTINCT").sum()) if total_cases else 0
    total_vehicle_runs = len(by_vehicle_all)
    pass_vehicle_runs = int(by_vehicle_all["strict_pass"].astype(bool).sum()) if total_vehicle_runs else 0
    case_ci = _wilson_ci(pass_cases, total_cases)
    veh_ci = _wilson_ci(pass_vehicle_runs, total_vehicle_runs)

    if total_cases > 0 and pass_cases == total_cases:
        overall_decision = "B5A_PASS_ALL_GRID"
    elif total_cases > 0 and pass_cases > 0:
        overall_decision = "B5A_PARTIAL_PASS"
    else:
        overall_decision = "B5A_FAIL_ALL_GRID"

    lines = [
        "PHASE 2 / B5A — DETERMINISTIC DISPERSION GRID",
        "=" * 72,
        f"height_deltas_m    : {[float(x) for x in args.height_deltas]}",
        f"velocity_deltas_mps: {[float(x) for x in args.velocity_deltas]}",
        f"heading_spread_deg : {float(args.heading_spread)}",
        f"n_cases            : {total_cases}",
        f"overall_decision   : {overall_decision}",
        f"case_pass_rate     : {pass_cases}/{total_cases} = {(pass_cases/total_cases if total_cases else float('nan')):.6g}",
        f"case_pass_rate_95ci: [{case_ci[0]:.6g}, {case_ci[1]:.6g}]",
        f"vehicle_pass_rate  : {pass_vehicle_runs}/{total_vehicle_runs} = {(pass_vehicle_runs/total_vehicle_runs if total_vehicle_runs else float('nan')):.6g}",
        f"vehicle_rate_95ci  : [{veh_ci[0]:.6g}, {veh_ci[1]:.6g}]",
        f"combined_all_csv   : {combined_all_csv}",
        "",
        "Case summary:",
    ]
    for _, r in by_case.iterrows():
        lines.append(
            f"  {r['case_label']} | h={r['height_delta_m']:g} m | v={r['velocity_delta_mps']:g} m/s | "
            f"decision={r['decision']} | pass={int(r['n_strict_pass'])}/{int(r['n_vehicles'])} | "
            f"role_distinct_ok={r['role_distinct_ok']} | max_dynamic_diff={r['max_dynamic_diff']}"
        )
    lines.append("")
    lines.append("Interpretation:")
    if overall_decision == "B5A_PASS_ALL_GRID":
        lines.append("  - Role-distinct 3/3 TAEM success is retained for all deterministic height/velocity perturbation cases.")
        lines.append("  - This supports a local U3 robustness claim before Monte Carlo expansion.")
    elif overall_decision == "B5A_PARTIAL_PASS":
        lines.append("  - At least one deterministic perturbation case passed, but failures occur in the tested grid.")
        lines.append("  - Use by-vehicle labels to identify the deterministic robustness boundary before Monte Carlo.")
    else:
        lines.append("  - No deterministic perturbation case achieved 3/3 role-distinct PASS_STRICT.")
        lines.append("  - Revisit role-specific robustness before claiming U3.")

    summary_txt = report_dir / "phase2_B5A_summary.txt"
    summary_json = report_dir / "phase2_B5A_summary.json"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    summary_json.write_text(json.dumps({
        "height_deltas_m": [float(x) for x in args.height_deltas],
        "velocity_deltas_mps": [float(x) for x in args.velocity_deltas],
        "heading_spread_deg": float(args.heading_spread),
        "overall_decision": overall_decision,
        "case_pass_rate": None if total_cases == 0 else pass_cases / total_cases,
        "case_pass_rate_95ci": list(case_ci),
        "vehicle_pass_rate": None if total_vehicle_runs == 0 else pass_vehicle_runs / total_vehicle_runs,
        "vehicle_pass_rate_95ci": list(veh_ci),
        "by_case_csv": str(by_case_path),
        "by_vehicle_all_csv": str(by_vehicle_all_path),
        "combined_all_csv": str(combined_all_csv),
        "manifest": manifest,
        "case_rows": case_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest["overall_decision"] = overall_decision
    manifest["by_case_csv"] = str(by_case_path)
    manifest["by_vehicle_all_csv"] = str(by_vehicle_all_path)
    manifest["summary_txt"] = str(summary_txt)
    manifest["summary_json"] = str(summary_json)
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print(f"[OK] wrote: {_rel(summary_txt)}")
    print(f"[OK] wrote: {_rel(summary_json)}")
    print(f"[OK] wrote: {_rel(by_case_path)}")
    print(f"[OK] wrote: {_rel(by_vehicle_all_path)}")


if __name__ == "__main__":
    main()
