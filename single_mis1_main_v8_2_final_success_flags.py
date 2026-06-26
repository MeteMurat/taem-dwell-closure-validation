# -*- coding: utf-8 -*-
"""single_mis1_main_v8_2_final_success_flags.py

Run the V8.2 final-success-flags recovery path.

This intentionally returns to the V1 dynamics/control law, because V1 was the
only family that produced a real TAEM dwell. V8.1 keeps the success latch and preserves the reached-event pulse
and final-row termination semantics.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import sys

import pandas as pd

import multiset as glbs  # type: ignore
sys.modules["settings"] = glbs

import customGuidance as cg  # type: ignore
import simulation as simcore  # type: ignore

cg.glbs = glbs
simcore.glbs = glbs

from customSimulation import CustomSimulation  # type: ignore
from database.vehicleParams import CAVHParams  # type: ignore
from dynamics.aerodynamic import AerodynamicCAVH  # type: ignore
from dynamics.motionEquation import ME6D  # type: ignore
from entity.missile import Missile  # type: ignore
from store.dataSave import DataSave  # type: ignore
from store.status import ME6DStatus, MissileStatus  # type: ignore
from utils.integral import RungeKutta4  # type: ignore


def _load_guidance_class():
    module_name = "multiMissileGuideInstance_mis1_state_first_v8_2_final_success_flags"
    try:
        mod = __import__(module_name)
        return mod.Mis1StateFirstGuidanceV8Final
    except Exception:
        pass

    candidates = [
        Path(__file__).with_name(f"{module_name}.py"),
        Path(__file__).resolve().parent / "guidance" / f"{module_name}.py",
        Path.cwd() / f"{module_name}.py",
        Path.cwd() / "guidance" / f"{module_name}.py",
    ]
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location(module_name, str(p))
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return mod.Mis1StateFirstGuidanceV8Final
    raise ModuleNotFoundError(f"{module_name}.py bulunamadı. Dosyayı proje köküne veya guidance/ klasörüne koyun.")


Mis1StateFirstGuidanceV8Final = _load_guidance_class()


class SingleMis1SimulationV8(CustomSimulation):
    def __init__(self, vehicle_id: int = 1):
        self.vehicle_id = int(vehicle_id)
        super().__init__()

    def init(self, mis=None, tar=None, guide=None, integ=None, db=None):
        # CustomSimulation.__init__ calls self.init() without arguments. Tolerate it.
        if mis is None or tar is None or guide is None or integ is None or db is None:
            return
        self.mis = mis
        self.tar = tar
        self.guide = guide
        self.integral = integ
        self.db = db
        self.mis.status.change_stat(glbs.MissileInitStatus)
        self.tar.status.change_stat(glbs.TargetInitStatus)
        self.gen_guide_params()
        self.guide.init(self.mis, self.tar, dict(self.guide_params))
        self.is_online = False

    def next(self):
        if not self._is_continue():
            return False
        self.h = self.step_len()
        self.gen_guide_params()
        guide_ret = self.guide.one_step_guide(self.mis, self.tar, self.guide_params)

        if self.mis.guide.get("end_guide", False):
            self.after_guide()
            return False

        if guide_ret:
            self.after_guide()
            self.one_step_integral()
            return True
        return False

    def save_data(self) -> None:
        guide_process = bool(self.mis.guide.get("guide_process", True))
        end_guide = bool(self.mis.guide.get("end_guide", False))
        final_saved = bool(self.mis.guide.get("_final_saved", False))
        if (not guide_process) and (not (end_guide and not final_saved)):
            return

        row = {
            "global_t": getattr(self, "t", float("nan")),
            "mis_id": self.vehicle_id,
            "E": self.mis.guide.get("E", float("nan")),
        }
        row.update(self.mis.status.status_dict())
        if isinstance(getattr(self.mis, "control", None), dict):
            row.update(self.mis.control)

        row.update({
            "lz_lon": getattr(getattr(self.tar, "status", self.tar), "longitude", float("nan")),
            "lz_lat": getattr(getattr(self.tar, "status", self.tar), "latitude", float("nan")),
            "lz_h": getattr(getattr(self.tar, "status", self.tar), "height", 0.0),
            "lz_id": self.vehicle_id,
            "guide_process": guide_process,
            "end_guide": end_guide,
            "end_reason": self.mis.guide.get("end_reason", "end_guide" if end_guide else ""),
            "guide_phase": self.mis.guide.get("guide_phase", ""),
            "t_local": getattr(self.mis.status, "t", getattr(self, "t", 0.0)),
        })

        extra = [
            "s_go", "sgo_ref", "ref_psi", "delta_psi", "q", "L12D", "sigma_max",
            "terminal_capture_active", "taem_in_box", "taem_reached", "taem_reached_event",
            "taem_reached_ever", "taem_success_latched", "taem_fail_latched",
            "taem_dwell_s", "taem_dwell_count", "taem_t_first_in_box", "taem_t_reached",
            "taem_t_global", "taem_t_local", "taem_h_err", "taem_v_err", "taem_s_go_err",
            "taem_h_norm", "taem_v_norm", "taem_sgo_norm", "taem_box_score", "box_score",
            "taem_capture_weight", "taem_heading_weight", "close_pass_escape", "escape_rebound_m",
            "s_go_min_running", "sigma_cmd_raw", "sigma_cmd_prev", "sigma_cmd_rate_limited",
            "sigma_cmd_smoothed", "success_mode",
        ]
        for k in extra:
            row[k] = self.mis.guide.get(k, None)

        row.setdefault("t", getattr(self.mis.status, "t", getattr(self, "t", 0.0)))
        self.db.update(row)
        if end_guide and not final_saved:
            self.mis.guide["_final_saved"] = True


def _ensure_parent(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _pick_case(index: int):
    sp = getattr(glbs, "StatusParams", None)
    if sp is not None:
        try:
            return sp[int(index)]
        except Exception:
            pass
    cases = getattr(glbs, "cases", None)
    if cases is not None:
        try:
            return cases[int(index)]
        except Exception:
            pass
    raise RuntimeError("multiset.StatusParams veya multiset.cases içinde mis_index bulunamadı.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mis-index", type=int, default=1)
    parser.add_argument("--out", default=os.path.join("store", "data_saved", "mis1_state_first_v8_2_final_success_flags.csv"))
    args = parser.parse_args()

    case = _pick_case(args.mis_index)
    glbs.MissileInitStatus = case["MissileInitStatus"]
    glbs.TargetInitStatus = case["TargetInitStatus"]
    glbs.MissileEndStatus = case["MissileEndStatus"]
    glbs.STORE_DATA = args.out

    mis = Missile(motion_equation=ME6D(), aerodynamic=AerodynamicCAVH(), params=CAVHParams(), status=ME6DStatus())
    tar = Missile(status=MissileStatus())
    guide = Mis1StateFirstGuidanceV8Final(case=case, vehicle_id=args.mis_index)
    integral = RungeKutta4()
    database = DataSave()

    simulation = SingleMis1SimulationV8(vehicle_id=args.mis_index)
    simulation.init(mis=mis, tar=tar, guide=guide, integ=integral, db=database)
    simulation.simulation()

    if hasattr(simulation.db, "finalize"):
        try:
            simulation.db.finalize()
        except Exception:
            pass

    result: pd.DataFrame = simulation.db.data.copy()
    if "mis_id" not in result.columns:
        result.insert(0, "mis_id", args.mis_index)
    for tcol in ["t_local", "global_t", "t"]:
        if tcol in result.columns:
            result = result.sort_values([tcol], kind="mergesort").reset_index(drop=True)
            break

    _ensure_parent(args.out)
    result.to_csv(args.out, index=False)
    print(f"[OK] saved: {args.out}")
    if len(result):
        cols = [c for c in ["taem_reached", "taem_reached_event", "taem_reached_ever", "taem_success_latched", "end_guide", "end_reason", "taem_dwell_s", "taem_h_err", "taem_v_err", "taem_s_go_err"] if c in result.columns]
        print(result.tail(1)[cols].T.to_string())


if __name__ == "__main__":
    main()
