# -*- coding: utf-8 -*-
"""
Phase 2 / B1R-P multiset: frozen V8.2 success CSV + recovered PathSpec.

This test keeps the frozen success CSV initial/target/end state but restores the
mis1 PathSpec from a local backup multiset. The prior B1R used a zero/minimal
PathSpec and reproduced the same close-pass-escape failure; therefore the next
controlled test is to restore the path-shaping/terminal-alpha parameters too.
"""

import os
import math
import importlib.util
import numpy as np
import pandas as pd
from numpy import seterr

seterr(all='raise')

MAXITER = int(float(os.environ.get("B1R_MAXITER", "2600000")))
t0 = 0
MIN_H = float(os.environ.get("B1R_MIN_H", "1e-2"))
GROUND_H = float(os.environ.get("B1R_GROUND_H", "5.0"))
INI_STEP = float(os.environ.get("B1R_INI_STEP", "0.1"))

ParamsToGuide = [
    "t", "min_h", "self", "is_main",
    "bank_dwell_sec", "sigma_cmd_ema",
    "cos_delta_psi_eps", "update_L12D_denom_eps",
    "L12D_clip_factor", "L12D_update_alpha",
    "height_tol",
    "quad_epsabs", "quad_epsrel", "quad_limit",
]

GuideMetaDefaults = {
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
}

BASELINE_CSV = os.environ.get(
    "B1R_BASELINE_CSV",
    os.path.join("store", "data_saved", "V8_2_BASELINE_FREEZE", "mis1_state_first_v8_2_final_success_flags.csv"),
)
PATHSPEC_SOURCE_FILE = os.environ.get("B1R_PATHSPEC_SOURCE_FILE", "multiset_BACKUP_before_phase2_B1.py")
PATHSPEC_SOURCE_ID = int(float(os.environ.get("B1R_PATHSPEC_SOURCE_ID", "1")))


def _fail(msg: str):
    raise RuntimeError("[B1R-P multiset] " + msg)


def _load_baseline_df() -> pd.DataFrame:
    if not os.path.exists(BASELINE_CSV):
        _fail("Baseline CSV not found: %s" % BASELINE_CSV)
    df = pd.read_csv(BASELINE_CSV)
    if len(df) == 0:
        _fail("Baseline CSV is empty: %s" % BASELINE_CSV)
    return df


def _num(row, col, default=None):
    if col not in row.index:
        return default
    try:
        v = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _pick_col(df: pd.DataFrame, candidates):
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _angle_to_rad(v: float) -> float:
    if abs(float(v)) <= 2.0 * math.pi + 1e-6:
        return float(v)
    return float(np.deg2rad(v))


def _env_angle_rad(name_deg: str, name_rad: str):
    if name_rad in os.environ:
        return float(os.environ[name_rad])
    if name_deg in os.environ:
        return float(np.deg2rad(float(os.environ[name_deg])))
    return None


def _target_from_df_or_env(df: pd.DataFrame, row: pd.Series):
    lon_deg_col = _pick_col(df, [
        "lz_lon_deg", "landing_zone_lon_deg", "target_lon_deg", "target_longitude_deg",
        "tar_lon_deg", "tar_longitude_deg",
    ])
    lat_deg_col = _pick_col(df, [
        "lz_lat_deg", "landing_zone_lat_deg", "target_lat_deg", "target_latitude_deg",
        "tar_lat_deg", "tar_latitude_deg",
    ])
    if lon_deg_col and lat_deg_col:
        lon = _num(row, lon_deg_col)
        lat = _num(row, lat_deg_col)
        if lon is not None and lat is not None:
            return float(np.deg2rad(lon)), float(np.deg2rad(lat)), f"CSV deg columns: {lon_deg_col}, {lat_deg_col}"

    lon_col = _pick_col(df, [
        "lz_lon", "landing_zone_lon", "target_lon", "target_longitude",
        "tar_lon", "tar_longitude", "TargetInitStatus_longitude",
    ])
    lat_col = _pick_col(df, [
        "lz_lat", "landing_zone_lat", "target_lat", "target_latitude",
        "tar_lat", "tar_latitude", "TargetInitStatus_latitude",
    ])
    if lon_col and lat_col:
        lon = _num(row, lon_col)
        lat = _num(row, lat_col)
        if lon is not None and lat is not None:
            return _angle_to_rad(lon), _angle_to_rad(lat), f"CSV angle columns: {lon_col}, {lat_col}"

    lon_env = _env_angle_rad("B1R_TARGET_LON_DEG", "B1R_TARGET_LON_RAD")
    lat_env = _env_angle_rad("B1R_TARGET_LAT_DEG", "B1R_TARGET_LAT_RAD")
    if lon_env is not None and lat_env is not None:
        return lon_env, lat_env, "environment target"

    _fail("Could not infer target lon/lat from CSV. Set B1R_TARGET_LON_DEG/LAT_DEG.")


def _ref_value(df: pd.DataFrame, names, default):
    col = _pick_col(df, names)
    if col is None:
        return float(default), "default"
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) == 0:
        return float(default), "default_empty_" + col
    return float(s.iloc[-1]), col


def _load_pathspec_from_file(path: str, idx: int):
    if not path or not os.path.exists(path):
        return {}, f"missing:{path}"
    try:
        spec = importlib.util.spec_from_file_location("_b1r_pathspec_source", path)
        if spec is None or spec.loader is None:
            return {}, f"load_failed:{path}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        sp = getattr(mod, "StatusParams", None)
        if not isinstance(sp, (list, tuple)) or idx >= len(sp):
            return {}, f"no_StatusParams_or_idx:{path}:{idx}"
        ps = dict(sp[idx].get("PathSpec", {}) or {})
        return ps, f"{path}:StatusParams[{idx}].PathSpec"
    except Exception as exc:
        return {}, f"error:{path}:{type(exc).__name__}:{exc}"


_df = _load_baseline_df()
_first = _df.iloc[0]

_INIT_LON = _angle_to_rad(_num(_first, "longitude", 0.0))
_INIT_LAT = _angle_to_rad(_num(_first, "latitude", 0.0))
_INIT_H = float(_num(_first, "height", 80000.0))
_INIT_V = float(_num(_first, "velocity", 7000.0))
_INIT_GAMMA = _angle_to_rad(_num(_first, "path_angle", 0.0))
_INIT_PSI = _angle_to_rad(_num(_first, "heading_angle", 120.0))
_INIT_T = float(_num(_first, "t", _num(_first, "global_t", 0.0)))

_TAR_LON, _TAR_LAT, _TARGET_SOURCE = _target_from_df_or_env(_df, _first)
_HTAEM, _HTAEM_SRC = _ref_value(_df, ["HTAEM", "H_TAEM", "taem_h_ref", "taem_h_target"], 25000.0)
_VTAEM, _VTAEM_SRC = _ref_value(_df, ["VTAEM", "V_TAEM", "taem_v_ref", "taem_v_target"], 2000.0)
_STAEM, _STAEM_SRC = _ref_value(_df, ["STAEM", "S_TAEM", "taem_s_go_ref", "taem_sgo_ref"], 50000.0)

_recovered_pathspec, _PATHSPEC_SOURCE = _load_pathspec_from_file(PATHSPEC_SOURCE_FILE, PATHSPEC_SOURCE_ID)
_PATH_SPEC = dict(_recovered_pathspec)
if not _PATH_SPEC:
    _PATH_SPEC = dict(
        name="B1R_P_fallback_zero_bias",
        policy_family="fallback_no_recovered_pathspec",
        psi_bias_deg=0.0,
        psi_bias_sgo_on_m=7.0e6,
        psi_bias_sgo_off_m=4.0e6,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=None,
    )

_PATH_SPEC["phase2_role"] = "B1R_ACTIVE_MIS1_FROM_SUCCESS_CSV_PLUS_RECOVERED_PATHSPEC"
_PATH_SPEC["baseline_csv"] = BASELINE_CSV
_PATH_SPEC["target_source"] = _TARGET_SOURCE
_PATH_SPEC["pathspec_source"] = _PATHSPEC_SOURCE
_PATH_SPEC.setdefault("name", "B1R_active_mis1_success_csv_plus_pathspec")

_case = {
    'MissileInitStatus': {
        "t": _INIT_T,
        "longitude": _INIT_LON,
        "latitude": _INIT_LAT,
        "height": _INIT_H,
        "velocity": _INIT_V,
        "path_angle": _INIT_GAMMA,
        "heading_angle": _INIT_PSI,
    },
    'TargetInitStatus': {"longitude": _TAR_LON, "latitude": _TAR_LAT},
    'MissileEndStatus': {
        "velocity": _VTAEM,
        "height": _HTAEM,
        "height_tol": 10.0,
        "s": _STAEM,
        "heading_angle": None,
        "t": float(os.environ.get("B1R_END_T", "2150")),
    },
    'PathSpec': _PATH_SPEC,
    'Phase2Role': 'B1R_ACTIVE_MIS1_FROM_SUCCESS_CSV_PLUS_PATHSPEC',
}

cases = [_case]
case_num = 0
MissileInitStatus = _case['MissileInitStatus']
MissileEndStatus = _case['MissileEndStatus']
TargetInitStatus = _case['TargetInitStatus']

StatusParams = []
for i in range(3):
    c = {
        'MissileInitStatus': dict(_case['MissileInitStatus']),
        'TargetInitStatus': dict(_case['TargetInitStatus']),
        'MissileEndStatus': dict(_case['MissileEndStatus']),
        'PathSpec': dict(_PATH_SPEC),
        'Phase2Role': 'B1R_CONTEXT_INACTIVE' if i != 1 else 'B1R_ACTIVE_MIS1_FROM_SUCCESS_CSV_PLUS_PATHSPEC',
    }
    c['PathSpec']['name'] = 'B1R_P_inactive_context_%d' % i if i != 1 else 'B1R_P_active_mis1_success_csv_plus_pathspec'
    StatusParams.append(c)

B1_ACTIVE_MIS_IDS = [1]
B1_MONITOR_VEHICLE_ID = 1
B1_BASELINE_CSV_USED = BASELINE_CSV
B1_PATHSPEC_SOURCE_USED = _PATHSPEC_SOURCE

CONSIDER_SIGMA_MAX = True
K_GAMMA_SGP = 3
ERR_TOL = 3e-4
K_SIGMA = 10
K_ALPHA = 5 * np.pi / 1e7 / 1.8
CONTROL_PARAM_LIST = ["m", "attack_angle", "bank_angle"]

GUIDE_SAVE_PARAM = [
    "sigma_max", "gamma_sg", "s_go", "sgo_ref", "ref_psi", "delta_psi", "q", "L12D", "E",
    "L12D_E", "L12D_alpha", "a_tol", "aL1", "aL2", "CL_beg", "aL2_orig",
    "ref_sgo", "ref_t", "ref_L12D", "L12D_beg",
    "psi_bias_cmd", "psi_bias_w", "psi_bias_w_sgo", "psi_bias_w_alt", "psi_bias_state",
    "cos_delta_psi", "L12D_singularity", "L12D_den_singularity", "L12D_update_hold",
    "sigma_cmd_raw", "sigma_cmd_prev", "L1_L", "BR_times", "sgn_ini",
    "taem_in_box", "taem_reached", "taem_reached_event", "taem_reached_ever",
    "taem_success_latched", "taem_success_flag",
    "taem_t_global", "taem_t_local", "taem_h_err", "taem_v_err", "taem_s_go_err", "taem_sgo_err",
    "taem_psi_err", "taem_gamma_err", "taem_dwell_s", "taem_dwell_time_s", "taem_dwell_count",
    "taem_dwell_steps", "box_score", "taem_close_score",
    "close_pass_escape", "close_pass_escape_latched",
    "guide_phase", "end_reason", "t_local_end",
]

MAX_EBR2_ITER = int(float(os.environ.get("B1R_MAX_EBR2_ITER", "5")))
STORE_DATA = os.environ.get(
    "B1R_STORE_DATA",
    os.path.join("store", "data_saved", "phase2_B1R_from_success_csv_pathspec_mis1_transfer.csv"),
)

print("[B1R-P multiset] baseline_csv =", BASELINE_CSV)
print("[B1R-P multiset] pathspec_source =", _PATHSPEC_SOURCE)
print("[B1R-P multiset] recovered PathSpec =", _PATH_SPEC)
print("[B1R-P multiset] init lon/lat/heading deg =", np.rad2deg(_INIT_LON), np.rad2deg(_INIT_LAT), np.rad2deg(_INIT_PSI))
print("[B1R-P multiset] target lon/lat deg =", np.rad2deg(_TAR_LON), np.rad2deg(_TAR_LAT), "source=", _TARGET_SOURCE)
print("[B1R-P multiset] end h/v/s =", _HTAEM, _VTAEM, _STAEM)
print("[B1R-P multiset] B1_ACTIVE_MIS_IDS =", B1_ACTIVE_MIS_IDS)
