# -*- coding: utf-8 -*-
# EditTime  : 2021-09-27 19:13
# Author    : Of yue
# File      : MultiMissileSim.py
# Intro     :
from itertools import chain
from typing import List

from entity.missile import Missile
from guidance.MultiGuide import MultiMissileGuidance
from store.dataSave import DataSave
from utils.integral import Integral
import multiset as glbs
import numpy as np


class MultiMissileSim:
    def __init__(self):
        # 最大迭代次数
        self.max_iter = getattr(glbs, "MAXITER", 0)
        # 当前迭代次数
        self.iter = 0

        # 最小积分步长
        self.min_h = getattr(glbs, "MIN_H", 1E-4)

        # 全局时间
        self.t = getattr(glbs, "t0", 0)

        # 参与仿真的导弹
        self.mis: List[Missile] = []
        self.tar: List[Missile] = []

        # 制导模块
        self.guide: MultiMissileGuidance = MultiMissileGuidance()
        self.guide_params_list = getattr(glbs, "ParamsToGuide", [])

        # 积分模块
        self.integral = Integral()

        # 数据存储模块
        self.db: List[DataSave] = []
        self.db_save_dict: dict = {}  # 每次存储值的临时字典
        self.init()

        # 其它
        # 是否为在线临时仿真
        self.is_main = True
        self._ended_this_step = False
    def init(self, mis=[], tar=[], guide=MultiMissileGuidance(), integ=Integral(), db=[]):
        """
        初始化导弹，目标，制导模式，积分，存储模块等信息，需重载
        :param mis: List[Missile]
        :param tar: List[Missile]
        :param guide: Guidance
        :param integ: Integral
        :param db: List[DataSave]
        :return:
        """
        pass

    def step_len(self):
        """
        计算每一步的积分步长，需重载
        :return:
        """
        return self.min_h

    def simulation(self):
        self._before_simulation()
        while self.next():
            self._after_one_step()
        self._after_simulation()

    def next(self):
        """
        单次仿真循环，当停止制导后自动结束
        :return:
        """
        if self._is_continue():
            if self.one_step_guide():
                # 此处应该先保存上一步的状态值，再改变状态
                self.after_guide()
                # 积分且更新状态
                self.one_step_integral()  # 包含了self.one_step_update_status()
                return True
        return False

    def one_step_guide(self):
        """
        1.产生控制指令
        :return: True代表单步制导执行成功
                False代表制导结束
        """
        # 产生传入制导模块的相关参数
        # 产生制导指令, 如果制导指令成功生成，则继续仿真
        return self.guide.one_step_guide(self.mis, self.tar, self.guide_params())

    def one_step_integral(self):
        """
        2.各个体单步积分
        :return:
        """
        for m in chain(self.mis, self.tar):
            self.one_step_integral_object(m)
        # If someone ended during integration, persist a post-integration final row.
        # This prevents missing touchdown/nonfinite rows in CSV.
        if getattr(self, "_ended_this_step", False):
            self.save_data()
            self._ended_this_step = False


    def one_step_integral_object(self, obj: Missile):
        # 如果时间累计大于步长，则制导一次
        if not obj.guide["guide_process"]:
            return False
        if obj.guide["end_guide"]:
            return False
        if obj.launched:
            # 如果导弹已发射则更新状态
            x, y0 = obj.status.x, obj.status.y

            temp_step_len = obj.guide.get("step_len", self.step_len())
            y_next, dy = self.integral.next_step(obj.equation.equation, x, y0, temp_step_len, obj.control, need_dy=True)
            x_next = x + temp_step_len
            if dy is not None:
                obj.guide["dy"] = dy

            # 3.各个体更新状态
            status_update_data = {k: v for k, v in zip(obj.status.integral_key, y_next)}
            status_update_data.update({obj.status.independent_key: x_next})
            obj.status.change_stat(status_update_data)

            # -------- Termination/safety guard (multi-vehicle) --------
            # If a vehicle goes below ground (or becomes NaN/Inf), stop its
            # propagation AND stop logging further unphysical values.
            vended = self._post_integral_guard(obj)
            if vended:
                self._ended_this_step = True

    def _post_integral_guard(self, obj):
        """Stop a vehicle when it becomes invalid.

        Returns:
        True if the object was terminated in this call, else False.
        """
        try:
            h = float(getattr(obj.status, "height", float("nan")))
        except Exception:
            h = float("nan")

        ground_h = float(getattr(glbs, "GROUND_H", 0.0))

        # NaN/Inf -> terminate immediately
        if not np.isfinite(h):
            try:
                obj.status.change_stat({"height": ground_h, "velocity": 0.0})
            except Exception:
                obj.status["height"] = ground_h
                obj.status["velocity"] = 0.0

            obj.guide["end_guide"] = True
            obj.guide["touchdown"] = False
            obj.guide["end_reason"] = obj.guide.get("end_reason", "nonfinite_state")
            obj.guide["_final_saved"] = False  # ensure final row gets written
            return True

        # Touchdown -> clamp to ground_h and terminate
        if h <= ground_h:
            try:
                obj.status.change_stat({"height": ground_h, "velocity": 0.0})
            except Exception:
                obj.status["height"] = ground_h
                obj.status["velocity"] = 0.0

            obj.guide["end_guide"] = True
            obj.guide["touchdown"] = True
            obj.guide["end_reason"] = obj.guide.get("end_reason", "touchdown")
            obj.guide["_final_saved"] = False  # ensure final row gets written
            return True

        return False


    def guide_params(self):
        """Build meta dict passed into guidance.

        Key behavior:
        - Always injects the running simulation object as meta["simulation"].
        - Skips keys whose values are None (prevents float(None) crashes in guidance).
        """
        meta = {"simulation": self}
        for param in getattr(self, "guide_params_list", []):
            if param in ("self", "simulation"):
                continue
            val = getattr(self, param, None)
            if val is None:
                continue
            meta[param] = val
        return meta

    def save_data(self) -> None:
        """
        存储数据
        :return: None
        """
        for index, (mis, db) in enumerate(zip(self.mis, self.db)):
            guide_process = bool(mis.guide.get("guide_process", False))
            end_guide = bool(mis.guide.get("end_guide", False))
            touchdown = bool(mis.guide.get("touchdown", False))
            final_saved = bool(mis.guide.get("_final_saved", False))

            # Save while active; also save exactly one final row when end_guide=True
            should_save = (guide_process and (not end_guide or not final_saved)) or touchdown
            if should_save:
                db_save_dict = {"global_t": self.t, "mis_id": index}

                # --- Time axes ---
                # global_t: simulation-wide time (may be discontinuous across vehicles due to staggered launches)
                # t_local: per-vehicle time referenced to that vehicle's launch_time
                launch_time = mis.guide.get("launch_time", 0.0)
                try:
                    launch_time = float(launch_time) if launch_time is not None else 0.0
                except Exception:
                    launch_time = 0.0
                db_save_dict["launch_time"] = launch_time
                db_save_dict["t_local"] = self.t - launch_time

                # --- Target info (useful for plotting and diagnostics) ---
                try:
                    tar_i = self.tar[index] if isinstance(self.tar, (list, tuple)) and index < len(self.tar) else (
                        self.tar[0] if isinstance(self.tar, (list, tuple)) and len(self.tar) > 0 else self.tar
                    )
                    if tar_i is not None and hasattr(tar_i, "status"):
                        tar_lon = getattr(tar_i.status, "longitude", None)
                        tar_lat = getattr(tar_i.status, "latitude", None)
                        db_save_dict["tar_longitude"] = tar_lon
                        db_save_dict["tar_latitude"] = tar_lat
                        if tar_lon is not None:
                            db_save_dict["tar_longitude_deg"] = float(np.degrees(tar_lon))
                        if tar_lat is not None:
                            db_save_dict["tar_latitude_deg"] = float(np.degrees(tar_lat))
                except Exception:
                    # Target logging is best-effort only.
                    pass

                # --- Path-shaping metadata (optional) ---
                path_spec = mis.guide.get("path_spec", None)
                if isinstance(path_spec, dict):
                    if "name" in path_spec:
                        db_save_dict["path_name"] = path_spec.get("name")
                    for _k in [
                        "psi_bias_deg", "psi_bias_sgo_on_m", "psi_bias_sgo_off_m",
                        "psi_bias_alt_on_m", "psi_bias_alt_off_m", "sgn_ini_override",
                        "heading_bias_deg", "turn_bias_deg", "bias_fade_s", "bias_fade_tau"
                    ]:  
                        if _k in path_spec:
                            db_save_dict[_k] = path_spec.get(_k)

                db_save_dict.update(mis.status.status_dict())
                db_save_dict.update(mis.control)

                # Critical for online-trajectory hooks used by guidance:
                # simulation_online() expects at least: s_go, E, L12D, t.
                # - t is typically part of status_dict().
                # - s_go / L12D live in mis.guide.
                # - E is also tracked in mis.guide["E"] (set in parse_param()).
                db_save_dict["E"] = mis.guide.get("E", None)
                db_save_dict["s_go"] = mis.guide.get("s_go", None)
                db_save_dict["L12D"] = mis.guide.get("L12D", None)

                # Optionally persist extra guide channels declared in config.
                for k in getattr(glbs, "GUIDE_SAVE_PARAM", []):
                    # Do not overwrite if already set above
                    if k not in db_save_dict:
                        db_save_dict[k] = mis.guide.get(k, None)

                # Debug / paper-ready fields
                db_save_dict.update({
                    "guide_process": guide_process,
                    "end_guide": end_guide,
                    "touchdown": touchdown,
                    "end_reason": mis.guide.get("end_reason", None),
                    "guide_phase": mis.guide.get("guide_phase", None),
                    "sigma_max": mis.guide.get("sigma_max", None),
                })

                db.update(db_save_dict)

                if end_guide:
                    mis.guide["_final_saved"] = True
    def _is_continue(self) -> bool:
        """判断是否继续仿真"""
        if self.iter > self.max_iter:
            return False
        if not self.is_continue():
            return False
        return True

    def is_continue(self):
        return True

    def after_guide(self):
        """
        制导指令计算完成后进行
        可存储导弹及其控制指令
        :return:
        """
        self.save_data()

    def _after_one_step(self):
        """每个积分循环完成后需要进行的操作
        可以存储数据等，但一般存储数据在制导完成之后进行"""
        # 迭代次数+1
        self.iter += 1
        # 时间前进h
        self.t += self.min_h
        self.after_one_step()

    def after_one_step(self):
        pass

    def _before_simulation(self):
        print("[SIM_START]")
        self.before_simulation()

    def before_simulation(self):
        pass

    def _after_simulation(self):
        """Finalize simulation with consistent end flags and flushed logs."""
        print("[SIM_END]")

        # Mark any still-active missiles as ended, so CSV is self-consistent
        for m in getattr(self, "mis", []):
            guide_process = bool(m.guide.get("guide_process", False))
            end_guide = bool(m.guide.get("end_guide", False))
            if guide_process and (not end_guide):
                m.guide["end_guide"] = True
                m.guide["touchdown"] = bool(m.guide.get("touchdown", False))
                m.guide["end_reason"] = m.guide.get("end_reason", "sim_terminated")
                m.guide["_final_saved"] = False

        # Save one final snapshot and flush buffers
        try:
            self.save_data()
        except Exception:
            pass

        for db in getattr(self, "db", []):
            try:
                db._flush()
            except Exception:
                pass
        self.after_simulation()


    def after_simulation(self):
        pass

    def from_mis_guide(self, mis: Missile, param_list: list):
        return {param: mis.guide.get(param, None)
                for param in param_list}
