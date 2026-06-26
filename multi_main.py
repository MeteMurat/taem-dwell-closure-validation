# -*- coding: utf-8 -*-
r"""
multi_main_phase2_B1_safe_v9.py

Phase 2 / B1 safe multi-vehicle runner — V9 exact single-runner alignment.

Fix vs v5:
- Adds B1 active-vehicle gating: by default only mis_id=1 is actively guided/integrated,
  while the N=3 multi-run scaffold remains present. This avoids running three heavy
  V8.2 online-update chains in parallel.
- Inactive vehicles are marked as ended placeholders and do not enter child guidance,
  online update, or integration.

Fix vs v4:
- Adds adapter-level allow_update_param/k_alpha propagation.
- Prevents recursive/heavy online-update loops when V8.2 child guidance calls simulation_online() inside a multi-vehicle adapter.

Fix vs v2:
- The V8.2 guidance file was found and the class was detected as
  `Mis1StateFirstGuidance`, but that class requires a `case` argument.
- This runner instantiates such case-based guidance classes safely.
- If the detected guidance class is a single-vehicle guidance class, this runner
  wraps it in a small multi-vehicle adapter and creates one child guidance object
  per vehicle using multiset.StatusParams[i].

Usage:
  copy .\multi_main_phase2_B1_safe_v9.py .\multi_main.py
  python .\multi_main.py
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

import multiset as glbs  # type: ignore

# V9 critical alignment with single_mis1_main_v8_2_final_success_flags.py:
# customGuidance.py imports `settings as glbs`. The successful single runner
# aliases settings -> multiset before importing customGuidance / simulation.
# Without this, a stale settings.py can silently drive the guidance law.
sys.modules["settings"] = glbs

from core.multiMissileSimInstance import MultiMisSimInstance as BaseMultiMisSimInstance
from database.vehicleParams import CAVHParams
from dynamics.aerodynamic import AerodynamicCAVH
from dynamics.motionEquation import ME6D
from entity.missile import Missile
from store.dataSave import DataSave
from store.status import ME6DStatus, MissileStatus
from utils.integral import RungeKutta4

try:
    from guidance.MultiGuide import MultiMissileGuidance  # type: ignore
except Exception:  # pragma: no cover - project-dependent
    MultiMissileGuidance = None  # type: ignore

try:
    from guidance.guide import Guidance  # type: ignore
except Exception:  # pragma: no cover - project-dependent
    Guidance = None  # type: ignore




class SafeMultiMisSimInstance(BaseMultiMisSimInstance):
    """B1-safe simulation wrapper.

    Some local versions of core.MultiMissileSim access obj.guide["guide_process"]
    directly during integration. The V8.2 single-vehicle guidance may not keep that
    key on every object at every phase, and target objects usually have an empty
    guide dictionary. This wrapper normalizes the guide flags before delegating to
    the original simulator. It does not change the dynamics or guidance law.
    """

    @staticmethod
    def _normalize_obj(obj, default_process: bool = True) -> None:
        if not hasattr(obj, "guide") or obj.guide is None:
            obj.guide = {}
        obj.guide.setdefault("guide_process", bool(default_process))
        obj.guide.setdefault("end_guide", False)
        obj.guide.setdefault("end_reason", "")
        obj.guide.setdefault("guide_phase", obj.guide.get("guide_phase", ""))

    def _normalize_all(self) -> None:
        for obj in list(getattr(self, "mis", []) or []) + list(getattr(self, "tar", []) or []):
            self._normalize_obj(obj, default_process=True)

    def init(self, *args, **kwargs):
        out = super().init(*args, **kwargs)
        self._normalize_all()
        return out

    def one_step_guide(self):
        self._normalize_all()
        out = super().one_step_guide()
        self._normalize_all()
        return out

    def one_step_integral_object(self, obj):
        self._normalize_obj(obj, default_process=True)
        return super().one_step_integral_object(obj)


GUIDANCE_CANDIDATES = [
    "guidance.multiMissileGuideInstance_mis1_state_first_v8_2_final_success_flags",
    "guidance.multiMissileGuideInstance_mis1_state_first_v8_1_success_latch_eventfix",
    "guidance.multiMissileGuideInstance_mis1_state_first_v8_success_latch",
    "guidance.multiMissileGuideInstance_state_first_v8_2_final_success_flags",
    "guidance.multiMissileGuideInstance_taem_state_first_v8_2_final_success_flags",
    "guidance.multiMissileGuideInstance_terminal_capture_phase_v8_2_final_success_flags",
    "guidance.multiMissileGuideInstance_terminal_capture_phase_v8",
    "guidance.multiMissileGuideInstance_terminal_capture_phase_v10",
    "guidance.multiMissileGuideInstance",
]

GUIDANCE_CLASS_NAME_CANDIDATES = [
    "Mis1StateFirstGuidanceV8Final",
    "MultiMisGuideInstance",
    "MultiMissileGuideInstance",
    "MultiGuideInstance",
    "MultiMisGuidance",
    "MultiMissileGuidanceInstance",
    "MultiMissileGuidance",
    "Mis1StateFirstGuidance",
    "TerminalCaptureGuidance",
    "StateFirstGuidance",
    "TAEMGuidance",
]


# -----------------------------------------------------------------------------
# Guidance discovery
# -----------------------------------------------------------------------------

def _discover_guidance_modules() -> list[str]:
    gdir = Path("guidance")
    if not gdir.exists():
        return []
    mods: list[str] = []
    for p in sorted(gdir.glob("multiMissileGuideInstance*.py")):
        if p.name.startswith("__"):
            continue
        mods.append(f"guidance.{p.stem}")
    return mods


def _is_project_guidance_class(mod, name: str, obj) -> bool:
    if not inspect.isclass(obj):
        return False
    module_defined = getattr(obj, "__module__", "") == getattr(mod, "__name__", "")
    lname = name.lower()
    looks_like = any(k in lname for k in ["guide", "guidance", "taem", "capture", "state"])
    return bool(module_defined and looks_like)


def _select_guidance_class_from_module(mod):
    for cname in GUIDANCE_CLASS_NAME_CANDIDATES:
        obj = getattr(mod, cname, None)
        if inspect.isclass(obj) and getattr(obj, "__module__", "") == getattr(mod, "__name__", ""):
            return cname, obj

    generic = []
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if _is_project_guidance_class(mod, name, obj):
            generic.append((name, obj))

    if generic:
        def score(item):
            name = item[0].lower()
            s = 0
            if "mis1" in name:
                s += 30
            if "state" in name:
                s += 20
            if "instance" in name:
                s += 20
            if "guide" in name:
                s += 15
            if "guidance" in name:
                s += 15
            if "taem" in name:
                s += 8
            if "base" in name or "test" in name:
                s -= 40
            return -s, name
        generic.sort(key=score)
        return generic[0]

    return None, None


def _load_guidance_class():
    tried: list[str] = []
    candidate_chain: list[str] = []
    for name in GUIDANCE_CANDIDATES + _discover_guidance_modules():
        if name not in candidate_chain:
            candidate_chain.append(name)

    skipped_messages: list[str] = []
    for module_name in candidate_chain:
        tried.append(module_name)
        try:
            mod = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if getattr(exc, "name", None) not in (module_name, module_name.split(".")[-1]):
                msg = f"{module_name}: internal ModuleNotFoundError: {exc}"
                print(f"[multi_main_B1_safe_v9] Skipped {msg}")
                skipped_messages.append(msg)
            continue
        except Exception as exc:
            msg = f"{module_name}: import error: {type(exc).__name__}: {exc}"
            print(f"[multi_main_B1_safe_v9] Skipped {msg}")
            skipped_messages.append(msg)
            continue

        cname, cls = _select_guidance_class_from_module(mod)
        if cls is not None:
            print(f"[multi_main_B1_safe_v9] Selected guidance module: {module_name}")
            print(f"[multi_main_B1_safe_v9] Selected guidance class : {cname}")
            return cls, module_name, cname

        local_classes = [
            name for name, obj in inspect.getmembers(mod, inspect.isclass)
            if getattr(obj, "__module__", "") == getattr(mod, "__name__", "")
        ]
        msg = f"{module_name}: no usable guidance class found; local classes={local_classes}"
        print(f"[multi_main_B1_safe_v9] Skipped {msg}")
        skipped_messages.append(msg)

    discovered = _discover_guidance_modules()
    raise ModuleNotFoundError(
        "No usable guidance class was found.\n"
        "Tried modules:\n  - " + "\n  - ".join(tried) + "\n"
        "Discovered guidance files:\n  - " + ("\n  - ".join(discovered) if discovered else "<none>") + "\n"
        "Skipped details:\n  - " + ("\n  - ".join(skipped_messages) if skipped_messages else "<none>")
    )


# -----------------------------------------------------------------------------
# Constructor helpers
# -----------------------------------------------------------------------------

def _status_params() -> list[dict]:
    sp = getattr(glbs, "StatusParams", None)
    if sp is None:
        return []
    try:
        return list(sp)
    except Exception:
        return []


def _target_case_index(n: int) -> int:
    raw = getattr(glbs, "B1_TARGET_MIS_ID", 1)
    try:
        idx = int(raw)
    except Exception:
        idx = 1
    if n <= 0:
        return 0
    return max(0, min(idx, n - 1))


def _try_construct(cls, attempts: Iterable[tuple[str, tuple, dict]]):
    errors: list[str] = []
    for label, args, kwargs in attempts:
        try:
            obj = cls(*args, **kwargs)
            print(f"[multi_main_B1_safe_v9] Constructed {cls.__name__} using: {label}")
            return obj
        except TypeError as exc:
            errors.append(f"{label}: TypeError: {exc}")
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
    raise TypeError("Could not construct guidance class. Attempts:\n  - " + "\n  - ".join(errors))


def _construct_direct_guidance(cls, n: int):
    sp = _status_params()
    target_i = _target_case_index(n)
    target_case = sp[target_i] if target_i < len(sp) else None

    attempts = [
        ("no arguments", tuple(), {}),
        (f"case=StatusParams[{target_i}]", tuple(), {"case": target_case}),
        (f"StatusParams[{target_i}] positional", (target_case,), {}),
        ("case=StatusParams", tuple(), {"case": sp}),
        ("StatusParams positional", (sp,), {}),
        (f"case_id={target_i}", tuple(), {"case_id": target_i}),
        (f"mis_id={target_i}", tuple(), {"mis_id": target_i}),
        (f"target_mis_id={target_i}", tuple(), {"target_mis_id": target_i}),
    ]
    return _try_construct(cls, attempts)


def _construct_child_guidance(cls, case: Any, idx: int):
    attempts = [
        (f"case=StatusParams[{idx}], vehicle_id={idx}", tuple(), {"case": case, "vehicle_id": idx}),
        (f"case=StatusParams[{idx}]", tuple(), {"case": case}),
        (f"StatusParams[{idx}] positional", (case,), {}),
        (f"case_id={idx}", tuple(), {"case_id": idx}),
        (f"mis_id={idx}", tuple(), {"mis_id": idx}),
        (f"vehicle_id={idx}", tuple(), {"vehicle_id": idx}),
        ("no arguments", tuple(), {}),
    ]
    return _try_construct(cls, attempts)


def _is_multi_guidance_class(cls) -> bool:
    if MultiMissileGuidance is not None:
        try:
            if issubclass(cls, MultiMissileGuidance):
                return True
        except Exception:
            pass
    lname = cls.__name__.lower()
    return "multi" in lname and ("guide" in lname or "guidance" in lname or "instance" in lname)


def _is_single_guidance_class(cls) -> bool:
    if Guidance is not None:
        try:
            return bool(issubclass(cls, Guidance) and not _is_multi_guidance_class(cls))
        except Exception:
            pass
    return not _is_multi_guidance_class(cls)


def _call_flexible_init(obj, mis, tar, meta):
    if not hasattr(obj, "init"):
        return
    attempts = [
        ("init(mis, tar, meta)", (mis, tar, meta), {}),
        ("init(mis, tar)", (mis, tar), {}),
        ("init(missile=mis, target=tar, meta=meta)", tuple(), {"missile": mis, "target": tar, "meta": meta}),
        ("init(mis=mis, tar=tar, meta=meta)", tuple(), {"mis": mis, "tar": tar, "meta": meta}),
    ]
    errors = []
    for label, args, kwargs in attempts:
        try:
            obj.init(*args, **kwargs)
            return
        except TypeError as exc:
            errors.append(f"{label}: {exc}")
    raise TypeError("Could not call child guidance init. Attempts:\n  - " + "\n  - ".join(errors))


def _call_flexible_one_step(obj, mis, tar, meta):
    if hasattr(obj, "one_step_guide"):
        attempts = [
            ("one_step_guide(mis, tar, meta)", (mis, tar, meta), {}),
            ("one_step_guide(mis, tar)", (mis, tar), {}),
        ]
        errors = []
        for label, args, kwargs in attempts:
            try:
                return obj.one_step_guide(*args, **kwargs)
            except TypeError as exc:
                errors.append(f"{label}: {exc}")
        raise TypeError("Could not call child one_step_guide. Attempts:\n  - " + "\n  - ".join(errors))

    if hasattr(obj, "guide"):
        obj.guide(mis, tar, meta)
        return not bool(mis.guide.get("end_guide", False))

    raise AttributeError(f"{obj.__class__.__name__} has neither one_step_guide nor guide")


class B1SingleOnlineSimulation:
    """Single-vehicle facade used by V8.2 online update routines.

    The original single-vehicle guidance expects meta["simulation"] to be a
    single-vehicle simulation object. In the B1 multi adapter, the parent
    simulator is multi-vehicle and therefore has sim.db as a list plus sim.mis
    and sim.tar as lists. CustomGuidance.simulation_online() then fails at
    sim.db.data. This facade gives the active child guidance an object with the
    expected single-vehicle shape while preserving the actual missile, target,
    guidance, and integrator objects through deepcopy.
    """

    def __init__(self, mis, tar, guide, parent=None, vehicle_index: int = 0):
        self.max_iter = int(getattr(glbs, "MAXITER", 100000))
        self.iter = 0
        self.h = float(getattr(glbs, "INI_STEP", 1.0) or 1.0)
        self.min_h = float(getattr(parent, "min_h", getattr(glbs, "MIN_H", 1e-2)) or 1e-2)
        self.t = float(getattr(parent, "t", getattr(getattr(mis, "status", None), "t", 0.0)) or 0.0)
        self.is_main = False
        self.is_online = True
        self.vehicle_index = int(vehicle_index)

        self.mis = mis
        self.tar = tar
        self.guide = guide
        self.integral = getattr(parent, "integral", None) or RungeKutta4()
        self.db = DataSave()
        self.db_save_dict = {}

        self.guide_params_list = list(getattr(glbs, "ParamsToGuide", []))
        self.guide_params = {}

        defaults = dict(getattr(glbs, "GuideMetaDefaults", {}) or {})
        for key, val in defaults.items():
            setattr(self, key, val)
        for key in self.guide_params_list:
            if not hasattr(self, key) and hasattr(glbs, key):
                setattr(self, key, getattr(glbs, key))

    def step_len(self) -> float:
        acc = int(getattr(self.guide, "accurate_mode", 0) or 0)
        if acc > 0:
            return float(pow(0.1, acc))
        return float(getattr(glbs, "INI_STEP", 1.0) or 1.0)

    def gen_guide_params(self) -> None:
        self.guide_params = {}
        for param in self.guide_params_list:
            if param == "self":
                self.guide_params["simulation"] = self
            else:
                self.guide_params[param] = getattr(self, param, None)
        self.guide_params.setdefault("simulation", self)
        self.guide_params.setdefault("t", self.t)
        self.guide_params.setdefault("min_h", self.min_h)
        self.guide_params.setdefault("is_main", False)
        self.guide_params.setdefault("vehicle_index", self.vehicle_index)
        self.guide_params.setdefault("mis_id", self.vehicle_index)

    def one_step_guide(self) -> bool:
        self.gen_guide_params()
        if hasattr(self.guide, "one_step_guide"):
            return bool(self.guide.one_step_guide(self.mis, self.tar, self.guide_params))
        if hasattr(self.guide, "guide"):
            self.guide.guide(self.mis, self.tar, self.guide_params)
            return not bool(self.mis.guide.get("end_guide", False))
        return False

    def one_step_integral_object(self, obj) -> None:
        if not getattr(obj, "launched", False):
            return
        if not hasattr(obj, "guide") or obj.guide is None:
            obj.guide = {}
        if obj.guide.get("guide_process", True) is False:
            return
        x, y0 = obj.status.x, obj.status.y
        y_next, dy = self.integral.next_step(obj.equation.equation, x, y0, self.h, obj.control, need_dy=True)
        x_next = x + self.h
        if dy is not None:
            obj.guide["dy"] = dy
        status_update_data = {k: v for k, v in zip(obj.status.integral_key, y_next)}
        status_update_data.update({obj.status.independent_key: x_next})
        obj.status.change_stat(status_update_data)

    def one_step_integral(self) -> None:
        self.one_step_integral_object(self.mis)
        self.one_step_integral_object(self.tar)

    def save_data(self) -> None:
        d = {"global_t": self.t, "E": self.mis.guide.get("E", None)}
        d.update(self.mis.status.status_dict())
        if isinstance(getattr(self.mis, "control", None), dict):
            d.update(self.mis.control)
        for k in getattr(glbs, "GUIDE_SAVE_PARAM", []):
            d[k] = self.mis.guide.get(k, None)
        self.db.update(d)

    def next(self) -> bool:
        if self.iter > self.max_iter:
            return False
        self.h = self.step_len()
        if not self.one_step_guide():
            return False
        self.save_data()
        self.one_step_integral()
        self.iter += 1
        self.t += self.h
        return True

    def simulation(self) -> None:
        print("[SIM_START]")
        while self.next():
            pass
        print("[SIM_END]")




def _active_mis_ids(n: int) -> set[int]:
    """Return active vehicle ids for B1.

    Default is {B1_TARGET_MIS_ID}, normally {1}.
    User can override in multiset.py with B1_ACTIVE_MIS_IDS = [1] or [0,1,2].
    """
    raw = getattr(glbs, "B1_ACTIVE_MIS_IDS", None)
    if raw is None:
        raw = [getattr(glbs, "B1_TARGET_MIS_ID", 1)]
    if isinstance(raw, (int, float, str)):
        raw = [raw]
    out: set[int] = set()
    try:
        for x in raw:
            try:
                i = int(x)
            except Exception:
                continue
            if 0 <= i < int(n):
                out.add(i)
    except Exception:
        pass
    if not out and n > 0:
        out.add(max(0, min(int(getattr(glbs, "B1_TARGET_MIS_ID", 1)), n - 1)))
    return out


class B1InactiveGuidance:
    """Placeholder for inactive vehicles in the B1 minimal transfer test."""
    accurate_mode = 0
    allow_update_param = False

    def __init__(self, idx: int):
        self.idx = idx
        self.guide_mode = "b1_inactive_placeholder"

    def init(self, mis, tar, meta=None):
        for obj, phase in ((mis, "b1_inactive_missile"), (tar, "b1_inactive_target")):
            if not hasattr(obj, "guide") or obj.guide is None:
                obj.guide = {}
            obj.guide.update({
                "guide_process": False,
                "end_guide": True,
                "end_reason": "b1_inactive_vehicle",
                "guide_phase": phase,
                "_final_saved": True,
            })

    def one_step_guide(self, mis, tar, meta=None):
        for obj, phase in ((mis, "b1_inactive_missile"), (tar, "b1_inactive_target")):
            if not hasattr(obj, "guide") or obj.guide is None:
                obj.guide = {}
            obj.guide.update({
                "guide_process": False,
                "end_guide": True,
                "end_reason": "b1_inactive_vehicle",
                "guide_phase": phase,
                "_final_saved": True,
            })
        return False

class MultiVehicleGuidanceAdapter:
    """Wrap a single-vehicle guidance class into a multi-vehicle guidance object.

    This is intentionally thin: it does not change the terminal latch/event logic.
    It only creates one independent guidance instance per vehicle and routes each
    missile/target pair to its own child guidance object.
    """

    def __init__(self, child_cls, status_params: list[dict], source_module: str, source_class: str, active_ids: set[int] | None = None):
        self.child_cls = child_cls
        self.status_params = status_params
        self.source_module = source_module
        self.source_class = source_class
        self.children: list[Any] = []
        self.active_ids: set[int] = set(active_ids or [])
        self.accurate_mode = 0
        self.guide_process = True
        # Adapter-level mirrors for the original single-vehicle online simulator.
        # V8.2 child guidance may deep-copy the simulation and then set
        # sim.guide.allow_update_param = False. Without propagation, that flag
        # stays on the adapter and the child guidances may start nested online
        # updates. Propagation keeps the online branch finite.
        self._allow_update_param = True
        self._k_alpha = None

    @property
    def allow_update_param(self):
        return self._allow_update_param

    @allow_update_param.setter
    def allow_update_param(self, value):
        self._allow_update_param = bool(value)
        for child in getattr(self, "children", []) or []:
            if hasattr(child, "allow_update_param"):
                try:
                    child.allow_update_param = bool(value)
                except Exception:
                    pass

    @property
    def k_alpha(self):
        return self._k_alpha

    @k_alpha.setter
    def k_alpha(self, value):
        self._k_alpha = value
        for child in getattr(self, "children", []) or []:
            if hasattr(child, "k_alpha"):
                try:
                    child.k_alpha = value
                except Exception:
                    pass

    def _propagate_adapter_controls(self) -> None:
        for child in getattr(self, "children", []) or []:
            if hasattr(child, "allow_update_param"):
                try:
                    child.allow_update_param = bool(getattr(self, "_allow_update_param", True))
                except Exception:
                    pass
            if getattr(self, "_k_alpha", None) is not None and hasattr(child, "k_alpha"):
                try:
                    child.k_alpha = getattr(self, "_k_alpha")
                except Exception:
                    pass

    def init(self, mis, tar, meta=None):
        meta = dict(meta or {})
        self.mis = mis
        self.tar = tar
        self.children = []

        n = len(mis)
        if len(self.status_params) < n:
            print("[multi_main_B1_safe_v9] WARNING: StatusParams shorter than vehicle count; missing cases use None")

        if not self.active_ids:
            self.active_ids = _active_mis_ids(n)
        print(f"[multi_main_B1_safe_v9] B1 active vehicle ids: {sorted(self.active_ids)}")

        for i in range(n):
            case = self.status_params[i] if i < len(self.status_params) else None
            if i in self.active_ids:
                child = _construct_child_guidance(self.child_cls, case, i)
            else:
                child = B1InactiveGuidance(i)
                print(f"[multi_main_B1_safe_v9] Vehicle {i} set inactive for B1 minimal transfer test")

            meta_i = dict(meta)
            meta_i.update({"vehicle_index": i, "mis_id": i, "case": case, "status_param": case})
            _call_flexible_init(child, mis[i], tar[i], meta_i)

            if not hasattr(mis[i], "guide") or mis[i].guide is None:
                mis[i].guide = {}
            if not hasattr(tar[i], "guide") or tar[i].guide is None:
                tar[i].guide = {}

            if i in self.active_ids:
                mis[i].guide.setdefault("guide_process", True)
                mis[i].guide.setdefault("end_guide", False)
                mis[i].guide.setdefault("guide_phase", getattr(child, "guide_mode", ""))
                tar[i].guide.setdefault("guide_process", True)
                tar[i].guide.setdefault("end_guide", False)
                tar[i].guide.setdefault("guide_phase", "target")
            else:
                mis[i].guide.update({"guide_process": False, "end_guide": True, "end_reason": "b1_inactive_vehicle", "guide_phase": "b1_inactive_missile", "_final_saved": True})
                tar[i].guide.update({"guide_process": False, "end_guide": True, "end_reason": "b1_inactive_vehicle", "guide_phase": "b1_inactive_target", "_final_saved": True})

            mis[i].guide.setdefault("child_guidance_class", self.source_class if i in self.active_ids else "B1InactiveGuidance")
            mis[i].guide.setdefault("child_guidance_module", self.source_module if i in self.active_ids else __name__)
            self.children.append(child)

        self._propagate_adapter_controls()
        print(f"[multi_main_B1_safe_v9] Adapter initialized {len(self.children)} child guidance objects")

    def one_step_guide(self, mis, tar, meta=None):
        meta = dict(meta or {})
        self._propagate_adapter_controls()
        if not bool(getattr(self, "_allow_update_param", True)):
            meta["b1_online_no_recursive_update"] = True
        for obj in list(mis or []) + list(tar or []):
            if not hasattr(obj, "guide") or obj.guide is None:
                obj.guide = {}
            obj.guide.setdefault("guide_process", True)
            obj.guide.setdefault("end_guide", False)
            obj.guide.setdefault("end_reason", "")
            obj.guide.setdefault("guide_phase", obj.guide.get("guide_phase", ""))

        any_running = False
        max_acc = 0

        for i, (m, t, child) in enumerate(zip(mis, tar, self.children)):
            if i not in self.active_ids:
                if not hasattr(m, "guide") or m.guide is None:
                    m.guide = {}
                if not hasattr(t, "guide") or t.guide is None:
                    t.guide = {}
                m.guide.update({"guide_process": False, "end_guide": True, "end_reason": "b1_inactive_vehicle", "guide_phase": "b1_inactive_missile", "_final_saved": True})
                t.guide.update({"guide_process": False, "end_guide": True, "end_reason": "b1_inactive_vehicle", "guide_phase": "b1_inactive_target", "_final_saved": True})
                continue

            if bool(m.guide.get("end_guide", False)) or (m.guide.get("guide_process", True) is False):
                continue

            case = self.status_params[i] if i < len(self.status_params) else None
            meta_i = dict(meta)
            meta_i.update({"vehicle_index": i, "mis_id": i, "case": case, "status_param": case})
            # Critical B1/V8 fix: V8.2 child guidance performs online prediction by
            # deepcopy(meta["simulation"]) and expects a single-vehicle sim.
            meta_i["simulation"] = B1SingleOnlineSimulation(
                m, t, child, parent=meta.get("simulation", None), vehicle_index=i
            )

            try:
                alive = _call_flexible_one_step(child, m, t, meta_i)
            except Exception as exc:
                # Do not silently hide errors; mark the vehicle and re-raise.
                m.guide["guide_process"] = False
                m.guide["end_guide"] = True
                m.guide["end_reason"] = f"guidance_error_vehicle_{i}_{type(exc).__name__}"
                print(f"[multi_main_B1_safe_v9] ERROR in child guidance vehicle {i}: {type(exc).__name__}: {exc}")
                raise

            if alive is None:
                alive = not bool(m.guide.get("end_guide", False))

            if bool(alive):
                any_running = True
                m.guide["guide_process"] = True
            else:
                m.guide["guide_process"] = False
                m.guide.setdefault("end_guide", True)
                m.guide.setdefault("end_reason", "child_guidance_finished")

            # Keep phase/debug info visible in the CSV.
            m.guide["guide_phase"] = str(getattr(child, "guide_mode", m.guide.get("guide_phase", "")))
            m.guide["child_guidance_class"] = self.source_class
            m.guide["child_guidance_module"] = self.source_module

            if not hasattr(t, "guide") or t.guide is None:
                t.guide = {}
            t.guide.setdefault("guide_process", True)
            t.guide.setdefault("end_guide", False)
            t.guide.setdefault("guide_phase", "target")

            try:
                acc = int(getattr(child, "accurate_mode", 0) or 0)
                max_acc = max(max_acc, acc)
            except Exception:
                pass

        self.accurate_mode = max_acc
        self.guide_process = any_running
        return any_running


def _make_guidance_instance(cls, module_name: str, class_name: str, n: int):
    if _is_multi_guidance_class(cls):
        print("[multi_main_B1_safe_v9] Guidance class classified as MULTI; using direct instance")
        return _construct_direct_guidance(cls, n), "direct_multi"

    print("[multi_main_B1_safe_v9] Guidance class classified as SINGLE/case-based; using multi-vehicle adapter")
    sp = _status_params()
    active = _active_mis_ids(n)
    print(f"[multi_main_B1_safe_v9] Requested B1_ACTIVE_MIS_IDS={sorted(active)}")
    adapter = MultiVehicleGuidanceAdapter(cls, sp, module_name, class_name, active_ids=active)
    return adapter, "single_to_multi_adapter_b1_active_only"


# -----------------------------------------------------------------------------
# Runner utilities
# -----------------------------------------------------------------------------

def _num_vehicles_from_statusparams() -> int:
    sp = _status_params()
    return max(1, len(sp)) if sp else 1


def _safe_store_path() -> str:
    p = getattr(glbs, "STORE_DATA", None)
    if not p or not isinstance(p, str):
        p = os.path.join("store", "data_saved", "multiSimulation_case.csv")
    return p


def _ensure_dir_for_file(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _flush_every_from(obj, default: int = 5000) -> int:
    try:
        fe = int(getattr(obj, "flush_every", default))
        return int(max(1, fe))
    except Exception:
        return int(default)


def _make_datasave(template=None):
    try:
        if template is not None:
            return DataSave(flush_every=_flush_every_from(template))
        return DataSave()
    except TypeError:
        return DataSave()


def _make_datasave_list(n: int, base_store: str):
    _ensure_dir_for_file(base_store)
    return [_make_datasave(None) for _ in range(n)]


def _dataframe_from_db(db) -> pd.DataFrame:
    data = getattr(db, "data", None)
    if callable(data):
        data = data()
    if data is None:
        return pd.DataFrame()
    return data.copy() if hasattr(data, "copy") else pd.DataFrame(data)


def main() -> None:
    GuidanceClass, selected_module, selected_class_name = _load_guidance_class()

    n = _num_vehicles_from_statusparams()
    print(f"[multi_main_B1_safe_v9] StatusParams vehicle count: N={n}")

    mis = [
        Missile(
            motion_equation=ME6D(),
            aerodynamic=AerodynamicCAVH(),
            params=CAVHParams(),
            status=ME6DStatus(),
        )
        for _ in range(n)
    ]
    tar = [Missile(status=MissileStatus()) for _ in range(n)]

    guide, guide_build_mode = _make_guidance_instance(GuidanceClass, selected_module, selected_class_name, n)
    print(f"[multi_main_B1_safe_v9] Guidance build mode: {guide_build_mode}")

    integral = RungeKutta4()
    store_path = _safe_store_path()
    database = _make_datasave_list(n, store_path)

    simulation = SafeMultiMisSimInstance()
    simulation.init(mis=mis, tar=tar, guide=guide, integ=integral, db=database)
    simulation.simulation()

    dbs = simulation.db if isinstance(simulation.db, (list, tuple)) else [simulation.db]
    for db in dbs:
        if hasattr(db, "finalize"):
            try:
                db.finalize()
            except Exception:
                pass

    frames: list[pd.DataFrame] = []
    for i, db in enumerate(dbs):
        df_i = _dataframe_from_db(db)
        if df_i.empty:
            print(f"[multi_main_B1_safe_v9] WARNING: vehicle {i} produced empty DataFrame")
        if "mis_id" not in df_i.columns:
            df_i.insert(0, "mis_id", i)
        frames.append(df_i)

    result = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    for tcol in ["t_local", "global_t", "t"]:
        if tcol in result.columns:
            result = result.sort_values(["mis_id", tcol], kind="mergesort").reset_index(drop=True)
            break

    result["selected_guidance_module"] = selected_module
    result["selected_guidance_class"] = selected_class_name
    result["guidance_build_mode"] = guide_build_mode
    result["settings_alias_to_multiset"] = True

    _ensure_dir_for_file(store_path)
    result.to_csv(store_path, index=False)

    print(f"[multi_main_B1_safe_v9] CSV saved to: {store_path}")
    print("[multi_main_B1_safe_v9] unique mis_id =", result["mis_id"].nunique() if "mis_id" in result.columns else "N/A")
    print("[multi_main_B1_safe_v9] rows =", len(result))


if __name__ == "__main__":
    main()
