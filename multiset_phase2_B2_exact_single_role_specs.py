# -*- coding: utf-8 -*-
"""
Phase 2 / B2 exact-single orchestration multiset.

Purpose
-------
Use the frozen V8.2 success CSV to recover the common initial state, target,
and TAEM terminal reference, then run each vehicle sequentially with a
role-specific PathSpec. This avoids the unreliable simultaneous MultiMissileSim
adapter path while preserving a multi-vehicle campaign structure.

Roles
-----
mis0: fixed-left/anchor role recovered from the pre-B1 same-target multiset.
mis1: V8.2 validated role; expected to reproduce PASS_STRICT.
mis2: merged-winner case2 role recovered from the pre-B1 same-target multiset.

This file is intended to be copied to multiset.py by
phase2_B2_exact_single_orchestrator.py.
"""

from __future__ import annotations

import os
import math
import numpy as np
import pandas as pd
from numpy import seterr

seterr(all='raise')

# ------------------------------------------------------------
# Simulation controls
# ------------------------------------------------------------
MAXITER = int(float(os.environ.get("B2_MAXITER", "2600000")))
t0 = 0
MIN_H = float(os.environ.get("B2_MIN_H", "1e-2"))
GROUND_H = float(os.environ.get("B2_GROUND_H", "5.0"))
INI_STEP = float(os.environ.get("B2_INI_STEP", "0.1"))

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

# ------------------------------------------------------------
# Frozen V8.2 reference CSV
# ------------------------------------------------------------
BASELINE_CSV = os.environ.get(
    "B2_BASELINE_CSV",
    os.path.join("store", "data_saved", "V8_2_BASELINE_FREEZE", "mis1_state_first_v8_2_final_success_flags.csv"),
)


def _fail(msg: str):
    raise RuntimeError("[B2 multiset] " + msg)


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

    lon_env = _env_angle_rad("B2_TARGET_LON_DEG", "B2_TARGET_LON_RAD")
    lat_env = _env_angle_rad("B2_TARGET_LAT_DEG", "B2_TARGET_LAT_RAD")
    if lon_env is not None and lat_env is not None:
        return lon_env, lat_env, "environment target"

    _fail("Could not infer target lon/lat from CSV. Set B2_TARGET_LON_DEG/LAT_DEG.")


def _ref_value(df: pd.DataFrame, names, default):
    col = _pick_col(df, names)
    if col is None:
        return float(default), "default"
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) == 0:
        return float(default), "default_empty_" + col
    return float(s.iloc[-1]), col


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

# ------------------------------------------------------------
# Role-specific PathSpecs recovered from the pre-B1 same-target setup.
# These are classification baselines, not tuned B2 patches.
# ------------------------------------------------------------
_PATH_SPECS = [
    dict(
        name="B2_mis0_fixed_anchor_recovered",
        policy_family="mis0_fixed_anchor",
        psi_bias_deg=-9.0,
        psi_bias_sgo_on_m=7.0e6,
        psi_bias_sgo_off_m=2.8e6,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=-1,
        terminal_alpha_boost_enable=True,
        terminal_alpha_boost_deg=0.75,
        terminal_alpha_boost_sgo_on_m=250000.0,
        terminal_alpha_boost_sgo_full_m=80000.0,
        terminal_alpha_boost_h_on_m=50000.0,
        terminal_alpha_boost_h_full_m=35000.0,
        phase2_role="B2_CLASSIFY_MIS0_RECOVERED_ROLE",
    ),
    dict(
        name="B2_mis1_v8_2_validated_recovered",
        policy_family="merged_winner_case4_case2",
        psi_bias_deg=-2.0,
        psi_bias_sgo_on_m=7.0e6,
        psi_bias_sgo_off_m=3.6e6,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=None,
        terminal_alpha_boost_enable=True,
        terminal_alpha_boost_deg=2.25,
        terminal_alpha_boost_sgo_on_m=330000.0,
        terminal_alpha_boost_sgo_full_m=120000.0,
        terminal_alpha_boost_h_on_m=50000.0,
        terminal_alpha_boost_h_full_m=35000.0,
        phase2_role="B2_REFERENCE_MIS1_B1E_PASS_ROLE",
    ),
    dict(
        name="B2_mis2_merged_winner_case2_recovered",
        policy_family="merged_winner_case4_case2",
        psi_bias_deg=-0.5,
        psi_bias_sgo_on_m=7.0e6,
        psi_bias_sgo_off_m=3.5e6,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=None,
        terminal_alpha_boost_enable=True,
        terminal_alpha_boost_deg=0.25,
        terminal_alpha_boost_sgo_on_m=240000.0,
        terminal_alpha_boost_sgo_full_m=80000.0,
        terminal_alpha_boost_h_on_m=50000.0,
        terminal_alpha_boost_h_full_m=35000.0,
        phase2_role="B2_CLASSIFY_MIS2_RECOVERED_ROLE",
    ),
]


def _make_case(i: int):
    pathspec = dict(_PATH_SPECS[i])
    pathspec["baseline_csv"] = BASELINE_CSV
    pathspec["target_source"] = _TARGET_SOURCE
    pathspec["b2_vehicle_id"] = int(i)
    return {
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
            "t": float(os.environ.get("B2_END_T", "2150")),
        },
        'PathSpec': pathspec,
        'Phase2Role': pathspec.get("phase2_role", f"B2_ROLE_{i}"),
    }


StatusParams = [_make_case(0), _make_case(1), _make_case(2)]
cases = StatusParams
case_num = int(float(os.environ.get("B2_DEFAULT_CASE_NUM", "1")))
case_num = max(0, min(2, case_num))

MissileInitStatus = StatusParams[case_num]['MissileInitStatus']
MissileEndStatus = StatusParams[case_num]['MissileEndStatus']
TargetInitStatus = StatusParams[case_num]['TargetInitStatus']

B2_VEHICLE_IDS = [0, 1, 2]
B2_BASELINE_CSV_USED = BASELINE_CSV
B2_TARGET_SOURCE_USED = _TARGET_SOURCE
B2_PATHSPECS = _PATH_SPECS

# Backward-compatible names used by prior B1 scripts.
B1_ACTIVE_MIS_IDS = [1]
B1_MONITOR_VEHICLE_ID = 1
B1_BASELINE_CSV_USED = BASELINE_CSV

# ------------------------------------------------------------
# Guidance parameters
# ------------------------------------------------------------
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

MAX_EBR2_ITER = int(float(os.environ.get("B2_MAX_EBR2_ITER", "5")))
STORE_DATA = os.environ.get("B2_STORE_DATA", os.path.join("store", "data_saved", "phase2_B2_exact_single_combined.csv"))

print("[B2 multiset] baseline_csv =", BASELINE_CSV)
print("[B2 multiset] target lon/lat deg =", np.rad2deg(_TAR_LON), np.rad2deg(_TAR_LAT), "source=", _TARGET_SOURCE)
print("[B2 multiset] init lon/lat/heading deg =", np.rad2deg(_INIT_LON), np.rad2deg(_INIT_LAT), np.rad2deg(_INIT_PSI))
print("[B2 multiset] end h/v/s =", _HTAEM, _VTAEM, _STAEM)
for _i, _ps in enumerate(_PATH_SPECS):
    print(f"[B2 multiset] StatusParams[{_i}] role=", _ps.get("phase2_role"), "PathSpec=", _ps)
