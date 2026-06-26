#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B5C independent local-envelope Monte Carlo validation.

Purpose
-------
B5B-E identified a candidate local envelope from the B5B conservative MC sample:
    h_delta_m   in [0, +500]
    v_delta_mps in [-20, +10]
    heading spread = [-2, 0, +2] deg

B5C validates this candidate with an independent Monte Carlo seed and fresh
exact-single role-distinct runs. This is a local U3 validation test, not a U4
universality claim.

Default:
    N=30 cases, seed=101, 30 cases × 3 vehicles = 90 exact-single runs.
"""

from __future__ import annotations

import argparse
import json
import math
import os
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


def _run(cmd: list[str], cwd: Path, log_path: Path) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as f:
        f.write("COMMAND:\n")
        f.write(" ".join(cmd) + "\n\n")
        f.flush()
        p = subprocess.run(cmd, cwd=str(cwd), stdout=f, stderr=subprocess.STDOUT, text=True, env=env)
        f.write(f"\nRETURN_CODE={p.returncode}\n")
    return int(p.returncode)


def _truth(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    s = str(v).strip().lower()
    if s in {"true", "1", "yes", "y", "t", "pass", "pass_strict"}:
        return True
    try:
        return float(v) > 0.5
    except Exception:
        return False


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="number of independent MC cases; each case runs 3 vehicles")
    ap.add_argument("--seed", type=int, default=101, help="independent validation seed")
    ap.add_argument("--h-min", type=float, default=0.0)
    ap.add_argument("--h-max", type=float, default=500.0)
    ap.add_argument("--v-min", type=float, default=-20.0)
    ap.add_argument("--v-max", type=float, default=10.0)
    ap.add_argument("--heading-spread", type=float, default=2.0)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--b5a-orchestrator", default="phase2_B5A_dispersion_grid_orchestrator.py")
    ap.add_argument("--multiset-source", default="multiset_phase2_B5AR_positive_velocity_specs.py")
    ap.add_argument("--out-root", default="store/data_saved/phase2_B5C_local_envelope_validation")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B5C_local_envelope_validation_report")
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=150.0)
    ap.add_argument("--tol-sgo", type=float, default=30000.0)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--continue-on-fail", action="store_true", help="continue if a subprocess crashes; not for ordinary TAEM failures")
    return ap.parse_args()


def _collect_close_count(df: pd.DataFrame) -> int:
    close_count = 0
    for c in ["last_close_pass_escape", "any_close_pass_escape", "close_pass_escape"]:
        if c in df.columns:
            close_count = max(close_count, int(df[c].map(_truth).sum()))
    return close_count


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    b5a = root / args.b5a_orchestrator
    multiset = root / args.multiset_source
    if not b5a.exists():
        raise FileNotFoundError(f"B5A orchestrator not found: {b5a}")
    if not multiset.exists():
        raise FileNotFoundError(f"multiset source not found: {multiset}")

    rng = np.random.default_rng(int(args.seed))
    samples = []
    for i in range(int(args.n)):
        h = float(rng.uniform(args.h_min, args.h_max))
        v = float(rng.uniform(args.v_min, args.v_max))
        samples.append({"mc_case_index": i, "height_delta_m": h, "velocity_delta_mps": v})

    out_root = root / args.out_root
    run_root = out_root / "case_runs"
    report_root = out_root / "case_reports"
    log_root = out_root / "logs"
    orch_root = out_root / "orchestrator"
    combined_root = out_root / "combined"
    summary_dir = root / args.report_dir
    for p in [out_root, run_root, report_root, log_root, orch_root, combined_root, summary_dir]:
        p.mkdir(parents=True, exist_ok=True)

    manifest = {
        "campaign": "B5C_LOCAL_ENVELOPE_VALIDATION",
        "n_cases": int(args.n),
        "seed": int(args.seed),
        "height_range_m": [float(args.h_min), float(args.h_max)],
        "velocity_range_mps": [float(args.v_min), float(args.v_max)],
        "heading_spread_deg": float(args.heading_spread),
        "started_at": _ts(),
        "samples": samples,
        "runs": [],
    }
    pd.DataFrame(samples).to_csv(summary_dir / "phase2_B5C_samples.csv", index=False)

    all_vehicle_frames: list[pd.DataFrame] = []
    all_case_frames: list[pd.DataFrame] = []
    failed_runs = []

    print(f"[B5C] Independent local-envelope validation N={args.n} seed={args.seed}")
    print(f"[B5C] h_delta=[{args.h_min},{args.h_max}] m, v_delta=[{args.v_min},{args.v_max}] m/s, heading_spread={args.heading_spread} deg")

    for s in samples:
        idx = int(s["mc_case_index"])
        h = float(s["height_delta_m"])
        v = float(s["velocity_delta_mps"])
        case_id = f"b5c{idx:03d}_h{h:+.3f}_v{v:+.3f}".replace("+", "p").replace("-", "m").replace(".", "p")
        case_outdir = orch_root / case_id
        case_run_dir = run_root / case_id
        case_report_dir = report_root / case_id
        case_combined_csv = combined_root / f"{case_id}_combined.csv"
        case_log = log_root / f"{case_id}_b5a_stdout_stderr.txt"
        by_vehicle_path = case_report_dir / "phase2_B5A_by_vehicle_all.csv"
        by_case_path = case_report_dir / "phase2_B5A_by_case.csv"

        if args.resume and by_vehicle_path.exists() and by_case_path.exists():
            print(f"[B5C] resume existing case {idx+1}/{args.n}: {case_id}")
        else:
            cmd = [
                args.python, str(b5a),
                "--height-deltas", f"{h:.9f}",
                "--velocity-deltas", f"{v:.9f}",
                "--heading-spread", f"{float(args.heading_spread):.9f}",
                "--outdir", str(case_outdir),
                "--run-dir", str(case_run_dir),
                "--report-dir", str(case_report_dir),
                "--combined-csv", str(case_combined_csv),
                "--multiset-source", str(multiset),
                "--tol-h", str(args.tol_h),
                "--tol-v", str(args.tol_v),
                "--tol-sgo", str(args.tol_sgo),
                "--python", args.python,
            ]
            print(f"[B5C] running case {idx+1}/{args.n}: h={h:+.3f} m, v={v:+.3f} m/s")
            rc = _run(cmd, root, case_log)
            manifest["runs"].append({"case_id": case_id, "mc_case_index": idx, "h": h, "v": v, "return_code": rc, "log": str(case_log)})
            if rc != 0:
                failed_runs.append({"case_id": case_id, "return_code": rc, "log": str(case_log)})
                print(f"[B5C][ERR] subprocess failed: {case_id}; see {_rel(case_log)}")
                if not args.continue_on_fail:
                    (summary_dir / "phase2_B5C_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise SystemExit(rc)
                continue

        if by_vehicle_path.exists():
            bv = pd.read_csv(by_vehicle_path)
            bv["b5c_case_index"] = idx
            bv["b5c_case_id"] = case_id
            bv["b5c_height_delta_m"] = h
            bv["b5c_velocity_delta_mps"] = v
            bv["b5c_seed"] = int(args.seed)
            all_vehicle_frames.append(bv)
        if by_case_path.exists():
            bc = pd.read_csv(by_case_path)
            bc["b5c_case_index"] = idx
            bc["b5c_case_id"] = case_id
            bc["b5c_height_delta_m"] = h
            bc["b5c_velocity_delta_mps"] = v
            bc["b5c_seed"] = int(args.seed)
            all_case_frames.append(bc)

    if not all_vehicle_frames:
        raise RuntimeError("No by-vehicle outputs were collected; B5C failed before producing results.")

    by_vehicle_all = pd.concat(all_vehicle_frames, ignore_index=True)
    by_case_all = pd.concat(all_case_frames, ignore_index=True) if all_case_frames else pd.DataFrame()

    by_vehicle_csv = summary_dir / "phase2_B5C_by_vehicle_all.csv"
    by_case_csv = summary_dir / "phase2_B5C_by_case_all.csv"
    by_vehicle_all.to_csv(by_vehicle_csv, index=False)
    by_case_all.to_csv(by_case_csv, index=False)

    case_rows = []
    for idx, g in by_vehicle_all.groupby("b5c_case_index"):
        nveh = int(len(g))
        strict_col = "strict_pass" if "strict_pass" in g.columns else "b1_strict_pass"
        npass = int(g[strict_col].map(_truth).sum()) if strict_col in g.columns else 0
        close_count = _collect_close_count(g)
        labels = sorted(set(str(x) for x in g.get("label", pd.Series(dtype=object)).dropna().tolist()))
        case_rows.append({
            "b5c_case_index": int(idx),
            "b5c_case_id": str(g["b5c_case_id"].iloc[0]),
            "height_delta_m": float(g["b5c_height_delta_m"].iloc[0]),
            "velocity_delta_mps": float(g["b5c_velocity_delta_mps"].iloc[0]),
            "n_vehicles": nveh,
            "n_strict_pass": npass,
            "case_pass": bool(npass == nveh and nveh > 0),
            "close_escape_count": close_count,
            "labels": "; ".join(labels),
        })
    case_summary = pd.DataFrame(case_rows).sort_values("b5c_case_index")
    case_summary_csv = summary_dir / "phase2_B5C_case_summary.csv"
    case_summary.to_csv(case_summary_csv, index=False)

    n_cases = int(len(case_summary))
    pass_cases = int(case_summary["case_pass"].sum())
    n_vehicle = int(len(by_vehicle_all))
    strict_col = "strict_pass" if "strict_pass" in by_vehicle_all.columns else "b1_strict_pass"
    pass_vehicle = int(by_vehicle_all[strict_col].map(_truth).sum()) if strict_col in by_vehicle_all.columns else 0
    close_vehicle = _collect_close_count(by_vehicle_all)

    case_ci = _wilson_ci(pass_cases, n_cases)
    veh_ci = _wilson_ci(pass_vehicle, n_vehicle)

    # Marginal by vehicle/role
    marginal_vehicle = []
    veh_col = "mis_id" if "mis_id" in by_vehicle_all.columns else "vehicle_id" if "vehicle_id" in by_vehicle_all.columns else None
    if veh_col:
        for mid, g in by_vehicle_all.groupby(veh_col):
            n = int(len(g))
            k = int(g[strict_col].map(_truth).sum()) if strict_col in g.columns else 0
            marginal_vehicle.append({"vehicle_id": int(mid), "n": n, "pass": k, "rate": k / n if n else float("nan"), "close_escape": _collect_close_count(g)})
    pd.DataFrame(marginal_vehicle).to_csv(summary_dir / "phase2_B5C_by_vehicle_role_summary.csv", index=False)

    # Decision policy for local envelope validation.
    case_rate = pass_cases / max(n_cases, 1)
    veh_rate = pass_vehicle / max(n_vehicle, 1)
    if n_cases > 0 and pass_cases == n_cases and close_vehicle == 0:
        decision = "B5C_LOCAL_ENVELOPE_VALIDATED_PASS_ALL"
    elif case_rate >= 0.80 and veh_rate >= 0.90:
        decision = "B5C_LOCAL_ENVELOPE_SUPPORTED"
    elif case_rate >= 0.60 and veh_rate >= 0.75:
        decision = "B5C_LOCAL_ENVELOPE_PARTIAL_SUPPORT"
    else:
        decision = "B5C_LOCAL_ENVELOPE_FRAGILE"

    lines: list[str] = []
    lines.append("PHASE 2 / B5C — INDEPENDENT LOCAL-ENVELOPE MC VALIDATION")
    lines.append("=" * 72)
    lines.append(f"n_cases             : {n_cases}")
    lines.append(f"seed                : {args.seed}")
    lines.append(f"height_range_m      : [{args.h_min}, {args.h_max}]")
    lines.append(f"velocity_range_mps  : [{args.v_min}, {args.v_max}]")
    lines.append(f"heading_spread_deg  : {args.heading_spread}")
    lines.append(f"overall_decision    : {decision}")
    lines.append(f"case_pass_rate      : {pass_cases}/{n_cases} = {case_rate:.6f}")
    lines.append(f"case_pass_rate_95ci : [{case_ci[0]:.6f}, {case_ci[1]:.6f}]")
    lines.append(f"vehicle_pass_rate   : {pass_vehicle}/{n_vehicle} = {veh_rate:.6f}")
    lines.append(f"vehicle_rate_95ci   : [{veh_ci[0]:.6f}, {veh_ci[1]:.6f}]")
    lines.append(f"close_escape_vehicle_rows: {close_vehicle}/{n_vehicle}")
    lines.append(f"failed_subprocess_cases  : {len(failed_runs)}")
    lines.append("")
    lines.append("[MARGINAL BY VEHICLE]")
    for r in marginal_vehicle:
        lines.append(f"mis{r['vehicle_id']}: pass={r['pass']}/{r['n']} rate={r['rate']:.3f} close_escape={r['close_escape']}")
    lines.append("")
    lines.append("[INTERPRETATION]")
    lines.append("- This is an independent validation of the local envelope extracted from B5B-E, not a broad U4 universality test.")
    lines.append("- A pass supports a local U3 claim inside h_delta=[0,+500] m and v_delta=[-20,+10] m/s.")
    lines.append("- A partial or fragile result means the B5B-E envelope was likely sample-specific and range-closure recovery is needed.")
    lines.append("")
    lines.append("Generated files:")
    for p in [by_vehicle_csv, by_case_csv, case_summary_csv, summary_dir / "phase2_B5C_by_vehicle_role_summary.csv"]:
        lines.append(f"  - {p}")

    summary_txt = summary_dir / "phase2_B5C_summary.txt"
    summary_json = summary_dir / "phase2_B5C_summary.json"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    summary_json.write_text(json.dumps({
        "campaign": "B5C_LOCAL_ENVELOPE_VALIDATION",
        "n_cases": n_cases,
        "seed": args.seed,
        "height_range_m": [args.h_min, args.h_max],
        "velocity_range_mps": [args.v_min, args.v_max],
        "heading_spread_deg": args.heading_spread,
        "overall_decision": decision,
        "case_pass_rate": case_rate,
        "case_pass_rate_95ci": case_ci,
        "vehicle_pass_rate": veh_rate,
        "vehicle_rate_95ci": veh_ci,
        "close_escape_vehicle_rows": close_vehicle,
        "failed_subprocess_cases": failed_runs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (summary_dir / "phase2_B5C_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print("")
    print("[OK] wrote:", _rel(summary_txt))


if __name__ == "__main__":
    main()
