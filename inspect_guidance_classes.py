# -*- coding: utf-8 -*-
"""Inspect local guidance multiMissileGuideInstance*.py modules and list class names."""
from __future__ import annotations
import importlib
import inspect
from pathlib import Path

mods = []
gdir = Path("guidance")
if gdir.exists():
    for p in sorted(gdir.glob("multiMissileGuideInstance*.py")):
        if not p.name.startswith("__"):
            mods.append(f"guidance.{p.stem}")

print("[inspect] discovered modules:")
for m in mods:
    print("  -", m)

for m in mods:
    print("\n[inspect]", m)
    try:
        mod = importlib.import_module(m)
    except Exception as exc:
        print("  IMPORT_ERROR:", type(exc).__name__, exc)
        continue
    classes = []
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        classes.append((name, getattr(obj, "__module__", "")))
    if not classes:
        print("  no classes found")
    for name, module in classes:
        mark = "LOCAL" if module == m else "imported"
        print(f"  class {name:<45} module={module} [{mark}]")
