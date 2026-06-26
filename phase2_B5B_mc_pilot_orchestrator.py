#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B5B Monte Carlo pilot orchestration.

This wrapper reuses the validated B5A exact-single role-distinct orchestrator
for randomly sampled height/velocity perturbation cases.

Default mode is CONSERVATIVE_U3:
    h_delta_m ~ Uniform[-500, +500]
    v_delta_mps ~ Uniform[-50, +10]
    heading spread = [-2, 0, +2] deg

This is intentionally not a broad universality claim. It is a pilot to quantify
whether the role-distinct transfer remains reliable inside the empirically safer
part of the deterministic B5A/B5A-R grid.
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


def _mode_ranges(mode: str) -> tuple[tuple[float, float], tuple[float, float], str]:
    mode = mode.lower().strip()
    if mode in {"conservative", "conservative_u3", "u3"}:
        return (-500.0, 500.0), (-50.0, 10.0), "CONSERVATIVE_U3"
    if mode in {"boundary", "positive_boundary", "fragility"}:
        return (-500.0, 500.0), (20.0, 50.0), "POSITIVE_VELOCITY_BOUNDARY"
    if mode in {"broad", "broad_pm50", "pm50"}:
        return (-500.0, 500.0), (-50.0, 50.0), "BROAD_PM50_DIAGNOSTIC"
    raise ValueError(f"unknown mode: {mode}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="conservative", choices=["conservative", "boundary", "broad"])
    ap.add_argument("--n", type=int, default=30, help="number of random perturbation cases; each case runs 3 vehicles")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--heading-spread", type=float, default=2.0)
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--b5a-orchestrator", default="phase2_B5A_dispersion_grid_orchestrator.py")
    ap.add_argument("--multiset-source", default="multiset_phase2_B5AR_positive_velocity_specs.py")
    ap.add_argument("--out-root", default="store/data_saved/phase2_B5B_mc_pilot")
    ap.add_argument("--tol-h", type=float, default=3000.0)
    ap.add_argument("--tol-v", type=float, default=150.0)
    ap.add_argument("--tol-sgo", type=float, default=30000.0)
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--continue-on-fail", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    b5a = root / args.b5a_orchestrator
    multiset = root / args.multiset_source
    if not b5a.exists():
        raise FileNotFoundError(f"B5A orchestrator not found: {b5a}")
    if not multiset.exists():
        raise FileNotFoundError(f"multiset source not found: {multiset}")

    h_rng, v_rng, mode_label = _mode_ranges(args.mode)
    rng = np.random.default_rng(int(args.seed))
    samples = []
    for i in range(int(args.n)):
        h = float(rng.uniform(h_rng[0], h_rng[1]))
        v = float(rng.uniform(v_rng[0], v_rng[1]))
        samples.append({"mc_case_index": i, "height_delta_m": h, "velocity_delta_mps": v})

    out_root = root / args.out_root / mode_label.lower()
    run_root = out_root / "case_runs"
    report_root = out_root / "case_reports"
    log_root = out_root / "logs"
    summary_dir = root / "store/data_saved" / f"phase2_B5B_mc_{mode_label.lower()}_report"
    for p in [out_root, run_root, report_root, log_root, summary_dir]:
        p.mkdir(parents=True, exist_ok=True)

    manifest = {
        "mode": mode_label,
        "n_cases": int(args.n),
        "seed": int(args.seed),
        "height_range_m": list(h_rng),
        "velocity_range_mps": list(v_rng),
        "heading_spread_deg": float(args.heading_spread),
        "started_at": _ts(),
        "samples": samples,
        "runs": [],
    }
    (summary_dir / "phase2_B5B_mc_samples.csv").write_text(pd.DataFrame(samples).to_csv(index=False), encoding="utf-8")

    all_vehicle_frames: list[pd.DataFrame] = []
    all_case_frames: list[pd.DataFrame] = []
    failed_runs = []

    print(f"[B5B] mode={mode_label} n={args.n} seed={args.seed}")
    print(f"[B5B] h_delta range={h_rng} v_delta range={v_rng} heading_spread={args.heading_spread}")

    for s in samples:
        idx = int(s["mc_case_index"])
        h = float(s["height_delta_m"])
        v = float(s["velocity_delta_mps"])
        case_id = f"mc{idx:03d}_h{h:+.3f}_v{v:+.3f}".replace("+", "p").replace("-", "m").replace(".", "p")
        case_outdir = out_root / "orchestrator" / case_id
        case_run_dir = run_root / case_id
        case_report_dir = report_root / case_id
        case_combined_csv = out_root / "combined" / f"{case_id}_combined.csv"
        case_log = log_root / f"{case_id}_b5a_stdout_stderr.txt"
        by_vehicle_path = case_report_dir / "phase2_B5A_by_vehicle_all.csv"
        by_case_path = case_report_dir / "phase2_B5A_by_case.csv"

        if args.resume and by_vehicle_path.exists() and by_case_path.exists():
            print(f"[B5B] resume existing case {idx+1}/{args.n}: {case_id}")
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
            print(f"[B5B] running case {idx+1}/{args.n}: h={h:+.3f} m, v={v:+.3f} m/s")
            rc = _run(cmd, root, case_log)
            manifest["runs"].append({"case_id": case_id, "mc_case_index": idx, "h": h, "v": v, "return_code": rc, "log": str(case_log)})
            if rc != 0:
                failed_runs.append({"case_id": case_id, "return_code": rc, "log": str(case_log)})
                print(f"[B5B][ERR] case failed: {case_id}; see {_rel(case_log)}")
                if not args.continue_on_fail:
                    (summary_dir / "phase2_B5B_mc_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                    raise SystemExit(rc)
                continue

        if by_vehicle_path.exists():
            bv = pd.read_csv(by_vehicle_path)
            bv["mc_case_index"] = idx
            bv["mc_case_id"] = case_id
            bv["mc_mode"] = mode_label
            bv["mc_height_delta_m"] = h
            bv["mc_velocity_delta_mps"] = v
            all_vehicle_frames.append(bv)
        if by_case_path.exists():
            bc = pd.read_csv(by_case_path)
            bc["mc_case_index"] = idx
            bc["mc_case_id"] = case_id
            bc["mc_mode"] = mode_label
            bc["mc_height_delta_m"] = h
            bc["mc_velocity_delta_mps"] = v
            all_case_frames.append(bc)

    if not all_vehicle_frames:
        raise RuntimeError("No by-vehicle outputs were collected; B5B failed before producing results.")

    by_vehicle_all = pd.concat(all_vehicle_frames, ignore_index=True)
    by_case_all = pd.concat(all_case_frames, ignore_index=True) if all_case_frames else pd.DataFrame()

    by_vehicle_csv = summary_dir / "phase2_B5B_mc_by_vehicle_all.csv"
    by_case_csv = summary_dir / "phase2_B5B_mc_by_case_all.csv"
    by_vehicle_all.to_csv(by_vehicle_csv, index=False)
    by_case_all.to_csv(by_case_csv, index=False)

    # Case-level pass: all 3 vehicles strict-pass in that MC case.
    case_rows = []
    for idx, g in by_vehicle_all.groupby("mc_case_index"):
        nveh = int(len(g))
        npass = int(g.get("strict_pass", pd.Series([False] * nveh)).map(_truth).sum())
        close_count = 0
        for c in ["last_close_pass_escape", "any_close_pass_escape"]:
            if c in g.columns:
                close_count = max(close_count, int(g[c].map(_truth).sum()))
        case_rows.append({
            "mc_case_index": int(idx),
            "mc_case_id": str(g["mc_case_id"].iloc[0]),
            "height_delta_m": float(g["mc_height_delta_m"].iloc[0]),
            "velocity_delta_mps": float(g["mc_velocity_delta_mps"].iloc[0]),
            "n_vehicles": nveh,
            "n_strict_pass": npass,
            "case_pass": bool(npass == nveh and nveh > 0),
            "close_escape_count": close_count,
        })
    mc_case_summary = pd.DataFrame(case_rows).sort_values("mc_case_index")
    mc_case_summary_csv = summary_dir / "phase2_B5B_mc_case_summary.csv"
    mc_case_summary.to_csv(mc_case_summary_csv, index=False)

    n_cases = int(len(mc_case_summary))
    pass_cases = int(mc_case_summary["case_pass"].sum())
    n_vehicle = int(len(by_vehicle_all))
    pass_vehicle = int(by_vehicle_all["strict_pass"].map(_truth).sum()) if "strict_pass" in by_vehicle_all.columns else 0
    close_vehicle = 0
    for c in ["last_close_pass_escape", "any_close_pass_escape"]:
        if c in by_vehicle_all.columns:
            close_vehicle = max(close_vehicle, int(by_vehicle_all[c].map(_truth).sum()))

    case_ci = _wilson_ci(pass_cases, n_cases)
    veh_ci = _wilson_ci(pass_vehicle, n_vehicle)

    # Marginal summaries
    vehicle_rows = []
    if "mis_id" in by_vehicle_all.columns:
        for mid, g in by_vehicle_all.groupby("mis_id"):
            n = len(g)
            k = int(g["strict_pass"].map(_truth).sum()) if "strict_pass" in g.columns else 0
            cclose = 0
            for c in ["last_close_pass_escape", "any_close_pass_escape"]:
                if c in g.columns:
                    cclose = max(cclose, int(g[c].map(_truth).sum()))
            vehicle_rows.append({"mis_id": int(mid), "n": int(n), "pass": k, "rate": k / n if n else float("nan"), "close_escape": cclose})
    pd.DataFrame(vehicle_rows).to_csv(summary_dir / "phase2_B5B_mc_by_vehicle_role_summary.csv", index=False)

    # Decision policy: conservative and honest.
    if n_cases > 0 and pass_cases == n_cases:
        decision = f"B5B_MC_{mode_label}_PASS_ALL_CASES"
    elif mode_label == "CONSERVATIVE_U3" and pass_vehicle / max(n_vehicle, 1) >= 0.80 and pass_cases / max(n_cases, 1) >= 0.60:
        decision = "B5B_MC_CONSERVATIVE_U3_PARTIAL_SUPPORT"
    elif pass_vehicle / max(n_vehicle, 1) >= 0.70:
        decision = f"B5B_MC_{mode_label}_PARTIAL_PASS"
    else:
        decision = f"B5B_MC_{mode_label}_FRAGILE"

    lines = []
    lines.append(f"PHASE 2 / B5B MONTE CARLO PILOT — {mode_label}")
    lines.append("=" * 72)
    lines.append(f"n_cases             : {n_cases}")
    lines.append(f"seed                : {args.seed}")
    lines.append(f"height_range_m      : [{h_rng[0]}, {h_rng[1]}]")
    lines.append(f"velocity_range_mps  : [{v_rng[0]}, {v_rng[1]}]")
    lines.append(f"heading_spread_deg  : {args.heading_spread}")
    lines.append(f"overall_decision    : {decision}")
    lines.append(f"case_pass_rate      : {pass_cases}/{n_cases} = {pass_cases/max(n_cases,1):.6f}")
    lines.append(f"case_pass_rate_95ci : [{case_ci[0]:.6f}, {case_ci[1]:.6f}]")
    lines.append(f"vehicle_pass_rate   : {pass_vehicle}/{n_vehicle} = {pass_vehicle/max(n_vehicle,1):.6f}")
    lines.append(f"vehicle_rate_95ci   : [{veh_ci[0]:.6f}, {veh_ci[1]:.6f}]")
    lines.append(f"close_escape_vehicle_rows: {close_vehicle}/{n_vehicle}")
    lines.append(f"failed_subprocess_cases  : {len(failed_runs)}")
    lines.append("")
    lines.append("[MARGINAL BY VEHICLE]")
    for r in vehicle_rows:
        lines.append(f"mis{r['mis_id']}: pass={r['pass']}/{r['n']} rate={r['rate']:.3f} close_escape={r['close_escape']}")
    lines.append("")
    lines.append("[INTERPRETATION]")
    if mode_label == "CONSERVATIVE_U3":
        lines.append("- This is a conservative U3 Monte Carlo pilot inside the safer velocity sector suggested by B5A/B5A-R.")
        lines.append("- It does not prove full universality; it tests local stochastic robustness under bounded h/v perturbations.")
        lines.append("- A strong U4 claim still requires broader dispersions, atmosphere/aero perturbations, and larger N.")
    elif mode_label == "POSITIVE_VELOCITY_BOUNDARY":
        lines.append("- This is a boundary/frangibility Monte Carlo over the positive-velocity sector.")
        lines.append("- Use it to quantify failure probability and close-pass/range-closure risk near the identified fragile direction.")
    else:
        lines.append("- This broad ±50 m/s diagnostic should not be overclaimed as universality unless pass rates are high and failure modes are controlled.")
    lines.append("")
    lines.append("Generated files:")
    for p in [by_vehicle_csv, by_case_csv, mc_case_summary_csv, summary_dir / "phase2_B5B_mc_by_vehicle_role_summary.csv"]:
        lines.append(f"  - {p}")

    summary_txt = summary_dir / "phase2_B5B_mc_summary.txt"
    summary_json = summary_dir / "phase2_B5B_mc_summary.json"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    summary_json.write_text(json.dumps({
        "mode": mode_label,
        "n_cases": n_cases,
        "seed": args.seed,
        "height_range_m": list(h_rng),
        "velocity_range_mps": list(v_rng),
        "heading_spread_deg": args.heading_spread,
        "overall_decision": decision,
        "case_pass_rate": pass_cases / max(n_cases, 1),
        "case_pass_rate_95ci": case_ci,
        "vehicle_pass_rate": pass_vehicle / max(n_vehicle, 1),
        "vehicle_rate_95ci": veh_ci,
        "close_escape_vehicle_rows": close_vehicle,
        "failed_subprocess_cases": failed_runs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (summary_dir / "phase2_B5B_mc_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print("")
    print("[OK] wrote:", _rel(summary_txt))


if __name__ == "__main__":
    main()
