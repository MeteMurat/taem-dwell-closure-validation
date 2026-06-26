# -*- coding: utf-8 -*-
# EditTime  : 2021-09-29 20:09
# Author    : Of yue
# File      : multiMissileSimInstance.py
# Intro     :

import numpy as np

import multiset as glbs
from entity.missile import Missile
from guidance.MultiGuide import MultiMissileGuidance
from core.MultiMissileSim import MultiMissileSim
from store.dataSave import DataSave
from utils.integral import Integral



def update_taem_event(mis: Missile, global_t: float, dt_guess: float = None) -> None:
    """Update TAEM dwell-based event flags in mis.guide (A2 instrumentation).

    Writes (sticky once reached):
      - taem_in_box, taem_reached
      - taem_dwell_time_s, taem_t_global
      - taem_err_h_m, taem_err_v_mps, taem_err_sgo_m
    """
    end = getattr(glbs, "MissileEndStatus", {}) or {}
    h_ref = float(end.get("height", np.nan))
    v_ref = float(end.get("velocity", np.nan))
    s_ref = float(end.get("s", np.nan))

    tol = getattr(glbs, "TAEM_TOLERANCES", {}) or {}
    h_tol = float(tol.get("height", 500.0))
    v_tol = float(tol.get("velocity", 50.0))
    s_tol = float(tol.get("s", 5000.0))
    dwell_sec = float(getattr(glbs, "TAEM_DWELL_SEC", 3.0))

    prev_t = mis.guide.get("_taem_prev_global_t", None)
    dt = 0.0
    try:
        if prev_t is not None and np.isfinite(prev_t) and np.isfinite(global_t):
            dt = float(global_t - prev_t)
        elif dt_guess is not None and np.isfinite(dt_guess):
            dt = float(dt_guess)
    except Exception:
        dt = 0.0
    if dt < 0:
        dt = 0.0
    if np.isfinite(global_t):
        mis.guide["_taem_prev_global_t"] = float(global_t)

    h = float(getattr(mis.status, "height", np.nan))
    v = float(getattr(mis.status, "velocity", np.nan))
    s_go = float(mis.guide.get("s_go", np.inf))

    h_err = (h - h_ref) if np.isfinite(h_ref) else np.nan
    v_err = (v - v_ref) if np.isfinite(v_ref) else np.nan
    s_err = (s_go - s_ref) if np.isfinite(s_ref) else np.nan

    in_box = (
        np.isfinite(h_err) and np.isfinite(v_err) and np.isfinite(s_err) and
        (abs(h_err) <= h_tol) and (abs(v_err) <= v_tol) and (abs(s_err) <= s_tol)
    )

    reached = bool(mis.guide.get("taem_reached", False))
    dwell = float(mis.guide.get("taem_dwell_time_s", 0.0) or 0.0)

    if not reached:
        dwell = (dwell + dt) if in_box else 0.0
        if in_box and (dwell >= dwell_sec):
            reached = True
            mis.guide["taem_t_global"] = float(global_t) if np.isfinite(global_t) else np.nan

    mis.guide.update({
        "taem_in_box": bool(in_box),
        "taem_reached": bool(reached),
        "taem_dwell_time_s": float(dwell),
        "taem_err_h_m": float(h_err) if np.isfinite(h_err) else np.nan,
        "taem_err_v_mps": float(v_err) if np.isfinite(v_err) else np.nan,
        "taem_err_sgo_m": float(s_err) if np.isfinite(s_err) else np.nan,
    })

class MultiMisSimInstance(MultiMissileSim):
    def __init__(self):
        super(MultiMisSimInstance, self).__init__()

    def init(self, mis=None, tar=None, guide=None, integ=None, db=None):
        if mis is None:
            mis = []
        if tar is None:
            tar = []
        if guide is None:
            guide = MultiMissileGuidance()
        if integ is None:
            integ = Integral()
        self.mis = mis
        self.tar = tar
        self.guide = guide
        self.integral = integ

        # --- DB handling (P3 fix): enforce per-vehicle DataSave instances ---
        # Supported usage:
        #   db is None              -> create N fresh DataSave()
        #   db is a single DB       -> create N fresh DataSave(flush_every=db.flush_every)
        #   db is a list/tuple      -> if len==N and all unique -> use as-is
        #                            else -> rebuild N fresh DataSave(template.flush_every)
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
        # 初始化导弹及目标状态
        for m, t, status in zip(self.mis, self.tar, glbs.StatusParams):
            m.status.change_stat(status["MissileInitStatus"])
            t.status.change_stat(status["TargetInitStatus"])
        # 初始化制导模型
        self.guide.init(self.mis, self.tar, self.guide_params())
    def save_data(self) -> None:
        """Save per-vehicle trajectory samples (MVE-safe).

        Behavior:
        - Save rows while guide_process=True (normal logging).
        - When end_guide becomes True, still save EXACTLY ONE final row (per vehicle),
          even if guide_process has already turned False in that step.

        This prevents CSVs where the terminal sample is missing or shows end_guide=False
        due to logging phase/timing.
        """
        for index, (mis, db) in enumerate(zip(self.mis, self.db)):
            guide_process = bool(mis.guide.get('guide_process', False))
            end_guide = bool(mis.guide.get('end_guide', False))
            final_saved = bool(mis.guide.get('_final_saved', False))

            # Save if (a) in guidance, or (b) just ended and final row not yet saved.
            if (not guide_process) and (not (end_guide and not final_saved)):
                continue

            # TAEM dwell-event channels (A2)
            update_taem_event(mis, global_t=getattr(self, 't', np.nan), dt_guess=getattr(self, 'h', None))

            # Core time & energy
            db_save_dict = {
                'global_t': getattr(self, 't', np.nan),
                'mis_id': index,
                'E': mis.guide.get('E', np.nan),
            }

            # Vehicle state & control
            db_save_dict.update(mis.status.status_dict())
            if isinstance(getattr(mis, 'control', None), dict):
                db_save_dict.update(mis.control)

            # Landing zone (target) info (if aligned)
            if hasattr(self, 'tar') and self.tar is not None and index < len(self.tar):
                tar = self.tar[index]
                lon = getattr(getattr(tar, 'status', tar), 'longitude', np.nan)
                lat = getattr(getattr(tar, 'status', tar), 'latitude', np.nan)
                h   = getattr(getattr(tar, 'status', tar), 'height', 0.0)
                db_save_dict.update({
                    'lz_lon': lon,
                    'lz_lat': lat,
                    'lz_h': h,
                    'lz_id': index,
                })

            # Optional: extra internal guidance params
            db_save_dict.update(self.from_mis_guide(mis, getattr(glbs, 'GUIDE_SAVE_PARAM', [])))

            # Always include TAEM channels even if GUIDE_SAVE_PARAM drifts
            for k, v in mis.guide.items():
                if isinstance(k, str) and k.startswith('taem_'):
                    db_save_dict[k] = v

            # Ensure a generic time column exists for post-processing
            if 't' not in db_save_dict:
                db_save_dict['t'] = getattr(mis.status, 't', getattr(self, 't', 0.0))

            # Terminal/debug flags (always)
            db_save_dict.update({
                'guide_process': guide_process,
                'end_guide': end_guide,
                'end_reason': mis.guide.get('end_reason', 'end_guide' if end_guide else ''),
                'guide_phase': mis.guide.get('guide_phase', ''),
            })

            db.update(db_save_dict)

            if end_guide and not final_saved:
                mis.guide['_final_saved'] = True