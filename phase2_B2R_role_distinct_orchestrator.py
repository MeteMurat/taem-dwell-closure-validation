#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B2R role-distinct exact-single sequential orchestration.

Runs the V8.2 exact single-runner sequentially for mis0/mis1/mis2 using a
role-distinct multiset. It then combines outputs, checks TAEM event success per
vehicle, and performs a built-in integrity audit to verify that the trajectories
are not replicated copies.
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
        backup_path = backup_dir / f"multiset_BACKUP_before_B2R_{_ts()}.py"
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


def _load_role_meta(root: Path) -> dict[int, dict[str, Any]]:
    # Fresh import from current multiset.py after copy.
    import importlib.util
    import sys as _sys

    multiset_path = root / "multiset.py"
    spec = importlib.util.spec_from_file_location("_b2r_current_multiset", multiset_path)
    if spec is None or spec.loader is None:
        return {}
    mod = importlib.util.module_from_spec(spec)
    old = _sys.modules.get("_b2r_current_multiset")
    _sys.modules["_b2r_current_multiset"] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    finally:
        if old is not None:
            _sys.modules["_b2r_current_multiset"] = old
    out: dict[int, dict[str, Any]] = {}
    sp = getattr(mod, "StatusParams", [])
    for i, c in enumerate(sp):
        ps = dict(c.get("PathSpec", {}) or {})
        init = dict(c.get("MissileInitStatus", {}) or {})
        out[int(i)] = {
            "phase2_role": c.get("Phase2Role", ps.get("phase2_role", f"B2R_ROLE_{i}")),
            "role_name": c.get("RoleName", ps.get("role_name", ps.get("name", f"role_{i}"))),
            "role_heading_delta_deg": c.get("RoleHeadingDeltaDeg", ps.get("role_heading_delta_deg")),
            "init_heading_angle": init.get("heading_angle"),
            "pathspec_name": ps.get("name"),
            "psi_bias_deg": ps.get("psi_bias_deg"),
            "terminal_alpha_boost_deg": ps.get("terminal_alpha_boost_deg"),
            "terminal_alpha_boost_enable": ps.get("terminal_alpha_boost_enable"),
            "policy_family": ps.get("policy_family"),
        }
    return out


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

    # Add explicit campaign metadata so audits do not depend on hidden PathSpec behavior.
    for key, val in role_meta.items():
        df[key] = val

    scaffold_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(scaffold_csv, index=False)
    out: dict[str, Any] = {"mis_id": int(mis_id), "rows": int(len(df)), "cols": int(len(df.columns)), "csv": str(scaffold_csv)}
    out.update(role_meta)
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


def _to_numeric_safe(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s.astype(float)
    if s.dtype == object:
        lower = s.astype(str).str.strip().str.lower()
        mapped = lower.map({"true": 1.0, "false": 0.0, "yes": 1.0, "no": 0.0, "1": 1.0, "0": 0.0})
        numeric = pd.to_numeric(s, errors="coerce")
        return numeric.where(numeric.notna(), mapped).astype(float)
    return pd.to_numeric(s, errors="coerce").astype(float)


def _trajectory_diff_audit(combined: pd.DataFrame, outdir: Path) -> dict[str, Any]:
    dyn_cols = [
        "global_t", "longitude", "latitude", "height", "velocity",
        "path_angle", "heading_angle", "s_go", "delta_psi",
        "bank_angle", "attack_angle", "E", "taem_h_err", "taem_v_err", "taem_s_go_err",
        "taem_in_box", "taem_reached", "taem_success_latched",
    ]
    dyn_cols = [c for c in dyn_cols if c in combined.columns]
    groups = {int(k): v.reset_index(drop=True) for k, v in combined.groupby("mis_id")}
    mids = sorted(groups.keys())
    rows = []
    lines = []
    lines.append("PHASE 2 / B2R ROLE-DISTINCT NUMERIC DIFFERENCE AUDIT")
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
                # Dynamic distinction should appear in state/control trajectory columns.
                if c in {"longitude", "latitude", "height", "velocity", "path_angle", "heading_angle", "s_go", "delta_psi", "bank_angle", "attack_angle", "E"}:
                    if np.isfinite(max_abs) and max_abs > 1e-9:
                        any_dynamic_difference = True
                        max_dynamic_diff_seen = max(max_dynamic_diff_seen, max_abs)
                rows.append({"pair": f"mis{a}_vs_mis{b}", "column": c, "max_abs_diff": max_abs, "mean_abs_diff": mean_abs})
                lines.append(f"{c:24s} max_abs_diff={max_abs:.12g} mean_abs_diff={mean_abs:.12g}")

    diff_df = pd.DataFrame(rows)
    diff_df.to_csv(outdir / "phase2_B2R_numeric_diff_by_pair.csv", index=False)
    (outdir / "phase2_B2R_numeric_diff_audit.txt").write_text("\n".join(lines), encoding="utf-8")
    return {
        "any_dynamic_difference": bool(any_dynamic_difference),
        "max_dynamic_diff_seen": float(max_dynamic_diff_seen),
        "diff_csv": str(outdir / "phase2_B2R_numeric_diff_by_pair.csv"),
        "diff_txt": str(outdir / "phase2_B2R_numeric_diff_audit.txt"),
    }


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="single_mis1_main_v8_2_final_success_flags.py")
    ap.add_argument("--vehicle-ids", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--multiset-source", default="multiset_phase2_B2R_role_distinct_heading_specs.py")
    ap.add_argument("--no-copy-multiset", action="store_true")
    ap.add_argument("--check-script", default="phase2_B1_mis1_transfer_check.py")
    ap.add_argument("--outdir", default="store/data_saved/phase2_B2R_role_distinct_orchestrator")
    ap.add_argument("--run-dir", default="store/data_saved/phase2_B2R_role_distinct_runs")
    ap.add_argument("--combined-csv", default="store/data_saved/phase2_B2R_role_distinct_combined.csv")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B2R_role_distinct_report")
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
        print(f"[B2R] copied {_rel(multiset_src)} -> multiset.py")
        if backup:
            print(f"[B2R] backup: {_rel(backup)}")
    else:
        print("[B2R] --no-copy-multiset: using current multiset.py")

    role_meta = _load_role_meta(root)
    manifest["role_meta"] = role_meta

    if combined_csv.exists():
        combined_csv.unlink()

    scaffold_paths: list[Path] = []
    for mid in args.vehicle_ids:
        single_out = run_dir / f"phase2_B2R_exact_single_runner_mis{mid}.csv"
        scaffold_out = run_dir / f"phase2_B2R_exact_single_scaffold_mis{mid}.csv"
        log_path = outdir / f"single_runner_mis{mid}_stdout_stderr.txt"
        for p in [single_out, scaffold_out]:
            if p.exists():
                p.unlink()
        cmd = [args.python, str(runner), "--mis-index", str(mid), "--out", str(single_out)]
        print(f"[B2R] running exact single runner for mis{mid}...")
        print("      " + " ".join(cmd))
        rc = _run(cmd, root, log_path)
        run_record: dict[str, Any] = {"mis_id": int(mid), "return_code": int(rc), "log": str(log_path), "single_csv": str(single_out)}
        if rc != 0:
            print(f"[B2R][ERR] single runner failed for mis{mid}; see {_rel(log_path)}")
            run_record["status"] = "RUN_FAILED"
            manifest["runs"].append(run_record)
            if not args.continue_on_run_fail:
                (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                raise SystemExit(rc)
            continue
        scaffold_summary = _add_mis_id_and_meta(single_out, scaffold_out, mid, role_meta.get(int(mid), {}))
        run_record["status"] = "RUN_OK"
        run_record["scaffold_csv"] = str(scaffold_out)
        run_record["scaffold_summary"] = scaffold_summary
        scaffold_paths.append(scaffold_out)
        manifest["runs"].append(run_record)
        print(f"[B2R] wrote scaffold CSV for mis{mid}: {_rel(scaffold_out)} rows={scaffold_summary['rows']}")

    if not scaffold_paths:
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        raise SystemExit("[B2R][ERR] No successful vehicle CSVs were produced.")

    frames = [pd.read_csv(p) for p in scaffold_paths]
    combined = pd.concat(frames, ignore_index=True)
    if "mis_id" in combined.columns:
        tcol = "global_t" if "global_t" in combined.columns else ("t" if "t" in combined.columns else None)
        if tcol:
            combined = combined.sort_values(["mis_id", tcol], kind="mergesort").reset_index(drop=True)
    combined_csv.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(combined_csv, index=False)
    print(f"[B2R] wrote combined CSV: {_rel(combined_csv)} rows={len(combined)}")

    # Per-vehicle checker.
    check_rows: list[dict[str, Any]] = []
    for mid in args.vehicle_ids:
        vid_report = report_dir / f"mis{mid}"
        vid_report.mkdir(parents=True, exist_ok=True)
        cmd = [
            args.python, str(check_script),
            "--csv", str(combined_csv),
            "--outdir", str(vid_report),
            "--target-mis-id", str(mid),
            "--tol-h", str(args.tol_h),
            "--tol-v", str(args.tol_v),
            "--tol-sgo", str(args.tol_sgo),
        ]
        log_path = outdir / f"checker_mis{mid}_stdout_stderr.txt"
        print(f"[B2R] checking mis{mid}...")
        rc = _run(cmd, root, log_path)
        decision_json = vid_report / "phase2_B1_decision.json"
        decision_txt = vid_report / "phase2_B1_decision.txt"
        data = _read_json(decision_json) or {}
        target_row = data.get("target_row", {}) if isinstance(data.get("target_row", {}), dict) else {}
        row: dict[str, Any] = {"mis_id": int(mid), "checker_return_code": int(rc), "checker_log": str(log_path)}
        row.update(role_meta.get(int(mid), {}))
        row.update({
            "decision": data.get("decision", "CHECK_FAILED" if rc else "UNKNOWN"),
            "strict_pass": bool(data.get("strict_pass", False)),
            "soft_pass": bool(data.get("soft_pass", False)),
            "decision_txt": str(decision_txt) if decision_txt.exists() else None,
        })
        for key in [
            "end_reason_last", "guide_phase_last", "taem_dwell_s_final_logged", "taem_dwell_count_final_logged",
            "taem_h_err_final", "taem_v_err_final", "taem_s_go_err_final", "taem_s_go_err_min_abs",
            "s_go_final", "s_go_min", "height_final", "velocity_final", "delta_psi_final",
            "any_close_pass_escape", "last_close_pass_escape",
        ]:
            row[key] = target_row.get(key)
        row["label"] = _classify(target_row, args.tol_h, args.tol_v, args.tol_sgo)
        check_rows.append(row)

    by_vehicle = pd.DataFrame(check_rows).sort_values("mis_id")
    by_vehicle_path = report_dir / "phase2_B2R_by_vehicle.csv"
    by_vehicle.to_csv(by_vehicle_path, index=False)

    diff_summary = _trajectory_diff_audit(combined, report_dir)

    n = len(by_vehicle)
    n_pass = int(by_vehicle["strict_pass"].astype(bool).sum()) if n else 0
    pass_rate = float(n_pass / n) if n else float("nan")
    role_distinct_ok = bool(diff_summary.get("any_dynamic_difference", False))
    decision = "B2R_PASS_ROLE_DISTINCT" if (n_pass == n and role_distinct_ok) else ("B2R_PASS_REPLICATED" if n_pass == n else "B2R_CLASSIFICATION_HAS_FAILURES")

    lines = []
    lines.append("PHASE 2 / B2R — ROLE-DISTINCT EXACT-SINGLE CLASSIFICATION")
    lines.append("=" * 72)
    lines.append(f"combined_csv       : {combined_csv}")
    lines.append(f"n_vehicles         : {n}")
    lines.append(f"n_strict_pass      : {n_pass}")
    lines.append(f"strict_pass_rate   : {pass_rate}")
    lines.append(f"role_distinct_ok   : {role_distinct_ok}")
    lines.append(f"max_dynamic_diff   : {diff_summary.get('max_dynamic_diff_seen')}")
    lines.append(f"decision           : {decision}")
    lines.append("")
    lines.append("Vehicle classification:")
    for _, r in by_vehicle.iterrows():
        lines.append(
            f"  mis{int(r['mis_id'])}: decision={r.get('decision')} | label={r.get('label')} | "
            f"role={r.get('phase2_role')} | heading_delta={r.get('role_heading_delta_deg')} | "
            f"end_reason={r.get('end_reason_last')} | dwell={r.get('taem_dwell_s_final_logged')} | "
            f"sgo_min_abs={r.get('taem_s_go_err_min_abs')}"
        )
    lines.append("")
    lines.append("Interpretation:")
    if decision == "B2R_PASS_ROLE_DISTINCT":
        lines.append("  - B2R produced 3/3 PASS_STRICT with dynamically distinct trajectories.")
        lines.append("  - This can be treated as the first role-distinct exact-single multi-vehicle transfer result.")
    elif decision == "B2R_PASS_REPLICATED":
        lines.append("  - All vehicles passed, but dynamic trajectories still look replicated.")
        lines.append("  - Do not claim role-specific transfer; inspect single runner case selection and PathSpec use.")
    else:
        lines.append("  - At least one vehicle failed. Use labels to decide role-specific recovery; do not tune inside B2R.")

    summary_txt = report_dir / "phase2_B2R_summary.txt"
    summary_json = report_dir / "phase2_B2R_summary.json"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    summary_json.write_text(json.dumps({
        "combined_csv": str(combined_csv),
        "n_vehicles": n,
        "n_strict_pass": n_pass,
        "strict_pass_rate": pass_rate,
        "role_distinct_ok": role_distinct_ok,
        "max_dynamic_diff_seen": diff_summary.get("max_dynamic_diff_seen"),
        "decision": decision,
        "by_vehicle_csv": str(by_vehicle_path),
        "diff_summary": diff_summary,
        "manifest": manifest,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest["by_vehicle_csv"] = str(by_vehicle_path)
    manifest["summary_txt"] = str(summary_txt)
    manifest["summary_json"] = str(summary_json)
    manifest["diff_summary"] = diff_summary
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print(f"[OK] wrote: {_rel(by_vehicle_path)}")
    print(f"[OK] wrote: {_rel(summary_txt)}")
    print(f"[OK] wrote: {_rel(summary_json)}")
    print(f"[OK] wrote: {_rel(Path(diff_summary['diff_txt']))}")


if __name__ == "__main__":
    main()
