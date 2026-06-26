# -*- coding: utf-8 -*-
"""
multiMissileGuideInstance_mis1_state_first_v1.py

Single-vehicle / mis1-focused state-first terminal guidance.

Intent:
- Move away from multi-vehicle lateral-shaping emphasis.
- Prioritize TAEM state capture on (h, v, s_go).
- Strongly suppress heading-driven terminal chasing near TAEM.
- Use dwell/hysteresis-based TAEM detection so "close pass + escape"
  is visible in logs instead of being misread as success.

Important:
- This file intentionally subclasses the visible single-vehicle
  CustomGuidance baseline so it can be used without the unavailable
  multi-vehicle guidance source file.
"""

from __future__ import annotations

import math
import sys
from typing import Any, Dict, Optional

import numpy as np

import multiset as glbs  # type: ignore
sys.modules["settings"] = glbs
import customGuidance as cg  # type: ignore
from customGuidance import CustomGuidance  # type: ignore
from database.Constant import earth as e  # type: ignore
from utils.common import limit_num  # type: ignore


# Force the inherited module to read the active entry configuration from multiset.py
cg.glbs = glbs


class Mis1StateFirstGuidance(CustomGuidance):
    """
    mis1-oriented terminal-capture guidance.

    Design choices:
    - Reuse the proven pre-terminal structure from CustomGuidance.
    - Add a terminal_capture_phase that:
        * suppresses heading pursuit near TAEM,
        * uses alpha primarily for h/v/s_go shaping,
        * rate-limits and smooths bank commands,
        * keeps logging explicit.
    - Replace single-threshold "finished" logic with TAEM dwell + escape logic.
    """

    def __init__(self, case: Dict[str, Any], vehicle_id: int = 1):
        super().__init__()
        self.case = case
        self.vehicle_id = int(vehicle_id)

        # Terminal state-first tuning
        self.terminal_capture_enabled = False
        self.terminal_capture_phase_name = "terminal_capture_phase"

        self.capture_sgo_on_m = 2.40e5
        self.capture_h_on_m = 4.20e4
        self.capture_v_on_mps = 3.10e3

        # TAEM box: entry / exit hysteresis
        self.taem_tol_h_enter_m = 2500.0
        self.taem_tol_v_enter_mps = 130.0
        self.taem_tol_sgo_enter_m = 2.50e4

        self.taem_tol_h_exit_m = 4200.0
        self.taem_tol_v_exit_mps = 190.0
        self.taem_tol_sgo_exit_m = 4.00e4

        self.taem_dwell_required_s = 4.0
        self.taem_dwell_required_count = 3

        # Terminal alpha shaping (state-first)
        self.k_alpha_h = np.deg2rad(1.8)
        self.k_alpha_v = np.deg2rad(1.2)
        self.k_alpha_s = np.deg2rad(2.1)

        self.h_err_norm_m = 5000.0
        self.v_err_norm_mps = 180.0
        self.sgo_err_norm_m = 4.50e4

        self.alpha_capture_min = np.deg2rad(4.0)

        # Terminal bank handling
        self.bank_deadband_rad = np.deg2rad(0.35)
        self.bank_rate_limit_radps = np.deg2rad(3.0)
        self.bank_ema = 0.22
        self.heading_sigma_gain = 0.18  # small, intentionally suppressed
        self.near_taem_heading_floor = 0.08

        # Escape / post-pass diagnostics
        self.escape_rebound_margin_m = 2.5e4
        self.escape_end_delay_s = 18.0

        self.last_taem_in_box = False
        self.last_taem_eval_t = None
        self.escape_timer_start = None

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def init(self, missile, target=None, meta=None):
        if meta is None:
            meta = {}

        # Case-specific terminal target
        end_status = self.case["MissileEndStatus"]
        glbs.MissileEndStatus = end_status  # for inherited helper compatibility

        self.alpha_max = missile.p.alpha_max
        self.alpha_sgp = missile.p.max_L2D_alpha
        self.alpha_2 = np.deg2rad(6.0)

        self.V_TAEM = float(end_status["velocity"])
        self.H_TAEM = float(end_status["height"])
        self.E_TAEM = e.E(self.V_TAEM, self.H_TAEM)
        self.S_TAEM = float(end_status["s"])

        self.guide_mode = "descent_phase1"
        self.EBR1 = (missile.E + self.E_alpha) / 2.0
        self.EBR2 = self.E_alpha

        self.err_tol = float(getattr(glbs, "ERR_TOL", 1e-2))
        self.kgamma = float(getattr(glbs, "K_GAMMA", 3))
        self.k_gamma_sgp = float(getattr(glbs, "K_GAMMA_SGP", 3))
        self.k_gamma_aap = float(getattr(glbs, "K_GAMMA_AAP", 3))
        self.k_sigma = float(getattr(glbs, "K_SIGMA", -50))
        self.k_alpha = float(getattr(glbs, "K_ALPHA", 5 * np.pi / 1.8e7))
        self.control_param_list = getattr(
            glbs,
            "CONTROL_PARAM_LIST",
            ["L", "D", "m", "attack_angle", "bank_angle"],
        )

        great_circle_heading = cg.heading_angle(
            missile.status.longitude,
            missile.status.latitude,
            target.status.longitude,
            target.status.latitude,
        )
        self.sgn = 1 if great_circle_heading[0] > missile.status.heading_angle else -1

        missile.guide["L2Dbsl_TAEM"] = cg.cav_corridor.L2D_E(self.E_TAEM)

        # Explicit logging / latches
        missile.guide.update(
            {
                "guide_phase": self.guide_mode,
                "guide_process": True,
                "terminal_capture_active": False,
                "taem_in_box": False,
                "taem_reached": False,
                "taem_dwell_s": 0.0,
                "taem_dwell_count": 0,
                "taem_t_first_in_box": np.nan,
                "taem_t_reached": np.nan,
                "taem_h_err": np.nan,
                "taem_v_err": np.nan,
                "taem_s_go_err": np.nan,
                "taem_h_norm": np.nan,
                "taem_v_norm": np.nan,
                "taem_sgo_norm": np.nan,
                "taem_box_score": 0.0,
                "taem_capture_weight": 0.0,
                "taem_heading_weight": 1.0,
                "close_pass_escape": False,
                "escape_rebound_m": np.nan,
                "s_go_min_running": np.inf,
                "sigma_cmd_prev": 0.0,
                "sigma_cmd_raw": 0.0,
                "sigma_cmd_rate_limited": 0.0,
                "sigma_cmd_smoothed": 0.0,
                "end_reason": "",
                "_final_saved": False,
            }
        )

    # ------------------------------------------------------------------
    # Per-step parse + TAEM metrics
    # ------------------------------------------------------------------
    def parse_param(self, mis, tar, meta=None):
        if meta is None:
            meta = {}
        super().parse_param(mis, tar, meta)

        h_err = float(mis.guide["h"] - self.H_TAEM)
        v_err = float(mis.guide["v"] - self.V_TAEM)
        sgo_err = float(mis.guide["s_go"] - self.S_TAEM)

        h_norm = float(np.clip(h_err / self.h_err_norm_m, -2.0, 2.0))
        v_norm = float(np.clip(v_err / self.v_err_norm_mps, -2.0, 2.0))
        sgo_norm = float(np.clip(sgo_err / self.sgo_err_norm_m, -2.0, 2.0))

        score = float(
            (1.0 - min(abs(h_err) / max(self.taem_tol_h_exit_m, 1.0), 1.0))
            + (1.0 - min(abs(v_err) / max(self.taem_tol_v_exit_mps, 1.0), 1.0))
            + (1.0 - min(abs(sgo_err) / max(self.taem_tol_sgo_exit_m, 1.0), 1.0))
        )

        # Running minimum s_go and rebound diagnostic
        sgo_min_running = float(min(mis.guide.get("s_go_min_running", np.inf), mis.guide["s_go"]))
        rebound = float(mis.guide["s_go"] - sgo_min_running) if np.isfinite(sgo_min_running) else np.nan

        capture_weight = self._capture_weight(mis)
        heading_weight = self._heading_weight(mis)

        mis.guide.update(
            {
                "taem_h_err": h_err,
                "taem_v_err": v_err,
                "taem_s_go_err": sgo_err,
                "taem_h_norm": h_norm,
                "taem_v_norm": v_norm,
                "taem_sgo_norm": sgo_norm,
                "taem_box_score": score,
                "taem_capture_weight": capture_weight,
                "taem_heading_weight": heading_weight,
                "s_go_min_running": sgo_min_running,
                "escape_rebound_m": rebound,
            }
        )

        self._update_taem_dwell(mis, meta)

    def _capture_weight(self, mis) -> float:
        s_go = float(mis.guide.get("s_go", np.inf))
        h = float(mis.guide.get("h", np.inf))
        v = float(mis.guide.get("v", np.inf))

        ws = 1.0 - np.clip((s_go - self.S_TAEM) / max(self.capture_sgo_on_m - self.S_TAEM, 1.0), 0.0, 1.0)
        wh = 1.0 - np.clip((h - self.H_TAEM) / max(self.capture_h_on_m - self.H_TAEM, 1.0), 0.0, 1.0)
        wv = 1.0 - np.clip((v - self.V_TAEM) / max(self.capture_v_on_mps - self.V_TAEM, 1.0), 0.0, 1.0)

        return float(np.clip(0.50 * ws + 0.30 * wh + 0.20 * wv, 0.0, 1.0))

    def _heading_weight(self, mis) -> float:
        cw = float(mis.guide.get("taem_capture_weight", 0.0))
        return float(np.clip(1.0 - 0.92 * cw, self.near_taem_heading_floor, 1.0))

    def _taem_in_box_entry(self, mis) -> bool:
        return (
            abs(float(mis.guide["taem_h_err"])) <= self.taem_tol_h_enter_m
            and abs(float(mis.guide["taem_v_err"])) <= self.taem_tol_v_enter_mps
            and abs(float(mis.guide["taem_s_go_err"])) <= self.taem_tol_sgo_enter_m
        )

    def _taem_in_box_exit(self, mis) -> bool:
        return (
            abs(float(mis.guide["taem_h_err"])) <= self.taem_tol_h_exit_m
            and abs(float(mis.guide["taem_v_err"])) <= self.taem_tol_v_exit_mps
            and abs(float(mis.guide["taem_s_go_err"])) <= self.taem_tol_sgo_exit_m
        )

    def _update_taem_dwell(self, mis, meta=None):
        if meta is None:
            meta = {}

        t_now = float(meta.get("t", getattr(mis.status, "t", 0.0)))
        if self.last_taem_eval_t is None:
            dt = 0.0
        else:
            dt = max(0.0, t_now - float(self.last_taem_eval_t))
        self.last_taem_eval_t = t_now

        prev_in_box = bool(mis.guide.get("taem_in_box", False))
        if prev_in_box:
            in_box = self._taem_in_box_exit(mis)
        else:
            in_box = self._taem_in_box_entry(mis)

        if in_box:
            if not prev_in_box and not np.isfinite(mis.guide.get("taem_t_first_in_box", np.nan)):
                mis.guide["taem_t_first_in_box"] = t_now
            mis.guide["taem_dwell_s"] = float(mis.guide.get("taem_dwell_s", 0.0) + dt)
            mis.guide["taem_dwell_count"] = int(mis.guide.get("taem_dwell_count", 0) + 1)
        else:
            mis.guide["taem_dwell_s"] = 0.0
            mis.guide["taem_dwell_count"] = 0

        reached = bool(mis.guide.get("taem_reached", False))
        if (not reached) and in_box:
            if (
                float(mis.guide["taem_dwell_s"]) >= self.taem_dwell_required_s
                or int(mis.guide["taem_dwell_count"]) >= self.taem_dwell_required_count
            ):
                mis.guide["taem_reached"] = True
                mis.guide["taem_t_reached"] = t_now

        mis.guide["taem_in_box"] = bool(in_box)

    # ------------------------------------------------------------------
    # Phase management
    # ------------------------------------------------------------------
    def should_enter_terminal_capture(self, mis) -> bool:
        if bool(mis.guide.get("terminal_capture_active", False)):
            return True

        if float(mis.guide.get("s_go", np.inf)) <= self.capture_sgo_on_m:
            return True
        if float(mis.guide.get("h", np.inf)) <= self.capture_h_on_m and float(mis.guide.get("v", np.inf)) <= self.capture_v_on_mps:
            return True
        if float(mis.guide.get("taem_capture_weight", 0.0)) >= 0.55:
            return True
        return False

    def steady_glide_phase(self, mis, tar=None, meta=None):
        if meta is None:
            meta = {}
        self.before_phase(mis, tar, meta)

        if self.should_enter_terminal_capture(mis):
            self.guide_mode = self.terminal_capture_phase_name
            mis.guide["terminal_capture_active"] = True
            self.terminal_capture_phase(mis, tar, meta)
            return

        alpha_bsl = self.attack_angle_plan(mis.guide["E"])
        sigma_bsl = self.sigma_bsl(mis, tar, meta)
        gamma_sg = mis.guide["gamma_sg"]
        sigma_max = self.sigma_max(mis, tar, meta)
        alpha_cmd, sigma_cmd = self.TDCT(alpha_bsl, sigma_bsl, gamma_sg - mis.status.path_angle)
        sigma_cmd = limit_num(sigma_cmd, abs_limit=sigma_max)
        mis.guide["attack_angle"] = alpha_cmd
        mis.guide["bank_angle"] = sigma_cmd

        if mis.guide["E"] < self.EBR2:
            mis.guide["sgo_EBR2"] = mis.guide["s_go"]
            self.guide_mode = "altitude_adjustment_phase"

    def altitude_adjustment_phase(self, mis, tar=None, meta=None):
        if meta is None:
            meta = {}
        self.before_phase(mis, tar, meta)

        if self.should_enter_terminal_capture(mis):
            self.guide_mode = self.terminal_capture_phase_name
            mis.guide["terminal_capture_active"] = True
            self.terminal_capture_phase(mis, tar, meta)
            return

        # Fallback to inherited AAP behavior when still outside capture conditions
        alpha_bsl = self.attack_angle_plan(mis.guide["E"])
        sigma_bsl = self.sigma_bsl(mis, tar, meta)
        f_sgo_ref = mis.guide.get("f_sgo_ref", None)
        sgo_ref = f_sgo_ref(mis.guide["E"]) if f_sgo_ref else mis.guide["s_go"]
        mis.guide["sgo_ref"] = sgo_ref
        delta_gamma = mis.guide["gamma_sg"] - mis.status.path_angle

        alpha_cmd = alpha_bsl + self.k_alpha * (mis.guide["s_go"] - sgo_ref)
        sigma_cmd = sigma_bsl - math.sin(sigma_bsl) * self.k_gamma_aap * delta_gamma / self.alpha_sgp

        mis.guide["attack_angle"] = alpha_cmd
        mis.guide["bank_angle"] = sigma_cmd

    def _safe_float(self, x, default=0.0):
        """Return finite float; otherwise default."""
        try:
            if x is None:
                return float(default)
            y = float(x)
            if not np.isfinite(y):
                return float(default)
            return y
        except Exception:
            return float(default)

    def _sigma_bsl_safe(self, mis, tar=None, meta=None):
        """Safe nominal bank baseline for terminal capture."""
        if meta is None:
            meta = {}
        candidates = []
        try:
            candidates.append(self.sigma_bsl(mis, tar, meta))
        except Exception:
            pass
        old_mode = getattr(self, "guide_mode", None)
        for mode in ("altitude_adjustment_phase", "steady_glide_phase"):
            try:
                self.guide_mode = mode
                candidates.append(self.sigma_bsl(mis, tar, meta))
            except Exception:
                pass
            finally:
                self.guide_mode = old_mode
        candidates.extend([
            mis.guide.get("bank_angle", None),
            mis.guide.get("sigma_cmd_prev", None),
            mis.control.get("bank_angle", None) if isinstance(getattr(mis, "control", None), dict) else None,
            0.0,
        ])
        for c in candidates:
            val = self._safe_float(c, np.nan)
            if np.isfinite(val):
                return val
        return 0.0

    def _sigma_max_safe(self, mis, tar=None, meta=None):
        try:
            val = self.sigma_max(mis, tar, meta)
        except Exception:
            val = getattr(self, "sigma_capture_max", np.deg2rad(70.0))
        val = abs(self._safe_float(val, getattr(self, "sigma_capture_max", np.deg2rad(70.0))))
        if val <= 1e-6:
            val = abs(getattr(self, "sigma_capture_max", np.deg2rad(70.0)))
        return float(val)

    def terminal_capture_phase(self, mis, tar=None, meta=None):
        if meta is None:
            meta = {}

        mis.guide["terminal_capture_active"] = True

        alpha_bsl = float(self.attack_angle_plan(mis.guide["E"]))
        sigma_nom = self._sigma_bsl_safe(mis, tar, meta)
        sigma_max = self._sigma_max_safe(mis, tar, meta)

        h_norm = float(mis.guide.get("taem_h_norm", 0.0))
        v_norm = float(mis.guide.get("taem_v_norm", 0.0))
        sgo_norm = float(mis.guide.get("taem_sgo_norm", 0.0))
        heading_weight = float(mis.guide.get("taem_heading_weight", 1.0))
        capture_weight = float(mis.guide.get("taem_capture_weight", 0.0))
        delta_psi = float(mis.guide.get("delta_psi", 0.0))

        # State-first alpha law:
        # - too low  (h_err < 0) -> increase alpha
        # - too slow (v_err < 0) -> decrease alpha
        # - too far  (s_go_err > 0) -> decrease alpha to stretch range
        alpha_cmd = (
            alpha_bsl
            - self.k_alpha_h * h_norm
            + self.k_alpha_v * v_norm
            - self.k_alpha_s * sgo_norm
        )
        alpha_cmd = float(np.clip(alpha_cmd, self.alpha_capture_min, self.alpha_max))

        # Heading is intentionally suppressed near TAEM.
        # Also shrink nominal bank magnitude as capture_weight grows.
        sigma_scale = float(np.clip(1.0 - 0.72 * capture_weight, 0.18, 1.0))
        if float(mis.guide.get("taem_s_go_err", 0.0)) < 0.0:
            # Slightly more bank authority if already overshooting s_go.
            sigma_scale = min(1.0, sigma_scale + 0.12)

        sigma_raw = sigma_nom * sigma_scale + self.heading_sigma_gain * heading_weight * delta_psi

        # Conservative damping toward zero when essentially inside the box
        if bool(mis.guide.get("taem_in_box", False)):
            sigma_raw *= 0.35

        sigma_cmd = self._shape_sigma_command(mis, sigma_raw, sigma_max, meta)

        mis.guide.update(
            {
                "attack_angle": alpha_cmd,
                "bank_angle": sigma_cmd,
                "sigma_cmd_raw": sigma_raw,
                "guide_phase": self.terminal_capture_phase_name,
            }
        )

    def _shape_sigma_command(self, mis, sigma_raw: float, sigma_max: float, meta=None) -> float:
        if meta is None:
            meta = {}
        dt_raw = meta.get("min_h", None)
        if dt_raw is None:
            dt_raw = getattr(meta.get("simulation", None), "h", 0.1)
        dt = max(self._safe_float(dt_raw, 0.1), 1e-3)

        prev = self._safe_float(mis.guide.get("sigma_cmd_prev", mis.control.get("bank_angle", 0.0)), 0.0)
        sigma_max = self._safe_float(abs(sigma_max), getattr(self, "sigma_capture_max", np.deg2rad(70.0)))
        sigma_raw = self._safe_float(sigma_raw, prev)

        sigma_limited = float(limit_num(sigma_raw, abs_limit=sigma_max))
        max_delta = self.bank_rate_limit_radps * dt
        sigma_rate = prev + float(np.clip(sigma_limited - prev, -max_delta, max_delta))

        if abs(sigma_rate - prev) < self.bank_deadband_rad:
            sigma_rate = prev

        sigma_smoothed = (1.0 - self.bank_ema) * prev + self.bank_ema * sigma_rate
        sigma_smoothed = float(limit_num(sigma_smoothed, abs_limit=sigma_max))

        mis.guide["sigma_cmd_prev"] = sigma_smoothed
        mis.guide["sigma_cmd_rate_limited"] = sigma_rate
        mis.guide["sigma_cmd_smoothed"] = sigma_smoothed

        return sigma_smoothed

    # ------------------------------------------------------------------
    # Guidance wrapper
    # ------------------------------------------------------------------
    def guide(self, mis, tar=None, meta=None):
        if meta is None:
            meta = {}
        self.parse_param(mis, tar, meta)
        self.integral_accurate(mis, tar, meta)

        if self.guide_mode == self.terminal_capture_phase_name:
            self.terminal_capture_phase(mis, tar, meta)
        else:
            self.guide_phase[self.guide_mode](mis, tar, meta)

        mis.guide["guide_phase"] = self.guide_mode
        self.guide2control(mis, tar, meta)

    # ------------------------------------------------------------------
    # Termination logic
    # ------------------------------------------------------------------
    def end_guide(self, mis, tar=None, meta=None, flag=False):
        if meta is None:
            meta = {}

        if getattr(self, "end_flag", False):
            return True

        if flag:
            self.end_flag = True
            mis.guide["guide_process"] = False
            mis.guide["end_guide"] = True
            mis.guide["end_reason"] = "forced_flag"
            return True

        t_now = float(meta.get("t", getattr(mis.status, "t", 0.0)))
        h = float(getattr(mis.status, "height", np.inf))

        # Primary success condition: real TAEM dwell reached
        if bool(mis.guide.get("taem_reached", False)):
            self.end_flag = True
            mis.guide["end_reason"] = "taem_dwell_reached"

        # Hard physical stop
        elif h <= float(getattr(glbs, "GROUND_H", 5.0)):
            self.end_flag = True
            mis.guide["end_reason"] = "ground_contact"

        # Close-pass escape detection:
        # after the running minimum, if s_go rebounds substantially and we have already
        # been in capture mode for a while, terminate as explicit escape.
        else:
            rebound = float(mis.guide.get("escape_rebound_m", np.nan))
            if bool(mis.guide.get("terminal_capture_active", False)) and np.isfinite(rebound):
                if rebound >= self.escape_rebound_margin_m:
                    if self.escape_timer_start is None:
                        self.escape_timer_start = t_now
                    elif (t_now - self.escape_timer_start) >= self.escape_end_delay_s:
                        self.end_flag = True
                        mis.guide["close_pass_escape"] = True
                        mis.guide["end_reason"] = "close_pass_escape"
                else:
                    self.escape_timer_start = None

        mis.guide["guide_process"] = not bool(self.end_flag)
        mis.guide["end_guide"] = bool(self.end_flag)
        if not mis.guide.get("end_reason"):
            mis.guide["end_reason"] = ""

        return bool(self.end_flag)



class Mis1StateFirstGuidanceV8Success(Mis1StateFirstGuidance):
    """V8.1 success-first wrapper over the only run family that produced a real TAEM dwell.

    This class intentionally preserves the V1 dynamics/control law. It only changes
    success plumbing: latch once TAEM dwell is reached and terminate cleanly.
    """

    def __init__(self, case: Dict[str, Any], vehicle_id: int = 1):
        super().__init__(case=case, vehicle_id=vehicle_id)
        self._v8_success_already_emitted = False

    def init(self, missile, target=None, meta=None):
        super().init(missile, target, meta)
        self._v8_success_already_emitted = False
        missile.guide.update({
            "taem_reached_event": False,
            "taem_reached_ever": bool(missile.guide.get("taem_reached", False)),
            "taem_success_latched": False,
            "taem_fail_latched": False,
            "taem_t_global": np.nan,
            "taem_t_local": np.nan,
            "box_score": missile.guide.get("taem_box_score", 0.0),
            "success_mode": "v8_v1_latch_only",
        })

    def _latch_success_if_needed(self, mis, meta=None):
        if meta is None:
            meta = {}
        reached = bool(mis.guide.get("taem_reached", False))
        if not reached:
            mis.guide["taem_reached_event"] = False
            mis.guide["taem_reached_ever"] = bool(mis.guide.get("taem_reached_ever", False))
            mis.guide["taem_success_latched"] = bool(mis.guide.get("taem_success_latched", False))
            mis.guide["box_score"] = mis.guide.get("taem_box_score", 0.0)
            return False

        # Keep the event pulse visible on the final saved row.
        # In the previous V8 build, _latch_success_if_needed() could be called
        # more than once in the same guidance step. The first call set
        # taem_reached_event=True, but the second call immediately overwrote it
        # with False because taem_success_latched was already True.  The CSV then
        # contained taem_success_latched=True but taem_reached_event=False, which
        # confused compare scripts that prioritize the explicit event column.
        was_latched = bool(mis.guide.get("taem_success_latched", False))
        event_already_marked_this_step = bool(mis.guide.get("taem_reached_event", False))
        first_event = (not was_latched) or event_already_marked_this_step
        t_global = float(meta.get("t", getattr(mis.status, "t", np.nan)))
        t_local = float(getattr(mis.status, "t", t_global))

        mis.guide["taem_reached_event"] = bool(first_event)
        mis.guide["taem_reached_ever"] = True
        mis.guide["taem_success_latched"] = True
        mis.guide["taem_fail_latched"] = False
        if first_event or not np.isfinite(float(mis.guide.get("taem_t_global", np.nan))):
            mis.guide["taem_t_global"] = t_global
            mis.guide["taem_t_local"] = t_local
        mis.guide["box_score"] = mis.guide.get("taem_box_score", 0.0)
        mis.guide["end_reason"] = "taem_dwell_reached"
        mis.guide["guide_process"] = False
        mis.guide["end_guide"] = True
        self.end_flag = True
        return True

    def _update_taem_dwell(self, mis, meta=None):
        super()._update_taem_dwell(mis, meta)
        self._latch_success_if_needed(mis, meta)

    def guide(self, mis, tar=None, meta=None):
        super().guide(mis, tar, meta)
        self._latch_success_if_needed(mis, meta)

    def one_step_guide(self, missile, target=None, meta=None):
        if meta is None:
            meta = {}
        self.guide(missile, target, meta)
        if self._latch_success_if_needed(missile, meta):
            return False
        if self.end_guide(missile, target, meta):
            return False
        return True

    def end_guide(self, mis, tar=None, meta=None, flag=False):
        if meta is None:
            meta = {}
        if flag:
            self.end_flag = True
            mis.guide["guide_process"] = False
            mis.guide["end_guide"] = True
            mis.guide["end_reason"] = "forced_flag"
            return True
        if self._latch_success_if_needed(mis, meta):
            return True
        return super().end_guide(mis, tar, meta, flag=False)
