#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B5A-R positive-velocity boundary refinement.

This wrapper reuses the validated B5A deterministic dispersion-grid orchestrator
and runs a finer positive-velocity sweep before Monte Carlo:

    height_delta_m       = [-500, 0, +500]
    velocity_delta_mps   = [+10, +20, +30, +40, +50]
    heading_spread_deg   = 2
    vehicle ids          = 0,1,2

Total = 15 cases x 3 vehicles = 45 exact-single role-distinct runs.

The goal is not to tune guidance. The goal is to locate the positive-velocity
robustness boundary observed in B5A.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd


def _run(cmd: list[str], cwd: Path) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("[B5A-R] running:", " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(cwd), env=env)
    return int(p.returncode)


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * ((phat * (1 - phat) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _make_b5ar_summary(report_dir: Path, out_name: str = "phase2_B5AR_summary") -> None:
    by_case_path = report_dir / "phase2_B5A_by_case.csv"
    by_vehicle_path = report_dir / "phase2_B5A_by_vehicle_all.csv"
    if not by_case_path.exists():
        raise FileNotFoundError(f"B5A by-case output not found: {by_case_path}")
    if not by_vehicle_path.exists():
        raise FileNotFoundError(f"B5A by-vehicle output not found: {by_vehicle_path}")

    by_case = pd.read_csv(by_case_path)
    by_vehicle = pd.read_csv(by_vehicle_path)

    pass_case_col = by_case["decision"].astype(str).eq("B5A_CASE_PASS_ROLE_DISTINCT")
    total_cases = int(len(by_case))
    pass_cases = int(pass_case_col.sum())
    total_vehicle = int(len(by_vehicle))
    pass_vehicle = int(by_vehicle.get("strict_pass", pd.Series(dtype=bool)).astype(bool).sum())
    case_ci = _wilson_ci(pass_cases, total_cases)
    veh_ci = _wilson_ci(pass_vehicle, total_vehicle)

    if total_cases > 0 and pass_cases == total_cases:
        overall = "B5AR_PASS_ALL_POSITIVE_V_GRID"
    elif pass_cases > 0:
        overall = "B5AR_PARTIAL_PASS_POSITIVE_V_GRID"
    else:
        overall = "B5AR_FAIL_POSITIVE_V_GRID"

    lines = [
        "PHASE 2 / B5A-R — POSITIVE-VELOCITY BOUNDARY REFINEMENT",
        "=" * 72,
        f"report_dir          : {report_dir}",
        "height_deltas_m     : [-500, 0, +500]",
        "velocity_deltas_mps : [+10, +20, +30, +40, +50]",
        "heading_spread_deg  : 2",
        f"n_cases             : {total_cases}",
        f"overall_decision    : {overall}",
        f"case_pass_rate      : {pass_cases}/{total_cases} = {pass_cases/total_cases if total_cases else float('nan'):.6f}",
        f"case_pass_rate_95ci : [{case_ci[0]:.6f}, {case_ci[1]:.6f}]",
        f"vehicle_pass_rate   : {pass_vehicle}/{total_vehicle} = {pass_vehicle/total_vehicle if total_vehicle else float('nan'):.6f}",
        f"vehicle_rate_95ci   : [{veh_ci[0]:.6f}, {veh_ci[1]:.6f}]",
        "",
        "Case summary:",
    ]

    sort_cols = [c for c in ["velocity_delta_mps", "height_delta_m"] if c in by_case.columns]
    if sort_cols:
        by_case = by_case.sort_values(sort_cols)
    for _, r in by_case.iterrows():
        lines.append(
            f"  {r.get('case_label')} | h={r.get('height_delta_m'):g} m | v={r.get('velocity_delta_mps'):g} m/s | "
            f"decision={r.get('decision')} | pass={int(r.get('n_strict_pass', 0))}/{int(r.get('n_vehicles', 0))} | "
            f"role_distinct_ok={r.get('role_distinct_ok')} | max_dynamic_diff={r.get('max_dynamic_diff')}"
        )

    # Marginal pass rate by positive velocity value
    lines.append("")
    lines.append("Marginal by velocity_delta_mps:")
    if "velocity_delta_mps" in by_vehicle.columns:
        for v, g in by_vehicle.groupby("velocity_delta_mps"):
            n = int(len(g))
            k = int(g.get("strict_pass", pd.Series(dtype=bool)).astype(bool).sum())
            ci = _wilson_ci(k, n)
            close_col = None
            for cand in ["last_close_pass_escape", "any_close_pass_escape"]:
                if cand in g.columns:
                    close_col = cand
                    break
            if close_col:
                close_count = int(g[close_col].astype(str).str.lower().isin(["true", "1", "yes"]).sum())
            else:
                close_count = 0
            lines.append(f"  v={float(v):+g} m/s | pass={k}/{n} rate={k/n if n else float('nan'):.3f} CI95=[{ci[0]:.3f},{ci[1]:.3f}] | close_escape={close_count}")

    lines.append("")
    lines.append("Interpretation guide:")
    lines.append("  - PASS_ALL means the positive-velocity boundary is above +50 m/s for this grid.")
    lines.append("  - PARTIAL_PASS means the boundary lies inside +10..+50 m/s and should be reported before Monte Carlo.")
    lines.append("  - FAIL means positive velocity perturbations are fragile even at +10 m/s.")

    txt_path = report_dir / f"{out_name}.txt"
    json_path = report_dir / f"{out_name}.json"
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps({
        "overall_decision": overall,
        "n_cases": total_cases,
        "n_pass_cases": pass_cases,
        "case_pass_rate": pass_cases / total_cases if total_cases else None,
        "case_pass_rate_95ci": case_ci,
        "n_vehicle_runs": total_vehicle,
        "n_pass_vehicle_runs": pass_vehicle,
        "vehicle_pass_rate": pass_vehicle / total_vehicle if total_vehicle else None,
        "vehicle_rate_95ci": veh_ci,
        "report_dir": str(report_dir),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[B5A-R] wrote:", txt_path)
    print("[B5A-R] wrote:", json_path)
    print("\n".join(lines))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--b5a-orchestrator", default="phase2_B5A_dispersion_grid_orchestrator.py")
    ap.add_argument("--multiset-source", default="multiset_phase2_B5AR_positive_velocity_specs.py")
    ap.add_argument("--height-deltas", nargs="*", type=float, default=[-500.0, 0.0, 500.0])
    ap.add_argument("--velocity-deltas", nargs="*", type=float, default=[10.0, 20.0, 30.0, 40.0, 50.0])
    ap.add_argument("--heading-spread", type=float, default=2.0)
    ap.add_argument("--python", default=sys.executable)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    b5a = root / args.b5a_orchestrator
    ms = root / args.multiset_source
    if not b5a.exists():
        raise FileNotFoundError(f"B5A orchestrator not found: {b5a}")
    if not ms.exists():
        raise FileNotFoundError(f"B5A-R multiset source not found: {ms}")

    report_dir = Path("store/data_saved/phase2_B5AR_positive_velocity_report")
    cmd = [
        args.python, str(b5a),
        "--heading-spread", str(args.heading_spread),
        "--height-deltas", *[str(x) for x in args.height_deltas],
        "--velocity-deltas", *[str(x) for x in args.velocity_deltas],
        "--multiset-source", str(ms),
        "--outdir", "store/data_saved/phase2_B5AR_positive_velocity_orchestrator",
        "--run-dir", "store/data_saved/phase2_B5AR_positive_velocity_runs",
        "--combined-csv", "store/data_saved/phase2_B5AR_positive_velocity_combined_all.csv",
        "--report-dir", str(report_dir),
    ]
    rc = _run(cmd, root)
    if rc != 0:
        raise SystemExit(rc)

    _make_b5ar_summary(root / report_dir)


if __name__ == "__main__":
    main()
