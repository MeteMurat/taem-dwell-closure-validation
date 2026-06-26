# -*- coding: utf-8 -*-
"""
phase2_B5F_mis0_reachability_orchestrator.py

B5F — mis0 long-propagation reachability + PathSpec activation audit

Purpose
-------
B5E showed that candidate path-shaping knobs did not differentiate the bounded
mis0 corner response within MAXITER=30000. B5F is therefore NOT another broad
psi-bias sweep. It is a short, evidence-generating reachability/audit campaign:

1. Run a few exact-single mis0 corner cases with larger MAXITER values.
2. Check whether range-to-go actually closes as propagation length increases.
3. Audit whether PathSpec / psi-bias channels are active in the generated CSV.
4. Classify whether the mis0 corner is a propagation-length issue or a guidance
   closure issue before any universality claim is expanded.

Run:
    python phase2_B5F_mis0_reachability_orchestrator.py --spec phase2_B5F_mis0_reachability_spec.json --limit 1

Full:
    python phase2_B5F_mis0_reachability_orchestrator.py --spec phase2_B5F_mis0_reachability_spec.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


def _as_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    if isinstance(x, (int, float, np.integer, np.floating)):
        try:
            return np.isfinite(float(x)) and float(x) > 0.5
        except Exception:
            return False
    return str(x).strip().lower() in {"1", "true", "t", "yes", "y", "pass", "passed"}


def _safe_float(x: Any, default: float = math.nan) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


def _safe_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _first_existing(df: pd.DataFrame, names: List[str]) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def _last_value(df: pd.DataFrame, names: List[str], default: Any = None) -> Any:
    c = _first_existing(df, names)
    if c is None or len(df) == 0:
        return default
    return df[c].iloc[-1]


def _first_value(df: pd.DataFrame, names: List[str], default: Any = None) -> Any:
    c = _first_existing(df, names)
    if c is None or len(df) == 0:
        return default
    return df[c].iloc[0]


def _max_abs_value(df: pd.DataFrame, names: List[str]) -> float:
    c = _first_existing(df, names)
    if c is None:
        return math.nan
    s = _safe_num(df[c])
    if not np.isfinite(s).any():
        return math.nan
    return float(np.nanmax(np.abs(s.to_numpy())))


def _max_value(df: pd.DataFrame, names: List[str]) -> float:
    c = _first_existing(df, names)
    if c is None:
        return math.nan
    s = _safe_num(df[c])
    if not np.isfinite(s).any():
        return math.nan
    return float(np.nanmax(s.to_numpy()))


def _min_value(df: pd.DataFrame, names: List[str]) -> float:
    c = _first_existing(df, names)
    if c is None:
        return math.nan
    s = _safe_num(df[c])
    if not np.isfinite(s).any():
        return math.nan
    return float(np.nanmin(s.to_numpy()))


def _unique_text(df: pd.DataFrame, col: str, max_items: int = 8) -> str:
    if col not in df.columns:
        return ""
    vals = []
    for v in df[col].dropna().astype(str).tolist():
        v = v.strip()
        if v and v not in vals:
            vals.append(v)
        if len(vals) >= max_items:
            break
    return "|".join(vals)


def _candidate_map(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(c["candidate_id"]): c for c in spec.get("candidate_pathspecs", [])}


def make_cases(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    cands = _candidate_map(spec)
    role = spec["mis0_role"]
    out = []
    for raw in spec["cases"]:
        cid = str(raw["candidate_id"])
        if cid not in cands:
            raise KeyError(f"candidate_id not found in candidate_pathspecs: {cid}")
        cand = dict(cands[cid])
        hd = float(raw.get("height_delta_m", 0.0))
        vd = float(raw.get("velocity_delta_mps", 0.0))
        hdeg = float(raw.get("heading_delta_deg", role.get("role_heading_delta_deg", -2.0)))
        maxiter = int(raw.get("generated_maxiter", spec.get("generated_maxiter", 100000)))
        label = raw.get("label") or f"{cid}_h{hd:+.0f}_v{vd:+.0f}_N{maxiter}"
        case_id = ("B5F_" + str(label)).replace("+", "p").replace("-", "m").replace(".", "p")
        out.append({
            "case_id": case_id,
            "label": str(label),
            "candidate": cand,
            "height_delta_m": hd,
            "velocity_delta_mps": vd,
            "heading_delta_deg": hdeg,
            "generated_maxiter": maxiter,
            "logical_mis_id": int(role.get("logical_mis_id", 0)),
            "role_name": str(role.get("role_name", "mis0_left_corner_role")),
            "sgn_ini_override": role.get("sgn_ini_override", -1),
        })
    return out


def render_multiset(spec: Dict[str, Any], case: Dict[str, Any], out_csv_rel: str) -> str:
    base = spec["base_initial_state"]
    target = spec["target"]
    taem = spec["taem_target"]
    cand = case["candidate"]

    h0 = float(base["height_m"]) + float(case["height_delta_m"])
    v0 = float(base["velocity_mps"]) + float(case["velocity_delta_mps"])
    hdg = float(base["heading_angle_deg"]) + float(case["heading_delta_deg"])
    generated_maxiter = int(case["generated_maxiter"])

    return f'''# -*- coding: utf-8 -*-
"""
AUTO-GENERATED by phase2_B5F_mis0_reachability_orchestrator.py
Do not edit this file manually during a B5F run.
Case: {case["case_id"]}
"""

import math
import os
import numpy as np
from numpy import seterr

seterr(all='raise')

MAXITER = {generated_maxiter}
t0 = 0
MIN_H = 1e-2
GROUND_H = 5.0
INI_STEP = 0.1

ParamsToGuide = [
    "t", "min_h", "self", "is_main",
    "bank_dwell_sec", "sigma_cmd_ema",
    "cos_delta_psi_eps", "update_L12D_denom_eps",
    "L12D_clip_factor", "L12D_update_alpha",
    "height_tol",
    "quad_epsabs", "quad_epsrel", "quad_limit",
]

GuideMetaDefaults = {{
    "bank_dwell_sec": 8.0,
    "sigma_cmd_ema": 0.15,
    "cos_delta_psi_eps": 1e-3,
    "update_L12D_denom_eps": 1e-6,
    "L12D_clip_factor": 0.98,
    "L12D_update_alpha": 0.15,
    "height_tol": 10.0,
    "quad_epsabs": 1e-7,
    "quad_epsrel": 1e-7,
    "quad_limit": 200,
}}

TARGET_LON_DEG = {float(target["lon_deg"])}
TARGET_LAT_DEG = {float(target["lat_deg"])}
_TAR_LON = np.deg2rad(TARGET_LON_DEG)
_TAR_LAT = np.deg2rad(TARGET_LAT_DEG)

_PATH_SPECS = [
    dict(
        name="{case["case_id"]}",
        phase2_campaign="B5F_mis0_reachability_pathspec_audit",
        phase2_role="{case["role_name"]}",
        role_name="{case["role_name"]}",
        logical_mis_id={int(case["logical_mis_id"])},
        b5f_case_id="{case["case_id"]}",
        b5f_candidate_id="{cand["candidate_id"]}",
        b5f_generated_maxiter={generated_maxiter},
        height_delta_m={float(case["height_delta_m"])},
        velocity_delta_mps={float(case["velocity_delta_mps"])},
        role_heading_delta_deg={float(case["heading_delta_deg"])},
        psi_bias_deg={float(cand["psi_bias_deg"])},
        psi_bias_sgo_on_m={float(cand["psi_bias_sgo_on_m"])},
        psi_bias_sgo_off_m={float(cand["psi_bias_sgo_off_m"])},
        psi_bias_alt_on_m={float(cand["psi_bias_alt_on_m"])},
        psi_bias_alt_off_m={float(cand["psi_bias_alt_off_m"])},
        sgn_ini_override={case["sgn_ini_override"]},
    ),
]

StatusParams = [
    {{
        'MissileInitStatus': {{
            "t": 0,
            "longitude": np.deg2rad({float(base["longitude_deg"])}),
            "latitude": np.deg2rad({float(base["latitude_deg"])}),
            "height": {h0},
            "velocity": {v0},
            "path_angle": np.deg2rad({float(base["path_angle_deg"])}),
            "heading_angle": np.deg2rad({hdg}),
        }},
        'TargetInitStatus': {{
            "longitude": _TAR_LON,
            "latitude": _TAR_LAT,
        }},
        'MissileEndStatus': {{
            "velocity": {float(taem["velocity_mps"])},
            "height": {float(taem["height_m"])},
            "height_tol": 10.0,
            "s": {float(taem["s_go_m"])},
            "heading_angle": None,
            "t": {float(taem["t_end_s"])},
        }},
        'PathSpec': _PATH_SPECS[0],
    }},
]

CONSIDER_SIGMA_MAX = True
K_GAMMA_SGP = 3
ERR_TOL = 3e-4
K_SIGMA = 10
K_ALPHA = 5 * np.pi / 1e7 / 1.8
CONTROL_PARAM_LIST = ["m", "attack_angle", "bank_angle"]

GUIDE_SAVE_PARAM = [
    "sigma_max", "gamma_sg", "s_go", "sgo_ref", "ref_psi", "delta_psi",
    "q", "L12D", "L12D_E", "L12D_alpha", "a_tol", "aL1", "aL2",
    "CL_beg", "aL2_orig", "ref_sgo", "ref_t", "ref_L12D", "L12D_beg",
    "psi_bias_cmd", "psi_bias_w", "psi_bias_w_sgo", "psi_bias_w_alt", "psi_bias_state",
    "cos_delta_psi", "L12D_singularity", "L12D_den_singularity", "L12D_update_hold",
    "sigma_cmd_raw", "sigma_cmd_prev", "L1_L", "BR_times", "sgn_ini", "end_reason", "t_local_end",
    "taem_in_box", "taem_reached", "taem_reached_event", "taem_reached_ever", "taem_success_latched",
    "taem_dwell_s", "taem_dwell_count", "taem_h_err", "taem_v_err", "taem_s_go_err", "close_pass_escape",
]

MAX_EBR2_ITER = 5
STORE_DATA = r"{out_csv_rel}"
'''


def annotate_and_evaluate(csv_path: Path, case: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    cand = case["candidate"]
    row: Dict[str, Any] = {
        "case_id": case["case_id"],
        "label": case.get("label", case["case_id"]),
        "candidate_id": cand["candidate_id"],
        "height_delta_m": case["height_delta_m"],
        "velocity_delta_mps": case["velocity_delta_mps"],
        "heading_delta_deg": case["heading_delta_deg"],
        "generated_maxiter": case["generated_maxiter"],
        "psi_bias_deg": cand["psi_bias_deg"],
        "psi_bias_sgo_on_m": cand["psi_bias_sgo_on_m"],
        "psi_bias_sgo_off_m": cand["psi_bias_sgo_off_m"],
        "psi_bias_alt_on_m": cand["psi_bias_alt_on_m"],
        "psi_bias_alt_off_m": cand["psi_bias_alt_off_m"],
        "csv": str(csv_path),
        "run_return_code": 0,
    }

    if not csv_path.exists():
        row.update({"decision": "NO_CSV", "strict_pass": False, "score": 1e9})
        return row

    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        row.update({"decision": "CSV_READ_ERROR", "strict_pass": False, "score": 1e9, "error": str(exc)})
        return row

    if len(df) == 0:
        row.update({"decision": "EMPTY_CSV", "strict_pass": False, "score": 1e9})
        return row

    # Annotate CSV for traceability.
    df["phase2_campaign"] = "B5F_mis0_reachability_pathspec_audit"
    df["phase2_role"] = case["role_name"]
    df["logical_mis_id"] = int(case["logical_mis_id"])
    df["b5f_case_id"] = case["case_id"]
    df["b5f_candidate_id"] = cand["candidate_id"]
    df["b5f_generated_maxiter"] = int(case["generated_maxiter"])
    df["b5f_height_delta_m"] = float(case["height_delta_m"])
    df["b5f_velocity_delta_mps"] = float(case["velocity_delta_mps"])
    df["b5f_heading_delta_deg"] = float(case["heading_delta_deg"])
    try:
        df.to_csv(csv_path, index=False)
    except Exception:
        pass

    last = df.iloc[-1]
    success_cols = spec["acceptance"]["strict_success_columns"]
    success_flags = {c: (_as_bool(last[c]) if c in df.columns else False) for c in success_cols}
    any_success_flag = any(success_flags.values())

    close_escape = _as_bool(_last_value(df, ["close_pass_escape", "any_close_pass_escape"], False))
    reject_close_escape = bool(spec["acceptance"].get("reject_if_close_pass_escape", True))

    h_err = _safe_float(_last_value(df, ["taem_h_err", "taem_err_h_m", "taem_h_err_final"], math.nan))
    v_err = _safe_float(_last_value(df, ["taem_v_err", "taem_err_v_mps", "taem_v_err_final"], math.nan))
    sgo_err = _safe_float(_last_value(df, ["taem_s_go_err", "taem_err_sgo_m", "taem_s_go_err_final"], math.nan))

    h_tol = float(spec["acceptance"]["reference_tolerances"]["h_tol_m"])
    v_tol = float(spec["acceptance"]["reference_tolerances"]["v_tol_mps"])
    sgo_tol = float(spec["acceptance"]["reference_tolerances"]["s_go_tol_m"])

    tol_ok = True
    if math.isfinite(h_err): tol_ok = tol_ok and abs(h_err) <= h_tol
    if math.isfinite(v_err): tol_ok = tol_ok and abs(v_err) <= v_tol
    if math.isfinite(sgo_err): tol_ok = tol_ok and abs(sgo_err) <= sgo_tol

    strict_pass = bool(any_success_flag and (not close_escape if reject_close_escape else True))

    s_go_start = _safe_float(_first_value(df, ["s_go"], math.nan))
    s_go_final = _safe_float(_last_value(df, ["s_go"], math.nan))
    s_go_min = _min_value(df, ["s_go"])
    s_go_drop_m = s_go_start - s_go_final if math.isfinite(s_go_start) and math.isfinite(s_go_final) else math.nan
    s_go_drop_pct = 100.0 * s_go_drop_m / s_go_start if math.isfinite(s_go_drop_m) and s_go_start > 0 else math.nan

    psi_bias_cmd_max_abs = _max_abs_value(df, ["psi_bias_cmd"])
    psi_bias_w_max = _max_value(df, ["psi_bias_w"])
    psi_bias_w_last = _safe_float(_last_value(df, ["psi_bias_w"], math.nan))
    psi_bias_state_unique = _unique_text(df, "psi_bias_state")
    guide_phase_unique = _unique_text(df, "guide_phase")
    guide_phase_last = str(_last_value(df, ["guide_phase"], "") or "")

    pathspec_active = bool(
        (math.isfinite(psi_bias_cmd_max_abs) and psi_bias_cmd_max_abs > 1e-8) or
        (math.isfinite(psi_bias_w_max) and psi_bias_w_max > 1e-8) or
        bool(psi_bias_state_unique)
    )

    # Reachability diagnosis: evidence-based, not a success claim.
    if strict_pass:
        decision = "PASS_STRICT"
    elif close_escape:
        decision = "FAIL_CLOSE_PASS_ESCAPE"
    elif math.isfinite(s_go_drop_pct) and s_go_drop_pct >= float(spec.get("reachability_drop_pct_threshold", 10.0)):
        decision = "NO_PASS_BUT_RANGE_CLOSING"
    elif pathspec_active:
        decision = "NO_PASS_PATHSPEC_ACTIVE_WEAK_CLOSURE"
    else:
        decision = "NO_PASS_PATHSPEC_INACTIVE_OR_PREPHASE"

    h_norm = abs(h_err) / h_tol if math.isfinite(h_err) else 5.0
    v_norm = abs(v_err) / v_tol if math.isfinite(v_err) else 5.0
    s_norm = abs(sgo_err) / sgo_tol if math.isfinite(sgo_err) else 5.0
    closure_bonus = max(0.0, min(100.0, s_go_drop_pct if math.isfinite(s_go_drop_pct) else 0.0))
    escape_penalty = 100.0 if close_escape else 0.0
    fail_penalty = 0.0 if strict_pass else 1000.0
    # Lower is better; reward range closure slightly.
    score = fail_penalty + escape_penalty + h_norm + v_norm + s_norm - 0.1 * closure_bonus

    row.update({
        "decision": decision,
        "strict_pass": bool(strict_pass),
        "close_pass_escape_last": bool(close_escape),
        "taem_h_err_final": h_err,
        "taem_v_err_final": v_err,
        "taem_s_go_err_final": sgo_err,
        "taem_dwell_s_final": _safe_float(_last_value(df, ["taem_dwell_s", "taem_dwell_s_final"], math.nan)),
        "taem_dwell_count_final": _safe_float(_last_value(df, ["taem_dwell_count", "taem_dwell_count_final"], math.nan)),
        "s_go_start": s_go_start,
        "s_go_final": s_go_final,
        "s_go_min": s_go_min,
        "s_go_drop_m": s_go_drop_m,
        "s_go_drop_pct": s_go_drop_pct,
        "height_start": _safe_float(_first_value(df, ["height"], math.nan)),
        "height_final": _safe_float(_last_value(df, ["height"], math.nan)),
        "velocity_start": _safe_float(_first_value(df, ["velocity"], math.nan)),
        "velocity_final": _safe_float(_last_value(df, ["velocity"], math.nan)),
        "q_max": _max_abs_value(df, ["q"]),
        "bank_angle_max_abs": _max_abs_value(df, ["bank_angle"]),
        "delta_psi_max_abs": _max_abs_value(df, ["delta_psi"]),
        "psi_bias_cmd_max_abs": psi_bias_cmd_max_abs,
        "psi_bias_w_max": psi_bias_w_max,
        "psi_bias_w_last": psi_bias_w_last,
        "psi_bias_state_unique": psi_bias_state_unique,
        "pathspec_active": pathspec_active,
        "guide_phase_unique": guide_phase_unique,
        "guide_phase_last": guide_phase_last,
        "score": float(score),
    })

    for k, v in success_flags.items():
        row[f"flag_{k}"] = bool(v)
    return row


def run_child(cmd: List[str], root: Path, log_out: Path, log_err: Path, timeout_sec: float, progress_interval: float, maxiter: int) -> Tuple[int, float, bool]:
    t0_run = time.time()
    timed_out = False
    return_code = None
    child_env = os.environ.copy()
    # Windows/Turkish locale fix:
    # the underlying guidance code prints Chinese status messages.
    # Without UTF-8 mode, Python may use cp1254 and crash with UnicodeEncodeError.
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"

    with open(log_out, "w", encoding="utf-8", errors="ignore") as fout, open(log_err, "w", encoding="utf-8", errors="ignore") as ferr:
        fout.write(f"[B5F parent] command: {' '.join(cmd)}\n")
        fout.write(f"[B5F parent] generated MAXITER: {maxiter}\n")
        fout.write(f"[B5F parent] timeout_sec: {timeout_sec}\n")
        fout.write("[B5F parent] env: PYTHONUTF8=1, PYTHONIOENCODING=utf-8\n")
        fout.flush()
        proc = subprocess.Popen(cmd, cwd=str(root), stdout=fout, stderr=ferr, text=True, shell=False, env=child_env)
        next_progress = time.time() + progress_interval
        while True:
            return_code = proc.poll()
            if return_code is not None:
                break
            elapsed = time.time() - t0_run
            if elapsed >= timeout_sec:
                timed_out = True
                print(f"[B5F] TIMEOUT: elapsed={elapsed:.1f}s / timeout={timeout_sec:.0f}s")
                try:
                    proc.kill()
                except Exception:
                    pass
                return_code = proc.wait(timeout=10)
                break
            if time.time() >= next_progress:
                print(f"[B5F] child still running: elapsed={elapsed:.0f}s / timeout={timeout_sec:.0f}s")
                next_progress = time.time() + progress_interval
            time.sleep(1.0)
    return int(return_code if return_code is not None else -999), float(time.time() - t0_run), bool(timed_out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="B5F JSON spec file")
    ap.add_argument("--limit", type=int, default=None, help="Run only first N cases")
    ap.add_argument("--skip-existing", action="store_true", help="Skip cases whose output CSV already exists")
    ap.add_argument("--timeout-sec", type=float, default=None, help="Per-case subprocess timeout. Overrides spec/case timeout.")
    ap.add_argument("--progress-interval-sec", type=float, default=60.0)
    ap.add_argument("--keep-last-multiset", action="store_true")
    args = ap.parse_args()

    root = Path.cwd()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    outdir = root / spec["output_dir"]
    runs_dir = outdir / "runs"
    logs_dir = outdir / "logs"
    outdir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    multiset_path = root / "multiset.py"
    if not multiset_path.exists():
        raise FileNotFoundError(f"multiset.py not found at: {multiset_path}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = root / f"multiset.py.B5F_backup_{stamp}"
    shutil.copy2(multiset_path, backup_path)

    cases = make_cases(spec)
    if args.limit is not None:
        cases = cases[: int(args.limit)]

    manifest = {
        "experiment": spec["experiment"],
        "created_at": stamp,
        "backup_multiset": str(backup_path),
        "n_cases": len(cases),
        "cases": [c["case_id"] for c in cases],
    }
    (outdir / "phase2_B5F_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    rows = []
    print(f"[B5F] cases = {len(cases)}")
    print(f"[B5F] output = {outdir}")
    print(f"[B5F] backup = {backup_path}")

    try:
        for idx, case in enumerate(cases, start=1):
            out_csv_rel = str((runs_dir / f"{case['case_id']}.csv").relative_to(root)).replace("\\", "/")
            out_csv_abs = root / out_csv_rel
            print(f"\n[B5F] ({idx}/{len(cases)}) {case['case_id']} MAXITER={case['generated_maxiter']}")

            if args.skip_existing and out_csv_abs.exists():
                print("[B5F] skip existing CSV")
                row = annotate_and_evaluate(out_csv_abs, case, spec)
                row["skipped_existing"] = True
                rows.append(row)
                continue

            multiset_text = render_multiset(spec, case, out_csv_rel)
            multiset_path.write_text(multiset_text, encoding="utf-8")

            cmd = [spec.get("python_exe", "python"), spec.get("run_script", "multi_main.py")]
            case_timeout = float(case.get("timeout_sec", spec.get("timeout_sec", 1800.0)))
            timeout_sec = float(args.timeout_sec if args.timeout_sec is not None else case_timeout)
            progress_interval = max(10.0, float(args.progress_interval_sec))
            log_out = logs_dir / f"{case['case_id']}.stdout.txt"
            log_err = logs_dir / f"{case['case_id']}.stderr.txt"

            rc, elapsed_s, timed_out = run_child(cmd, root, log_out, log_err, timeout_sec, progress_interval, int(case["generated_maxiter"]))

            row = annotate_and_evaluate(out_csv_abs, case, spec)
            row["run_return_code"] = int(rc)
            row["elapsed_s"] = float(elapsed_s)
            row["timeout_sec"] = float(timeout_sec)
            row["timed_out"] = bool(timed_out)
            if timed_out:
                row["decision"] = "TIMEOUT_" + str(row.get("decision", "NO_DECISION"))
                row["strict_pass"] = False
                row["score"] = 1e9
            elif rc != 0 and row.get("decision") != "PASS_STRICT":
                row["decision"] = "SUBPROCESS_FAIL_" + str(row.get("decision", "NO_DECISION"))
                row["strict_pass"] = False
                row["score"] = 1e9

            rows.append(row)
            print(
                f"[B5F] decision={row.get('decision')} score={row.get('score')} "
                f"sgo_start={row.get('s_go_start')} sgo_final={row.get('s_go_final')} "
                f"drop_pct={row.get('s_go_drop_pct')} pathspec_active={row.get('pathspec_active')} "
                f"phase_last={row.get('guide_phase_last')} elapsed_s={row.get('elapsed_s')} timed_out={row.get('timed_out')}"
            )
            pd.DataFrame(rows).to_csv(outdir / "phase2_B5F_by_run_partial.csv", index=False)

    finally:
        if args.keep_last_multiset:
            print("[B5F] keeping last generated multiset.py")
        else:
            shutil.copy2(backup_path, multiset_path)
            print("[B5F] original multiset.py restored")

    report = pd.DataFrame(rows)
    if len(report):
        report = report.sort_values(["strict_pass", "score"], ascending=[False, True]).reset_index(drop=True)
    report_path = outdir / "phase2_B5F_by_run.csv"
    report.to_csv(report_path, index=False)
    best_path = outdir / "phase2_B5F_best_candidates.csv"
    report.head(12).to_csv(best_path, index=False)

    print("\n[B5F] DONE")
    print(f"[B5F] report: {report_path}")
    print(f"[B5F] best  : {best_path}")
    if len(report):
        n_pass = int(report["strict_pass"].astype(bool).sum())
        print(f"[B5F] strict_pass = {n_pass}/{len(report)}")
        cols = [
            "case_id", "candidate_id", "generated_maxiter", "decision", "strict_pass", "score",
            "s_go_start", "s_go_final", "s_go_drop_pct", "pathspec_active", "guide_phase_last",
            "taem_h_err_final", "taem_v_err_final", "taem_s_go_err_final", "timed_out",
        ]
        print(report[[c for c in cols if c in report.columns]].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
