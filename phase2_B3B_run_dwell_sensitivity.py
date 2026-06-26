#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 / B3B-run dwell sensitivity.

Purpose
-------
B3B-post showed that N=4/5 dwell cannot be concluded from CSVs that terminate at
N=3. This script runs a true exact-single sequential campaign while preventing
the V8.2 guidance from ending at the default dwell=3 event until the requested
minimum dwell has been reached.

Mechanism
---------
The single runner first tries to import a root-level module named
multiMissileGuideInstance_mis1_state_first_v8_2_final_success_flags.py before
falling back to guidance/. For each dwell requirement, this script creates a
root-level shadow module that subclasses the original guidance class from
 guidance/ and suppresses premature taem_dwell_reached termination until
B3B_DWELL_REQ_S / B3B_DWELL_REQ_COUNT is satisfied.

This does NOT change the guidance law; it only raises the event latch/end
requirement for the B3B robustness campaign.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MODULE_STEM = "multiMissileGuideInstance_mis1_state_first_v8_2_final_success_flags"


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
        run_env.update({str(k): str(v) for k, v in env.items()})
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
        backup_path = backup_dir / f"multiset_BACKUP_before_B3B_run_{_ts()}.py"
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


def _float_or_nan(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return float("nan")


def _safe_label(x: float) -> str:
    return ("%g" % float(x)).replace("-", "m").replace(".", "p")


def _role_meta(mid: int, dwell_req: float, spread: float) -> dict[str, Any]:
    # Same role family as B2R/B3A spread=2 deg; spread can be overridden.
    if mid == 0:
        return {
            "phase2_role": "B3B_DWELL_MIS0_LEFT_HEADING_PROBE",
            "role_name": "B3B_mis0_left_heading_probe",
            "role_heading_delta_deg": -float(spread),
            "b3b_heading_spread_deg": float(spread),
            "b3b_dwell_req_s": float(dwell_req),
            "pathspec_name": "B3B_mis0_left_fixed_anchor_probe",
            "psi_bias_deg": -9.0,
            "terminal_alpha_boost_deg": 0.75,
            "policy_family": "mis0_fixed_anchor",
        }
    if mid == 1:
        return {
            "phase2_role": "B3B_DWELL_REFERENCE_MIS1_B1E_CONTROL",
            "role_name": "B3B_mis1_nominal_B1E_control",
            "role_heading_delta_deg": 0.0,
            "b3b_heading_spread_deg": float(spread),
            "b3b_dwell_req_s": float(dwell_req),
            "pathspec_name": "B3B_mis1_v8_2_validated_nominal",
            "psi_bias_deg": -2.0,
            "terminal_alpha_boost_deg": 2.25,
            "policy_family": "merged_winner_case4_case2",
        }
    return {
        "phase2_role": "B3B_DWELL_MIS2_RIGHT_HEADING_PROBE",
        "role_name": "B3B_mis2_right_heading_probe",
        "role_heading_delta_deg": float(spread),
        "b3b_heading_spread_deg": float(spread),
        "b3b_dwell_req_s": float(dwell_req),
        "pathspec_name": "B3B_mis2_right_case2_probe",
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
    rows: list[dict[str, Any]] = []
    lines: list[str] = []
    lines.append(f"PHASE 2 / B3B NUMERIC DIFFERENCE AUDIT — {prefix}")
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


def _create_guidance_shadow(root: Path, dwell_req: float, backup_dir: Path) -> dict[str, Any]:
    shadow = root / f"{MODULE_STEM}.py"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = None
    if shadow.exists():
        backup = backup_dir / f"{MODULE_STEM}_BACKUP_before_B3B_{_ts()}.py"
        shutil.copy2(shadow, backup)
        shadow.unlink()
    code = f'''# -*- coding: utf-8 -*-
"""Auto-generated B3B dwell-threshold shadow wrapper.
Do not edit manually. Generated by phase2_B3B_run_dwell_sensitivity.py.
"""
from __future__ import annotations
import os
import math
from guidance.{MODULE_STEM} import *  # noqa
from guidance.{MODULE_STEM} import Mis1StateFirstGuidanceV8Final as _BaseV8Final
try:
    from guidance.{MODULE_STEM} import Mis1StateFirstGuidance as _BaseAlias
except Exception:
    _BaseAlias = _BaseV8Final


def _float_env(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)


class _B3BDwellMixin:
    def _b3b_req_s(self):
        return _float_env("B3B_DWELL_REQ_S", "{float(dwell_req)}")

    def _b3b_req_count(self):
        return int(math.ceil(_float_env("B3B_DWELL_REQ_COUNT", str(self._b3b_req_s()))))

    def _b3b_current_dwell(self, mis):
        g = getattr(mis, "guide", {{}})
        dwell_s = _safe_float(g.get("taem_dwell_s", g.get("taem_dwell_time_s", 0.0)), 0.0)
        dwell_count = _safe_float(g.get("taem_dwell_count", g.get("taem_dwell_steps", 0.0)), 0.0)
        return dwell_s, dwell_count

    def _b3b_clear_early_dwell_end(self, mis):
        g = getattr(mis, "guide", {{}})
        dwell_s, dwell_count = self._b3b_current_dwell(mis)
        req_s = self._b3b_req_s()
        req_count = self._b3b_req_count()
        end_reason = str(g.get("end_reason", ""))
        looks_like_dwell_end = (
            end_reason == "taem_dwell_reached" or
            bool(g.get("taem_success_latched", False)) or
            bool(g.get("taem_reached", False)) or
            bool(g.get("taem_reached_ever", False))
        )
        enough = (dwell_s + 1e-9 >= req_s) or (dwell_count + 1e-9 >= req_count)
        if looks_like_dwell_end and not enough:
            # Suppress only premature dwell-success termination. Keep trajectory running.
            try:
                self.end_flag = False
            except Exception:
                pass
            g["end_guide"] = False
            g["guide_process"] = True
            g["end_reason"] = "b3b_waiting_for_higher_dwell"
            g["b3b_waiting_for_higher_dwell"] = True
            g["b3b_dwell_req_s"] = req_s
            g["b3b_dwell_req_count"] = req_count
            return True
        g["b3b_dwell_req_s"] = req_s
        g["b3b_dwell_req_count"] = req_count
        g["b3b_waiting_for_higher_dwell"] = False
        return False

    def guide(self, mis, tar=None, meta={{}}):
        out = super().guide(mis, tar, meta)
        self._b3b_clear_early_dwell_end(mis)
        return out

    def end_guide(self, mis=None, tar=None, meta={{}}, flag=False):
        out = super().end_guide(mis, tar, meta, flag=flag)
        if mis is not None and self._b3b_clear_early_dwell_end(mis):
            return False
        return out


class Mis1StateFirstGuidanceV8Final(_B3BDwellMixin, _BaseV8Final):
    pass


class Mis1StateFirstGuidance(_B3BDwellMixin, _BaseAlias):
    pass
'''
    shadow.write_text(code, encoding="utf-8")
    return {"shadow": str(shadow), "backup": None if backup is None else str(backup), "dwell_req": float(dwell_req)}


def _restore_guidance_shadow(root: Path, shadow_info: dict[str, Any]) -> None:
    shadow = Path(shadow_info["shadow"])
    backup = shadow_info.get("backup")
    if shadow.exists():
        shadow.unlink()
    if backup:
        shutil.copy2(Path(backup), shadow)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="single_mis1_main_v8_2_final_success_flags.py")
    ap.add_argument("--vehicle-ids", nargs="*", type=int, default=[0, 1, 2])
    ap.add_argument("--dwell-reqs", nargs="*", type=float, default=[3.0, 4.0, 5.0])
    ap.add_argument("--heading-spread", type=float, default=2.0, help="Role-distinct spread used for B3B-run; default reproduces B2R.")
    ap.add_argument("--multiset-source", default="multiset_phase2_B3B_dwell_specs.py")
    ap.add_argument("--no-copy-multiset", action="store_true")
    ap.add_argument("--keep-shadow", action="store_true", help="Leave root-level guidance shadow file for debugging.")
    ap.add_argument("--check-script", default="phase2_B1_mis1_transfer_check.py")
    ap.add_argument("--outdir", default="store/data_saved/phase2_B3B_run_dwell_orchestrator")
    ap.add_argument("--run-dir", default="store/data_saved/phase2_B3B_run_dwell_runs")
    ap.add_argument("--combined-csv", default="store/data_saved/phase2_B3B_run_dwell_combined_all.csv")
    ap.add_argument("--report-dir", default="store/data_saved/phase2_B3B_run_dwell_report")
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
    original_guidance = root / "guidance" / f"{MODULE_STEM}.py"
    _require_file(runner, "V8.2 exact single runner")
    _require_file(check_script, "TAEM checker script")
    _require_file(original_guidance, "original V8.2 guidance module")

    manifest: dict[str, Any] = {
        "root": str(root),
        "runner": str(runner),
        "vehicle_ids": [int(x) for x in args.vehicle_ids],
        "dwell_reqs": [float(x) for x in args.dwell_reqs],
        "heading_spread": float(args.heading_spread),
        "multiset_source": str(multiset_src),
        "report_dir": str(report_dir),
        "runs": [],
    }

    if not args.no_copy_multiset:
        backup = _copy_multiset(multiset_src, multiset_dst, outdir)
        manifest["copied_multiset"] = True
        manifest["backup_multiset"] = None if backup is None else str(backup)
        print(f"[B3B-run] copied {_rel(multiset_src)} -> multiset.py")
        if backup:
            print(f"[B3B-run] backup: {_rel(backup)}")
    else:
        print("[B3B-run] --no-copy-multiset: using current multiset.py")

    all_frames: list[pd.DataFrame] = []
    all_vehicle_rows: list[dict[str, Any]] = []
    dwell_rows: list[dict[str, Any]] = []

    for dwell_req in args.dwell_reqs:
        dwell_label = f"dwell_{_safe_label(dwell_req)}"
        print(f"\n[B3B-run] === dwell requirement {dwell_req:g} ({dwell_label}) ===")
        shadow_info = _create_guidance_shadow(root, float(dwell_req), outdir / dwell_label)
        manifest.setdefault("shadow_modules", []).append(shadow_info)

        dwell_run_dir = run_dir / dwell_label
        dwell_report_dir = report_dir / dwell_label
        dwell_orch_dir = outdir / dwell_label
        dwell_run_dir.mkdir(parents=True, exist_ok=True)
        dwell_report_dir.mkdir(parents=True, exist_ok=True)
        dwell_orch_dir.mkdir(parents=True, exist_ok=True)
        env = {
            "B3B_DWELL_REQ_S": str(float(dwell_req)),
            "B3B_DWELL_REQ_COUNT": str(int(math.ceil(float(dwell_req)))),
            "B3B_HEADING_SPREAD_DEG": str(float(args.heading_spread)),
            # The B3B multiset is compatible with the B3A variable too.
            "B3A_HEADING_SPREAD_DEG": str(float(args.heading_spread)),
        }

        scaffold_paths: list[Path] = []
        try:
            for mid in args.vehicle_ids:
                role_meta = _role_meta(int(mid), float(dwell_req), float(args.heading_spread))
                single_out = dwell_run_dir / f"phase2_B3B_{dwell_label}_single_runner_mis{mid}.csv"
                scaffold_out = dwell_run_dir / f"phase2_B3B_{dwell_label}_scaffold_mis{mid}.csv"
                log_path = dwell_orch_dir / f"single_runner_mis{mid}_stdout_stderr.txt"
                for p in [single_out, scaffold_out]:
                    if p.exists():
                        p.unlink()
                cmd = [args.python, str(runner), "--mis-index", str(mid), "--out", str(single_out)]
                print(f"[B3B-run] running dwell={dwell_req:g} mis{mid}...")
                rc = _run(cmd, root, log_path, env=env)
                run_record: dict[str, Any] = {"dwell_req": float(dwell_req), "mis_id": int(mid), "return_code": int(rc), "log": str(log_path), "single_csv": str(single_out)}
                if rc != 0:
                    print(f"[B3B-run][ERR] runner failed for dwell={dwell_req:g} mis{mid}; see {_rel(log_path)}")
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
                print(f"[B3B-run] wrote scaffold: {_rel(scaffold_out)} rows={scaffold_summary['rows']}")
        finally:
            if not args.keep_shadow:
                _restore_guidance_shadow(root, shadow_info)

        if not scaffold_paths:
            dwell_rows.append({"dwell_req": float(dwell_req), "decision": "B3B_RUN_FAILED", "n_vehicles": 0, "n_strict_pass": 0, "strict_pass_rate": 0.0, "role_distinct_ok": False})
            continue

        frames = [pd.read_csv(p) for p in scaffold_paths]
        combined = pd.concat(frames, ignore_index=True)
        combined["b3b_dwell_req_s"] = float(dwell_req)
        combined["b3b_heading_spread_deg"] = float(args.heading_spread)
        tcol = "global_t" if "global_t" in combined.columns else ("t" if "t" in combined.columns else None)
        if tcol:
            combined = combined.sort_values(["b3b_dwell_req_s", "mis_id", tcol], kind="mergesort").reset_index(drop=True)
        dwell_combined_csv = report_dir / f"phase2_B3B_{dwell_label}_combined.csv"
        combined.to_csv(dwell_combined_csv, index=False)
        all_frames.append(combined)

        check_rows: list[dict[str, Any]] = []
        for mid in args.vehicle_ids:
            vid_report = dwell_report_dir / f"mis{mid}"
            vid_report.mkdir(parents=True, exist_ok=True)
            cmd = [
                args.python, str(check_script),
                "--csv", str(dwell_combined_csv),
                "--outdir", str(vid_report),
                "--target-mis-id", str(mid),
                "--tol-h", str(args.tol_h),
                "--tol-v", str(args.tol_v),
                "--tol-sgo", str(args.tol_sgo),
            ]
            log_path = dwell_orch_dir / f"checker_mis{mid}_stdout_stderr.txt"
            print(f"[B3B-run] checking dwell={dwell_req:g} mis{mid}...")
            rc = _run(cmd, root, log_path)
            decision_json = vid_report / "phase2_B1_decision.json"
            decision_txt = vid_report / "phase2_B1_decision.txt"
            data = _read_json(decision_json) or {}
            target_row = data.get("target_row", {}) if isinstance(data.get("target_row", {}), dict) else {}
            role_meta = _role_meta(int(mid), float(dwell_req), float(args.heading_spread))
            dwell_s_final = _float_or_nan(target_row.get("taem_dwell_s_final_logged", target_row.get("taem_dwell_time_s_final_logged")))
            dwell_count_final = _float_or_nan(target_row.get("taem_dwell_count_final_logged", target_row.get("taem_dwell_steps_final_logged")))
            meets_dwell = (np.isfinite(dwell_s_final) and dwell_s_final + 1e-9 >= float(dwell_req)) or (np.isfinite(dwell_count_final) and dwell_count_final + 1e-9 >= math.ceil(float(dwell_req)))
            base_strict = bool(data.get("strict_pass", False))
            strict_with_req = bool(base_strict and meets_dwell)
            row: dict[str, Any] = {
                "dwell_req": float(dwell_req),
                "dwell_label": dwell_label,
                "mis_id": int(mid),
                "checker_return_code": int(rc),
                "checker_log": str(log_path),
                **role_meta,
                "decision": data.get("decision", "CHECK_FAILED" if rc else "UNKNOWN"),
                "strict_pass_base_checker": base_strict,
                "strict_pass_with_dwell_req": strict_with_req,
                "meets_dwell_req": bool(meets_dwell),
                "decision_txt": str(decision_txt) if decision_txt.exists() else None,
            }
            for key in [
                "end_reason_last", "guide_phase_last", "taem_dwell_s_final_logged", "taem_dwell_count_final_logged",
                "taem_h_err_final", "taem_v_err_final", "taem_s_go_err_final", "taem_s_go_err_min_abs",
                "s_go_final", "s_go_min", "height_final", "velocity_final", "delta_psi_final",
                "any_close_pass_escape", "last_close_pass_escape",
            ]:
                row[key] = target_row.get(key)
            check_rows.append(row)
            all_vehicle_rows.append(row)

        by_vehicle = pd.DataFrame(check_rows).sort_values("mis_id")
        by_vehicle_path = dwell_report_dir / f"phase2_B3B_{dwell_label}_by_vehicle.csv"
        by_vehicle.to_csv(by_vehicle_path, index=False)
        diff_summary = _trajectory_diff_audit(combined, dwell_report_dir, dwell_label)

        n = len(by_vehicle)
        n_pass = int(by_vehicle["strict_pass_with_dwell_req"].astype(bool).sum()) if n else 0
        pass_rate = float(n_pass / n) if n else float("nan")
        role_distinct_ok = bool(diff_summary.get("any_dynamic_difference", False))
        decision = "B3B_DWELL_PASS_ROLE_DISTINCT" if (n_pass == n and role_distinct_ok) else ("B3B_DWELL_PASS_REPLICATED" if n_pass == n else "B3B_DWELL_HAS_FAILURES")
        dwell_row = {
            "dwell_req": float(dwell_req),
            "dwell_label": dwell_label,
            "n_vehicles": n,
            "n_strict_pass": n_pass,
            "strict_pass_rate": pass_rate,
            "role_distinct_ok": role_distinct_ok,
            "max_dynamic_diff": float(diff_summary.get("max_dynamic_diff_seen", float("nan"))),
            "decision": decision,
            "combined_csv": str(dwell_combined_csv),
            "by_vehicle_csv": str(by_vehicle_path),
            "diff_txt": diff_summary.get("diff_txt"),
        }
        dwell_rows.append(dwell_row)

        dwell_lines = []
        dwell_lines.append(f"PHASE 2 / B3B-run — DWELL REQUIREMENT {dwell_req:g}")
        dwell_lines.append("=" * 72)
        dwell_lines.append(f"decision         : {decision}")
        dwell_lines.append(f"n_vehicles       : {n}")
        dwell_lines.append(f"n_strict_pass    : {n_pass}")
        dwell_lines.append(f"role_distinct_ok : {role_distinct_ok}")
        dwell_lines.append(f"max_dynamic_diff : {diff_summary.get('max_dynamic_diff_seen')}")
        dwell_lines.append("")
        for _, r in by_vehicle.iterrows():
            dwell_lines.append(
                f"mis{int(r['mis_id'])}: strict_req={r.get('strict_pass_with_dwell_req')} | role={r.get('phase2_role')} | "
                f"heading_delta={r.get('role_heading_delta_deg')} | end_reason={r.get('end_reason_last')} | "
                f"dwell_s={r.get('taem_dwell_s_final_logged')} | dwell_count={r.get('taem_dwell_count_final_logged')} | "
                f"sgo_min_abs={r.get('taem_s_go_err_min_abs')}"
            )
        (dwell_report_dir / f"phase2_B3B_{dwell_label}_summary.txt").write_text("\n".join(dwell_lines), encoding="utf-8")
        print("\n".join(dwell_lines))

    if all_frames:
        combined_all = pd.concat(all_frames, ignore_index=True)
        combined_all.to_csv(combined_all_csv, index=False)
    else:
        combined_all = pd.DataFrame()

    by_vehicle_all = pd.DataFrame(all_vehicle_rows)
    by_vehicle_all_path = report_dir / "phase2_B3B_run_by_vehicle_all.csv"
    by_vehicle_all.to_csv(by_vehicle_all_path, index=False)

    by_dwell = pd.DataFrame(dwell_rows).sort_values("dwell_req")
    by_dwell_path = report_dir / "phase2_B3B_run_by_dwell.csv"
    by_dwell.to_csv(by_dwell_path, index=False)

    all_pass_role = len(by_dwell) > 0 and bool((by_dwell["decision"] == "B3B_DWELL_PASS_ROLE_DISTINCT").all())
    any_pass_role = len(by_dwell) > 0 and bool((by_dwell["decision"] == "B3B_DWELL_PASS_ROLE_DISTINCT").any())
    overall_decision = "B3B_RUN_PASS_ALL_DWELL_REQS" if all_pass_role else ("B3B_RUN_PARTIAL_PASS" if any_pass_role else "B3B_RUN_FAIL_ALL_DWELL_REQS")

    lines = []
    lines.append("PHASE 2 / B3B-run — TRUE DWELL SENSITIVITY")
    lines.append("=" * 72)
    lines.append(f"dwell_reqs       : {[float(x) for x in args.dwell_reqs]}")
    lines.append(f"heading_spread   : {float(args.heading_spread)}")
    lines.append(f"overall_decision : {overall_decision}")
    lines.append(f"combined_all_csv : {combined_all_csv}")
    lines.append("")
    lines.append("Dwell summary:")
    for _, r in by_dwell.iterrows():
        lines.append(
            f"  dwell_req={r['dwell_req']:g} | decision={r['decision']} | "
            f"pass={int(r['n_strict_pass'])}/{int(r['n_vehicles'])} | "
            f"role_distinct_ok={r['role_distinct_ok']} | max_dynamic_diff={r['max_dynamic_diff']}"
        )
    lines.append("")
    lines.append("Interpretation:")
    if overall_decision == "B3B_RUN_PASS_ALL_DWELL_REQS":
        lines.append("  - Role-distinct 3/3 TAEM success is retained for all tested dwell requirements.")
        lines.append("  - This supports event-latch robustness beyond the default N=3 dwell setting.")
    elif overall_decision == "B3B_RUN_PARTIAL_PASS":
        lines.append("  - At least one dwell requirement passed, but not the full tested set.")
        lines.append("  - Use by-vehicle labels to identify the dwell robustness boundary.")
    else:
        lines.append("  - No tested dwell requirement achieved 3/3 role-distinct PASS_STRICT under the raised latch condition.")
        lines.append("  - Inspect single-runner logs and by-vehicle rows before changing guidance.")

    summary_txt = report_dir / "phase2_B3B_run_summary.txt"
    summary_json = report_dir / "phase2_B3B_run_summary.json"
    summary_txt.write_text("\n".join(lines), encoding="utf-8")
    summary_json.write_text(json.dumps({
        "dwell_reqs": [float(x) for x in args.dwell_reqs],
        "heading_spread": float(args.heading_spread),
        "overall_decision": overall_decision,
        "by_dwell_csv": str(by_dwell_path),
        "by_vehicle_all_csv": str(by_vehicle_all_path),
        "combined_all_csv": str(combined_all_csv),
        "manifest": manifest,
        "dwell_rows": dwell_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["overall_decision"] = overall_decision
    manifest["by_dwell_csv"] = str(by_dwell_path)
    manifest["by_vehicle_all_csv"] = str(by_vehicle_all_path)
    manifest["summary_txt"] = str(summary_txt)
    manifest["summary_json"] = str(summary_json)
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print(f"[OK] wrote: {_rel(summary_txt)}")
    print(f"[OK] wrote: {_rel(summary_json)}")
    print(f"[OK] wrote: {_rel(by_dwell_path)}")


if __name__ == "__main__":
    main()
