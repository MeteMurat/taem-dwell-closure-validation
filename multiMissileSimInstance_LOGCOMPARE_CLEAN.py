# -*- coding: utf-8 -*-
"""TAEM-aware multiMissileSimInstance replacement.

Purpose
-------
Adds a reproducible TAEM event/logging layer at simulation-save time.
This patch does **not** require the missing multiMissileGuideInstance source
in order to start producing stable TAEM labels in the CSV.

Key behavior
------------
- Computes TAEM errors against per-vehicle MissileEndStatus targets.
- Computes an in-box flag using configurable tolerances.
- Uses dwell-based detection (N consecutive in-box samples).
- Emits a one-row pulse ``taem_reached=True`` at first confirmation.
- Persists ``taem_reached_ever`` plus first-reach timestamps afterward.
- Optionally can end the run on TAEM confirmation if enabled in multiset.py.
"""

from __future__ import annotations

import math
from typing import Any, Dict

import numpy as np

import multiset as glbs
from entity.missile import Missile
from guidance.MultiGuide import MultiMissileGuidance
from core.MultiMissileSim import MultiMissileSim
from store.dataSave import DataSave
from utils.integral import Integral


class MultiMisSimInstance(MultiMissileSim):
    def __init__(self):
        super(MultiMisSimInstance, self).__init__()

    def init(self, mis=[], tar=[], guide=MultiMissileGuidance(), integ=Integral(), db=None):
        self.mis = mis
        self.tar = tar
        self.guide = guide
        self.integral = integ

        def _flush_every_from(obj, default: int = 5000) -> int:
            try:
                fe = int(getattr(obj, "flush_every", default))
                return int(max(1, fe))
            except Exception:
                return int(default)

        def _new_db_like(template=None) -> DataSave:
            return DataSave(flush_every=_flush_every_from(template)) if template is not None else DataSave()

        n = len(mis)
        if db is None:
            self.db = [_new_db_like(None) for _ in range(n)]
        elif hasattr(db, "update"):
            self.db = [_new_db_like(db) for _ in range(n)]
        elif isinstance(db, (list, tuple)):
            db_list = list(db)
            if len(db_list) == n and all(hasattr(x, "update") for x in db_list) and len(set(map(id, db_list))) == n:
                self.db = db_list
            else:
                template = db_list[0] if (len(db_list) > 0 and hasattr(db_list[0], "update")) else None
                self.db = [_new_db_like(template) for _ in range(n)]
        else:
            self.db = [_new_db_like(None) for _ in range(n)]

        for m, t, status in zip(self.mis, self.tar, glbs.StatusParams):
            m.status.change_stat(status["MissileInitStatus"])
            t.status.change_stat(status["TargetInitStatus"])
        self.guide.init(self.mis, self.tar, self.guide_params())

    @staticmethod
    def _safe_float(v: Any, default=np.nan) -> float:
        try:
            if v is None:
                return float(default)
            if isinstance(v, np.ndarray):
                if v.size == 0:
                    return float(default)
                v = v.reshape(-1)[-1]
            return float(v)
        except Exception:
            return float(default)

    @staticmethod
    def _wrap_angle_rad(x: float) -> float:
        if not np.isfinite(x):
            return float("nan")
        return (x + math.pi) % (2.0 * math.pi) - math.pi

    def _vehicle_status_cfg(self, index: int) -> Dict[str, Any]:
        try:
            return dict(glbs.StatusParams[index])
        except Exception:
            return {}

    def _current_t_local(self, mis: Missile, global_t: float) -> float:
        t_local = self._safe_float(getattr(getattr(mis, "status", None), "t", np.nan), np.nan)
        if np.isfinite(t_local):
            return t_local
        launch_t = self._safe_float(mis.guide.get("launch_time", np.nan), np.nan)
        if np.isfinite(launch_t):
            return float(global_t - launch_t)
        return float(global_t)

    def _compute_taem_snapshot(self, mis: Missile, index: int, global_t: float) -> Dict[str, Any]:
        cfg = self._vehicle_status_cfg(index)
        end_cfg = dict(cfg.get("MissileEndStatus", {}))

        h_ref = self._safe_float(end_cfg.get("height", np.nan), np.nan)
        v_ref = self._safe_float(end_cfg.get("velocity", np.nan), np.nan)
        s_ref = self._safe_float(end_cfg.get("s", np.nan), np.nan)
        psi_ref = self._safe_float(end_cfg.get("heading_angle", np.nan), np.nan)
        gamma_ref = self._safe_float(end_cfg.get("path_angle", np.nan), np.nan)

        h = self._safe_float(getattr(mis.status, "height", np.nan), np.nan)
        v = self._safe_float(getattr(mis.status, "velocity", np.nan), np.nan)
        psi = self._safe_float(getattr(mis.status, "heading_angle", np.nan), np.nan)
        gamma = self._safe_float(getattr(mis.status, "path_angle", np.nan), np.nan)
        s_go = self._safe_float(mis.guide.get("s_go", np.nan), np.nan)

        tol_h = self._safe_float(
            end_cfg.get("height_tol", getattr(glbs, "TAEM_TOL_H_M", np.nan)),
            np.nan,
        )
        tol_v = self._safe_float(getattr(glbs, "TAEM_TOL_V_MPS", np.nan), np.nan)
        tol_sgo = self._safe_float(getattr(glbs, "TAEM_TOL_SGO_M", np.nan), np.nan)

        use_heading = bool(getattr(glbs, "TAEM_USE_HEADING", False)) and np.isfinite(psi_ref)
        use_gamma = bool(getattr(glbs, "TAEM_USE_PATH_ANGLE", False)) and np.isfinite(gamma_ref)
        tol_psi = math.radians(self._safe_float(getattr(glbs, "TAEM_TOL_HEADING_DEG", np.nan), np.nan))
        tol_gamma = math.radians(self._safe_float(getattr(glbs, "TAEM_TOL_PATH_ANGLE_DEG", np.nan), np.nan))

        h_err = h - h_ref if np.isfinite(h) and np.isfinite(h_ref) else np.nan
        v_err = v - v_ref if np.isfinite(v) and np.isfinite(v_ref) else np.nan
        s_err = s_go - s_ref if np.isfinite(s_go) and np.isfinite(s_ref) else np.nan
        psi_err = self._wrap_angle_rad(psi - psi_ref) if use_heading and np.isfinite(psi) else np.nan
        gamma_err = self._wrap_angle_rad(gamma - gamma_ref) if use_gamma and np.isfinite(gamma) else np.nan

        checks = []
        if np.isfinite(h_err) and np.isfinite(tol_h):
            checks.append(abs(h_err) <= tol_h)
        if np.isfinite(v_err) and np.isfinite(tol_v):
            checks.append(abs(v_err) <= tol_v)
        if np.isfinite(s_err) and np.isfinite(tol_sgo):
            checks.append(abs(s_err) <= tol_sgo)
        if use_heading and np.isfinite(psi_err) and np.isfinite(tol_psi):
            checks.append(abs(psi_err) <= tol_psi)
        if use_gamma and np.isfinite(gamma_err) and np.isfinite(tol_gamma):
            checks.append(abs(gamma_err) <= tol_gamma)

        in_box = bool(len(checks) > 0 and all(checks))
        dwell_steps_req = int(max(1, int(getattr(glbs, "TAEM_DWELL_STEPS", 4))))
        prev_count = int(mis.guide.get("_taem_dwell_count", 0))
        prev_t = self._safe_float(mis.guide.get("_taem_prev_global_t", np.nan), np.nan)
        prev_dwell_s = self._safe_float(mis.guide.get("_taem_dwell_s", 0.0), 0.0)
        dt = 0.0 if not np.isfinite(prev_t) else max(0.0, float(global_t - prev_t))

        if in_box:
            dwell_count = prev_count + 1
            dwell_s = prev_dwell_s + dt
        else:
            dwell_count = 0
            dwell_s = 0.0

        already_reached = bool(mis.guide.get("_taem_reached_ever", False))
        just_reached = (not already_reached) and (dwell_count >= dwell_steps_req)
        reached_ever = already_reached or just_reached

        t_local = self._current_t_local(mis, global_t)
        if just_reached:
            mis.guide["_taem_t_global"] = float(global_t)
            mis.guide["_taem_t_local"] = float(t_local)
            mis.guide["_taem_reached_ever"] = True
        taem_t_global = self._safe_float(mis.guide.get("_taem_t_global", np.nan), np.nan)
        taem_t_local = self._safe_float(mis.guide.get("_taem_t_local", np.nan), np.nan)

        mis.guide["_taem_prev_global_t"] = float(global_t)
        mis.guide["_taem_dwell_count"] = int(dwell_count)
        mis.guide["_taem_dwell_s"] = float(dwell_s)
        mis.guide["_taem_reached_ever"] = bool(reached_ever)

        if just_reached and bool(getattr(glbs, "TAEM_END_ON_REACHED", False)):
            mis.guide["end_guide"] = True
            mis.guide["end_reason"] = "taem_reached"

        out = {
            "t_local": float(t_local),
            "taem_h_ref": h_ref,
            "taem_v_ref": v_ref,
            "taem_s_go_ref": s_ref,
            "taem_heading_ref": psi_ref,
            "taem_gamma_ref": gamma_ref,
            "taem_h_tol": tol_h,
            "taem_v_tol": tol_v,
            "taem_s_go_tol": tol_sgo,
            "taem_h_err": h_err,
            "taem_v_err": v_err,
            "taem_s_go_err": s_err,
            "taem_err_h": h_err,
            "taem_err_v": v_err,
            "taem_err_sgo": s_err,
            "taem_err_psi": psi_err,
            "taem_err_gamma": gamma_err,
            "taem_in_box": bool(in_box),
            "taem_dwell_count": int(dwell_count),
            "taem_dwell_s": float(dwell_s),
            "taem_dwell_steps_req": int(dwell_steps_req),
            "taem_reached": bool(just_reached),
            "taem_reached_ever": bool(reached_ever),
            "taem_t_global": taem_t_global,
            "taem_t_local": taem_t_local,
        }
        return out

    def save_data(self) -> None:
        """Save per-vehicle trajectory samples.

        Cleanup rules
        -------------
        - Guidance is the single source of TAEM truth.
        - Once a vehicle is ended and its final state has been written, do not
          emit further frozen duplicate rows.
        - Keep backward-compatible alias columns for compare scripts.
        """
        for index, (mis, db) in enumerate(zip(self.mis, self.db)):
            guide_process = bool(mis.guide.get('guide_process', False))
            end_guide = bool(mis.guide.get('end_guide', False))
            final_saved = bool(mis.guide.get('_final_saved', False))

            # Hard stop for post-end duplicate logging.
            if end_guide and final_saved:
                continue

            if (not guide_process) and (not end_guide):
                continue

            global_t = self._safe_float(getattr(self, 't', np.nan), np.nan)
            t_local = self._current_t_local(mis, global_t)
            db_save_dict = {
                'global_t': global_t,
                'mis_id': index,
                'E': mis.guide.get('E', np.nan),
                't_local': float(t_local),
            }

            db_save_dict.update(mis.status.status_dict())
            if isinstance(getattr(mis, 'control', None), dict):
                db_save_dict.update(mis.control)

            if hasattr(self, 'tar') and self.tar is not None and index < len(self.tar):
                tar = self.tar[index]
                lon = getattr(getattr(tar, 'status', tar), 'longitude', np.nan)
                lat = getattr(getattr(tar, 'status', tar), 'latitude', np.nan)
                h = getattr(getattr(tar, 'status', tar), 'height', 0.0)
                db_save_dict.update({
                    'lz_lon': lon,
                    'lz_lat': lat,
                    'lz_h': h,
                    'lz_id': index,
                })

            db_save_dict.update(self.from_mis_guide(mis, getattr(glbs, 'GUIDE_SAVE_PARAM', [])))

            # Guidance-owned TAEM fields: copy through directly.
            for key in (
                'taem_in_box', 'taem_reached', 'taem_reached_ever', 'taem_reached_event',
                'taem_t_global', 'taem_t_local', 'taem_entry_t',
                'taem_h_err', 'taem_v_err', 'taem_s_go_err', 'taem_psi_err',
                'taem_dwell_count', 'taem_dwell_max_count', 'taem_reach_mode',
                'taem_h_tol_m', 'taem_v_tol', 'taem_sgo_tol_m', 'taem_psi_tol_rad',
                'taem_close_score', 'box_score', 'taem_box_margin',
                'taem_best_score', 'taem_best_t_global', 'taem_best_t_local',
            ):
                if key in mis.guide:
                    db_save_dict[key] = mis.guide.get(key)

            # Backward-compatible aliases expected by analysis scripts.
            if 'taem_h_err' in db_save_dict and 'taem_err_h' not in db_save_dict:
                db_save_dict['taem_err_h'] = db_save_dict['taem_h_err']
            if 'taem_v_err' in db_save_dict and 'taem_err_v' not in db_save_dict:
                db_save_dict['taem_err_v'] = db_save_dict['taem_v_err']
            if 'taem_s_go_err' in db_save_dict and 'taem_err_sgo' not in db_save_dict:
                db_save_dict['taem_err_sgo'] = db_save_dict['taem_s_go_err']

            if 't' not in db_save_dict:
                db_save_dict['t'] = getattr(mis.status, 't', getattr(self, 't', 0.0))

            db_save_dict.update({
                'guide_process': guide_process,
                'end_guide': end_guide,
                'end_reason': mis.guide.get('end_reason', 'end_guide' if end_guide else ''),
                'guide_phase': mis.guide.get('guide_phase', ''),
            })

            db.update(db_save_dict)

            if end_guide and not final_saved:
                mis.guide['_final_saved'] = True

                mis.guide['_final_saved'] = True
