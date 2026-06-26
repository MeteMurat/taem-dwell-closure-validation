import math
import numpy as np
from numpy import seterr

seterr(all='raise')

# ------------------------------------------------------------
# Simulation controls
# ------------------------------------------------------------

# Maximum iteration count
MAXITER = 2.6e6

# Global initial time
t0 = 0

# Minimum simulation step
MIN_H = 1e-2
GROUND_H = 5.0
# Initial step length per vehicle
INI_STEP = 0.1

# Parameters passed to guidance each step
# - self: the simulation object
# - t: global time
# - min_h: step size
# - is_main: main-loop indicator (if used by your sim)
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
# Case setup: SAME target (lon/lat) for all vehicles
# ------------------------------------------------------------

# Common target (deg)
TARGET_LON_DEG = 75.0
TARGET_LAT_DEG = -25.0

_TAR_LON = np.deg2rad(TARGET_LON_DEG)
_TAR_LAT = np.deg2rad(TARGET_LAT_DEG)

# Path shaping (same target, different route)
# psi_bias_deg: heading reference bias at long range
# psi_bias_sgo_on_m : bias fully active when s_go >= this value
# psi_bias_sgo_off_m: bias fades to 0 when s_go <= this value
# sgn_ini_override  : force initial bank-direction sign (-1, +1)
# CSV’nize göre: başlangıç s_go ≈ 11.115e6 m.
# mis_id=2, 3e6 eşiğinin altına hiç inmediği için w=1 kaldı.
# Bu yüzden fade penceresini 7e6 -> 4e6 aralığına taşıyoruz.
# Ayrıca irtifa fallback ekliyoruz: 50 km üstünde bias aktif, 25 km altında bias sıfır.
_PATH_SPECS = [
    dict(
        name="route_left",
        psi_bias_deg=-11.178132,
        psi_bias_sgo_on_m=1663327.063851,
        psi_bias_sgo_off_m=414649.479978,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=-1,
        beg_sgo_trigger_m=859210.408718,
        terminal_alpha_boost_enable=False,
    ),
    dict(
        name="route_mid",
        psi_bias_deg=0.0,
        psi_bias_sgo_on_m=1.8e6,
        psi_bias_sgo_off_m=3.5e5,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=None,
        beg_sgo_trigger_m=925122.506847,
        terminal_alpha_boost_enable=True,
        terminal_alpha_boost_deg=0.688355,
        terminal_alpha_boost_sgo_on_m=541955.376040,
        terminal_alpha_boost_sgo_full_m=140891.176159,
        terminal_alpha_boost_h_on_m=5.0e4,
        terminal_alpha_boost_h_full_m=3.0e4,
    ),
    dict(
        name="route_right",
        psi_bias_deg=4.768682,
        psi_bias_sgo_on_m=1760308.750316,
        psi_bias_sgo_off_m=292699.506058,
        psi_bias_alt_on_m=50000.0,
        psi_bias_alt_off_m=25000.0,
        sgn_ini_override=+1,
        beg_sgo_trigger_m=1359720.743867,
        steady_sigma_cap_rad=np.deg2rad(38.438651),
        beg_sigma_cap_rad=np.deg2rad(22.582093),
        terminal_alpha_boost_enable=False,
    ),
]

# Simulation case parameters
StatusParams = [
    {
        'MissileInitStatus': {
            "t": 0,
            "longitude": np.deg2rad(0),
            "latitude": np.deg2rad(50),
            "height": 80000,
            "velocity": 7000,
            "path_angle": np.deg2rad(0),
            "heading_angle": np.deg2rad(120),
        },
        'TargetInitStatus': {
            "longitude": _TAR_LON,
            "latitude": _TAR_LAT,
        },
        'MissileEndStatus': {
            "velocity": 2000,
            "height": 25000.0, "height_tol": 10.0,
            "s": 50000.0,
            "heading_angle": None,
            "t": 2150,
        },
        'PathSpec': _PATH_SPECS[0],
    },
    {
        'MissileInitStatus': {
            "t": 0,
            "longitude": np.deg2rad(0),
            "latitude": np.deg2rad(50),
            "height": 80000,
            "velocity": 7000,
            "path_angle": np.deg2rad(0),
            "heading_angle": np.deg2rad(120),
        },
        'TargetInitStatus': {
            "longitude": _TAR_LON,
            "latitude": _TAR_LAT,
        },
        'MissileEndStatus': {
            "velocity": 2000,
            "height": 25000.0,
            "s": 50000.0,
            "heading_angle": None,
            "t": 2150,
        },
        'PathSpec': _PATH_SPECS[1],
    },
    {
        'MissileInitStatus': {
            "t": 0,
            "longitude": np.deg2rad(0),
            "latitude": np.deg2rad(50),
            "height": 80000,
            "velocity": 7000,
            "path_angle": np.deg2rad(0),
            "heading_angle": np.deg2rad(120),
        },
        'TargetInitStatus': {
            "longitude": _TAR_LON,
            "latitude": _TAR_LAT,
        },
        'MissileEndStatus': {
            "velocity": 2000,
            "height": 25000.0,
            "s": 50000.0,
            "heading_angle": None,
            "t": 2150,
        },
        'PathSpec': _PATH_SPECS[2],
    },
]

# ------------------------------------------------------------
# Guidance parameters
# ------------------------------------------------------------

CONSIDER_SIGMA_MAX = True
K_GAMMA_SGP = 3
ERR_TOL = 3e-4
K_SIGMA = 10
K_ALPHA = 5 * np.pi / 1e7 / 1.8

# Values copied from guide dict directly into control dict
CONTROL_PARAM_LIST = ["m", "attack_angle", "bank_angle"]

# Extra guide parameters to be saved (CSV columns)
GUIDE_SAVE_PARAM = [
    "sigma_max",
    "gamma_sg",
    "s_go",
    "sgo_ref",
    "ref_psi",
    "delta_psi",
    "q",
    "L12D",
    "L12D_E",
    "L12D_alpha",
    "a_tol",
    "aL1",
    "aL2",
    "CL_beg",
    "aL2_orig",
    "ref_sgo",
    "ref_t",
    "ref_L12D",
    "L12D_beg",
    # path shaping diagnostics
    "psi_bias_cmd",
    "psi_bias_w",
    "psi_bias_w_sgo",
    "psi_bias_w_alt",
    "psi_bias_state",
    "cos_delta_psi",
    "L12D_singularity",
    "L12D_den_singularity",
    "L12D_update_hold",
    "sigma_cmd_raw",
    "sigma_cmd_prev",
    "L1_L",
    "BR_times",
    "sgn_ini",
    "beg_k_PN_eff",
    "beg_lateral_gain",
    "beg_sigma_cmd_raw",
    "beg_sigma_cmd_damped",
    "beg_rebound_w",
    "sgo_rebound",

    # TAEM diagnostics / latch outputs
    "taem_h_err",
    "taem_v_err",
    "taem_s_go_err",
    "taem_psi_err",
    "taem_in_box",
    "taem_in_box_strict",
    "taem_near_box",
    "taem_reached",
    "taem_entry_t",
    "taem_t_global",
    "taem_t_local",
    "taem_dwell_count",
    "taem_dwell_max_count",
    "taem_close_score",
    "box_score",
    "taem_box_margin",
    "taem_best_score",
    "taem_best_t_global",
    "taem_best_t_local",
    "taem_reach_mode",
    "taem_psi_tol_rad",
    "stop_on_taem_reached",

    "end_reason",
    "t_local_end",
]

MAX_EBR2_ITER = 5

# ------------------------------------------------------------
# Output paths (required by multi_main.py)
# ------------------------------------------------------------

STORE_DATA = 'store/data_saved/multiSimulation_case.csv'
