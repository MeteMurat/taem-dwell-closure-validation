#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B3A heading-spread sensitivity orchestration.

Runs exact-single sequential campaigns for multiple heading-spread values using
multiset_phase2_B3A_heading_spread_specs.py. Each spread produces a 3-vehicle
role-distinct campaign and a TAEM checker report. The script then aggregates
all spreads into a robustness table.
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
        backup_path = backup_dir / f"multiset_BACKUP_before_B3A_{_ts()}.py"
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
            "phase2_role": "B3A_CLASSIFY_MIS0_LEFT_HEADING_PROBE",
            "role_name": "B3A_mis0_left_heading_probe",
            "role_heading_delta_deg": -float(spread),
            "b3a_heading_spread_deg": float(spread),
            "pathspec_name": "B3A_mis0_left_fixed_anchor_probe",
            "psi_bias_deg": -9.0,
            "terminal_alpha_boost_deg": 0.75,
            "policy_family": "mis0_fixed_anchor",
        }
    if mid == 1:
        return {
            "phase2_role": "B3A_REFERENCE_MIS1_B1E_CONTROL",
            "role_name": "B3A_mis1_nominal_B1E_control",
            "role_heading_delta_deg": 0.0,
            "b3a_heading_spread_deg": float(spread),
            "pathspec_name": "B3A_mis1_v8_2_validated_nominal",
            "psi_bias_deg": -2.0,
            "terminal_alpha_boost_deg": 2.25,
            "policy_family": "merged_winner_case4_case2",
        }
    return {
        "phase2_role": "B3A_CLASSIFY_MIS2_RIGHT_HEADING_PROBE",
        "role_name": "B3A_mis2_right_heading_probe",
        "role_heading_delta_deg": float(spread),
        "b3a_heading_spread_deg": float(spread),
        "pathspec_name": "B3A_mis2_right_case2_probe",
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
    lines = []
    lines.append(f"PHASE 2 / B3A NUMERIC DIFFERENCE AUDIT — {prefix}")
    lines.append("=" * 72)
    lines.append(f"mis_ids: {mids}")
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


def _spread_label(spread: float) -> str:
    s = ("%g" % float(spread)).replace("-", "m").replace(".", "p")
    return f"spread_{s}deg"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="single_mis1_main_v8_2_final_success_flags.py")
    ap.add_argument("--vehicle-ids", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--spreads", nargs="*", type=float, default=[1.0, 2.0, 3.0, 4.0])
    ap.add_argument("--multiset-source", default="multiset_phase2_B3A_heading_spread_specs.py")
    ap.add_argument("--no-copy-multiset", action="store_true")
    ap.add_argument("--check-script", default="phase2_B1_mis1_transfer_check.py")
    ap.add_argument("--outdir", default="store/data_saved/phase2_B3A_heading_spread_orchestrator")
    ap.add_argument("--run-dir", default="store/data_saved/phase2_B3A_heading_spread_runs")
    ap.add_argument("--combined-csv", default="store/data_saved/phase2_B3A_heading_spread_combined_all.csv")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B3A_heading_spread_report")
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

    manifest: dict[str, Any] = {
        "root": str(root),
        "runner": str(runner),
        "vehicle_ids": [int(x) for x in args.vehicle_ids],
        "spreads": [float(x) for x in args.spreads],
        "multiset_source": str(multiset_src),
        "report_dir": str(report_dir),
        "runs": [],
    }

    if not args.no_copy_multiset:
        backup = _copy_multiset(multiset_src, multiset_dst, outdir)
        manifest["copied_multiset"] = True
        manifest["backup_multiset"] = None if backup is None else str(backup)
        print(f"[B3A] copied {_rel(multiset_src)} -> multiset.py")
        if backup:
            print(f"[B3A] backup: {_rel(backup)}")
    else:
        print("[B3A] --no-copy-multiset: using current multiset.py")

    all_frames: list[pd.DataFrame] = []
    all_vehicle_rows: list[dict[str, Any]] = []
    spread_rows: list[dict[str, Any]] = []

    for spread in args.spreads:
        label = _spread_label(spread)
        print(f"\n[B3A] === heading spread {spread:g} deg ({label}) ===")
        spread_run_dir = run_dir / label
        spread_report_dir = report_dir / label
        spread_orch_dir = outdir / label
        spread_run_dir.mkdir(parents=True, exist_ok=True)
        spread_report_dir.mkdir(parents=True, exist_ok=True)
        spread_orch_dir.mkdir(parents=True, exist_ok=True)
        env = {"B3A_HEADING_SPREAD_DEG": str(float(spread))}

        scaffold_paths: list[Path] = []
        for mid in args.vehicle_ids:
            role_meta = _role_meta(float(spread), int(mid))
            single_out = spread_run_dir / f"phase2_B3A_{label}_single_runner_mis{mid}.csv"
            scaffold_out = spread_run_dir / f"phase2_B3A_{label}_scaffold_mis{mid}.csv"
            log_path = spread_orch_dir / f"single_runner_mis{mid}_stdout_stderr.txt"
            for p in [single_out, scaffold_out]:
                if p.exists():
                    p.unlink()
            cmd = [args.python, str(runner), "--mis-index", str(mid), "--out", str(single_out)]
            print(f"[B3A] running spread={spread:g} mis{mid}...")
            rc = _run(cmd, root, log_path, env=env)
            run_record: dict[str, Any] = {"spread_deg": float(spread), "mis_id": int(mid), "return_code": int(rc), "log": str(log_path), "single_csv": str(single_out)}
            if rc != 0:
                print(f"[B3A][ERR] runner failed for spread={spread:g} mis{mid}; see {_rel(log_path)}")
                run_record["status"] = "RUN_FAILED"
                manifest["runs"].append(run_record)
                if not args.continue_on_run_fail:
                    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                    raise SystemExit(rc)
                continue
            scaffold_summary = _add_mis_id_and_meta(single_out, scaffold_out, int(mid), role_meta)
            run_record["status"] = "RUN_OK"
            run_record["scaffold_csv"] = str(scaffold_out)
            run_record["scaffold_summary"] = scaffold_summary
            scaffold_paths.append(scaffold_out)
            manifest["runs"].append(run_record)
            print(f"[B3A] wrote scaffold: {_rel(scaffold_out)} rows={scaffold_summary['rows']}")

        if not scaffold_paths:
            spread_rows.append({"spread_deg": float(spread), "decision": "B3A_RUN_FAILED", "n_vehicles": 0, "n_strict_pass": 0, "strict_pass_rate": 0.0, "role_distinct_ok": False})
            continue

        frames = [pd.read_csv(p) for p in scaffold_paths]
        combined = pd.concat(frames, ignore_index=True)
        combined["b3a_heading_spread_deg"] = float(spread)
        tcol = "global_t" if "global_t" in combined.columns else ("t" if "t" in combined.columns else None)
        if tcol:
            combined = combined.sort_values(["b3a_heading_spread_deg", "mis_id", tcol], kind="mergesort").reset_index(drop=True)
        spread_combined_csv = report_dir / f"phase2_B3A_{label}_combined.csv"
        combined.to_csv(spread_combined_csv, index=False)
        all_frames.append(combined)

        check_rows: list[dict[str, Any]] = []
        for mid in args.vehicle_ids:
            vid_report = spread_report_dir / f"mis{mid}"
            vid_report.mkdir(parents=True, exist_ok=True)
            cmd = [
                args.python, str(check_script),
                "--csv", str(spread_combined_csv),
                "--outdir", str(vid_report),
                "--target-mis-id", str(mid),
                "--tol-h", str(args.tol_h),
                "--tol-v", str(args.tol_v),
                "--tol-sgo", str(args.tol_sgo),
            ]
            log_path = spread_orch_dir / f"checker_mis{mid}_stdout_stderr.txt"
            print(f"[B3A] checking spread={spread:g} mis{mid}...")
            rc = _run(cmd, root, log_path)
            decision_json = vid_report / "phase2_B1_decision.json"
            decision_txt = vid_report / "phase2_B1_decision.txt"
            data = _read_json(decision_json) or {}
            target_row = data.get("target_row", {}) if isinstance(data.get("target_row", {}), dict) else {}
            role_meta = _role_meta(float(spread), int(mid))
            row: dict[str, Any] = {
                "spread_deg": float(spread),
                "spread_label": label,
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
        by_vehicle_path = spread_report_dir / f"phase2_B3A_{label}_by_vehicle.csv"
        by_vehicle.to_csv(by_vehicle_path, index=False)
        diff_summary = _trajectory_diff_audit(combined, spread_report_dir, label)

        n = len(by_vehicle)
        n_pass = int(by_vehicle["strict_pass"].astype(bool).sum()) if n else 0
        pass_rate = float(n_pass / n) if n else float("nan")
        role_distinct_ok = bool(diff_summary.get("any_dynamic_difference", False))
        decision = "B3A_SPREAD_PASS_ROLE_DISTINCT" if (n_pass == n and role_distinct_ok) else ("B3A_SPREAD_PASS_REPLICATED" if n_pass == n else "B3A_SPREAD_HAS_FAILURES")
        spread_row = {
            "spread_deg": float(spread),
            "spread_label": label,
            "n_vehicles": n,
            "n_strict_pass": n_pass,
            "strict_pass_rate": pass_rate,
            "role_distinct_ok": role_distinct_ok,
            "max_dynamic_diff": float(diff_summary.get("max_dynamic_diff_seen", float("nan"))),
            "decision": decision,
            "combined_csv": str(spread_combined_csv),
            "by_vehicle_csv": str(by_vehicle_path),
            "diff_txt": diff_summary.get("diff_txt"),
        }
        spread_rows.append(spread_row)

        # Spread-level text summary.
        spread_lines = []
        spread_lines.append(f"PHASE 2 / B3A — HEADING SPREAD {spread:g} DEG")
        spread_lines.append("=" * 72)
        spread_lines.append(f"decision         : {decision}")
        spread_lines.append(f"n_strict_pass    : {n_pass}/{n}")
        spread_lines.append(f"role_distinct_ok : {role_distinct_ok}")
        spread_lines.append(f"max_dynamic_diff : {diff_summary.get('max_dynamic_diff_seen')}")
        spread_lines.append("")
        for _, r in by_vehicle.iterrows():
            spread_lines.append(
                f"mis{int(r['mis_id'])}: decision={r.get('decision')} | role={r.get('phase2_role')} | "
                f"heading_delta={r.get('role_heading_delta_deg')} | end_reason={r.get('end_reason_last')} | "
                f"dwell={r.get('taem_dwell_s_final_logged')} | sgo_min_abs={r.get('taem_s_go_err_min_abs')}"
            )
        (spread_report_dir / f"phase2_B3A_{label}_summary.txt").write_text("\n".join(spread_lines), encoding="utf-8")
        print("\n".join(spread_lines))

    if all_frames:
        combined_all = pd.concat(all_frames, ignore_index=True)
        combined_all.to_csv(combined_all_csv, index=False)
    else:
        combined_all = pd.DataFrame()

    by_vehicle_all = pd.DataFrame(all_vehicle_rows)
    by_vehicle_all_path = report_dir / "phase2_B3A_by_vehicle_all.csv"
    by_vehicle_all.to_csv(by_vehicle_all_path, index=False)

    by_spread = pd.DataFrame(spread_rows).sort_values("spread_deg")
    by_spread_path = report_dir / "phase2_B3A_by_spread.csv"
    by_spread.to_csv(by_spread_path, index=False)

    all_pass_role = len(by_spread) > 0 and bool(((by_spread["decision"] == "B3A_SPREAD_PASS_ROLE_DISTINCT").all()))
    any_pass_role = len(by_spread) > 0 and bool(((by_spread["decision"] == "B3A_SPREAD_PASS_ROLE_DISTINCT").any()))
    overall_decision = "B3A_PASS_ALL_SPREADS" if all_pass_role else ("B3A_PARTIAL_PASS" if any_pass_role else "B3A_FAIL_ALL_SPREADS")

    lines = []
    lines.append("PHASE 2 / B3A — HEADING-SPREAD SENSITIVITY")
    lines.append("=" * 72)
    lines.append(f"spreads          : {[float(x) for x in args.spreads]}")
    lines.append(f"n_spreads        : {len(by_spread)}")
    lines.append(f"overall_decision : {overall_decision}")
    lines.append(f"combined_all_csv : {combined_all_csv}")
    lines.append("")
    lines.append("Spread summary:")
    for _, r in by_spread.iterrows():
        lines.append(
            f"  spread={r['spread_deg']:g} deg | decision={r['decision']} | "
            f"pass={int(r['n_strict_pass'])}/{int(r['n_vehicles'])} | "
            f"role_distinct_ok={r['role_distinct_ok']} | max_dynamic_diff={r['max_dynamic_diff']}"
        )
    lines.append("")
    lines.append("Interpretation:")
    if overall_decision == "B3A_PASS_ALL_SPREADS":
        lines.append("  - Role-distinct 3/3 TAEM success is retained for all tested heading spreads.")
        lines.append("  - This supports a bounded heading-dispersion robustness claim.")
    elif overall_decision == "B3A_PARTIAL_PASS":
        lines.append("  - At least one heading spread passed, but the full tested family did not.")
        lines.append("  - Use by-vehicle labels to identify the robustness boundary.")
    else:
        lines.append("  - No tested heading spread achieved 3/3 role-distinct PASS_STRICT.")
        lines.append("  - Revisit role-specific PathSpec recovery before tolerance/dwell sensitivity.")

    summary_txt = report_dir / "phase2_B3A_summary.txt"
    summary_json = report_dir / "phase2_B3A_summary.json"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    summary_json.write_text(json.dumps({
        "spreads": [float(x) for x in args.spreads],
        "overall_decision": overall_decision,
        "by_spread_csv": str(by_spread_path),
        "by_vehicle_all_csv": str(by_vehicle_all_path),
        "combined_all_csv": str(combined_all_csv),
        "manifest": manifest,
        "spread_rows": spread_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["overall_decision"] = overall_decision
    manifest["by_spread_csv"] = str(by_spread_path)
    manifest["by_vehicle_all_csv"] = str(by_vehicle_all_path)
    manifest["summary_txt"] = str(summary_txt)
    manifest["summary_json"] = str(summary_json)
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print(f"[OK] wrote: {_rel(summary_txt)}")
    print(f"[OK] wrote: {_rel(summary_json)}")
    print(f"[OK] wrote: {_rel(by_spread_path)}")
    print(f"[OK] wrote: {_rel(by_vehicle_all_path)}")


if __name__ == "__main__":
    main()
