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


class MultiMisSimInstance(MultiMissileSim):
    def __init__(self):
        super(MultiMisSimInstance, self).__init__()

    def init(self, mis=[], tar=[], guide=MultiMissileGuidance(), integ=Integral(), db=[]):
        self.mis = mis
        self.tar = tar
        self.guide = guide
        self.integral = integ
        self.db = [db for _ in mis]
        # 初始化导弹及目标状态
        for m, t, status in zip(self.mis, self.tar, glbs.StatusParams):
            m.status.change_stat(status["MissileInitStatus"])
            t.status.change_stat(status["TargetInitStatus"])
        # 初始化制导模型
        self.guide.init(self.mis, self.tar, self.guide_params())

    def save_data(self) -> None:
        """Save per-vehicle trajectory samples.

        Notes (multi-vehicle entry):
        - Always logs a stable vehicle id column (mis_id) using the list index.
        - Logs per-vehicle landing zone / target information (lz_lon/lz_lat/lz_h) if available.
        """
        for index, (mis, db) in enumerate(zip(self.mis, self.db)):
            # 如果此仿真周期进行了制导，则保存数据
            if mis.guide.get("guide_process", False) and not mis.guide.get("end_guide", False):
                # Core time & energy
                db_save_dict = {
                    "global_t": self.t,
                    "mis_id": index,
                    "E": mis.guide.get("E", np.nan),
                }

                # Vehicle state & control
                db_save_dict.update(mis.status.status_dict())
                db_save_dict.update(mis.control)

                # Landing zone (target) info (if the target list is aligned with vehicles)
                if hasattr(self, "tar") and self.tar is not None and index < len(self.tar):
                    tar = self.tar[index]
                    # Many projects keep target as a static object with status fields longitude/latitude/height
                    lon = getattr(getattr(tar, "status", tar), "longitude", np.nan)
                    lat = getattr(getattr(tar, "status", tar), "latitude", np.nan)
                    h   = getattr(getattr(tar, "status", tar), "height", 0.0)
                    db_save_dict.update({
                        "lz_lon": lon,
                        "lz_lat": lat,
                        "lz_h": h,
                        "lz_id": index,
                    })

                # Optional: extra internal guidance params (if defined in glbs.GUIDE_SAVE_PARAM)
                db_save_dict.update(self.from_mis_guide(mis, getattr(glbs, 'GUIDE_SAVE_PARAM', [])))

                # Ensure a generic time column exists for post-processing
                if "t" not in db_save_dict:
                    db_save_dict["t"] = getattr(mis.status, "t", self.t)

                db.update(db_save_dict)
