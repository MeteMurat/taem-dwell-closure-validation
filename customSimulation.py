import numpy as np

import settings as glbs
from entity.missile import Missile
from guidance.guide import Guidance
from simulation import TrajectorySimulation
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

class CustomSimulation(TrajectorySimulation):
    def __init__(self):
        super(CustomSimulation, self).__init__()

    def init(self, mis=None, tar=None, guide=None, integ=None, db=None):
        if mis is None:
            mis = Missile()
        if tar is None:
            tar = Missile()
        if guide is None:
            guide = Guidance()
        if integ is None:
            integ = Integral()
        if db is None:
            db = DataSave()
        self.mis = mis
        self.tar = tar
        self.guide = guide
        self.integral = integ
        self.db = db
        # 初始化导弹及目标状态
        self.mis.status.change_stat(glbs.MissileInitStatus)
        self.tar.status.change_stat(glbs.TargetInitStatus)
        # 初始化制导模型
        self.guide.init(self.mis, self.tar)

        self.is_online = False

    def step_len(self) -> float:
        if self.guide.accurate_mode:
            return pow(0.1, self.guide.accurate_mode)
        return 1

    def save_data(self) -> None:
        # TAEM dwell-event channels (A2)
        update_taem_event(self.mis, global_t=self.t, dt_guess=getattr(self, 'h', None))
        self.db_save_dict = {"global_t": self.t,
                             "E": self.mis.guide["E"]}
        self.db_save_dict.update(self.mis.status.status_dict())
        self.db_save_dict.update(self.mis.control)
        self.db_save_dict.update(self.from_mis_guide(getattr(glbs, 'GUIDE_SAVE_PARAM', [])))

        self.db.update(self.db_save_dict)

    def is_continue(self):
        return True

    def after_simulation(self):
        if self.is_online:
            return
        status = {
            '经度': np.rad2deg(self.mis.status.longitude),
            '纬度': np.rad2deg(self.mis.status.latitude),
            '时间': self.mis.status.t,
            '速度': self.mis.status.velocity,
            '高度': self.mis.status.height,
            'Δψ': self.mis.guide["delta_psi"]
        }
        print('导弹结束状态：')
        for k in status.keys():
            print(f'{k}: {status[k]}\n')