# -*- coding: utf-8 -*-
# Minimal recovery source for B1R-P PathSpec.
# Only StatusParams[1]["PathSpec"] is used by multiset_phase2_B1R_from_success_csv_plus_pathspec.py.

StatusParams = [
    {"PathSpec": {"name": "unused_context_0"}},
    {
        "PathSpec": {
            "name": "mis1_merged_winner_case4",
            "policy_family": "merged_winner_case4_case2",
            "psi_bias_deg": -2.0,
            "psi_bias_sgo_on_m": 7000000.0,
            "psi_bias_sgo_off_m": 3600000.0,
            "psi_bias_alt_on_m": 50000.0,
            "psi_bias_alt_off_m": 25000.0,
            "sgn_ini_override": None,
            "terminal_alpha_boost_enable": True,
            "terminal_alpha_boost_deg": 2.25,
            "terminal_alpha_boost_sgo_on_m": 330000.0,
            "terminal_alpha_boost_sgo_full_m": 120000.0,
            "terminal_alpha_boost_h_on_m": 50000.0,
            "terminal_alpha_boost_h_full_m": 35000.0
        }
    },
    {"PathSpec": {"name": "unused_context_2"}}
]
