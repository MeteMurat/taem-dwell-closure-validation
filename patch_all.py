import re, shutil
from pathlib import Path

def patch_multi_main():
    p = Path("multi_main.py")
    if not p.exists():
        print("[SKIP] multi_main.py not found")
        return
    s = p.read_text(encoding="utf-8")

    # Ensure import numpy (used for cfg stamping in some versions)
    if "import numpy as np" not in s:
        s = s.replace("import os\nimport pandas as pd\n", "import os\nimport pandas as pd\nimport numpy as np\n")

    pat = r"def _safe_store_path\(\) -> str:\n.*?\n\s*return p\n"
    if not re.search(pat, s, flags=re.S):
        print("[WARN] _safe_store_path pattern not found; skipping store override patch.")
        p.write_text(s, encoding="utf-8")
        return

    new_fun = (
        "def _safe_store_path() -> str:\n"
        "    \"\"\"Output CSV path resolution.\n"
        "    Priority:\n"
        "      1) EG_STORE_DATA env var (set by run_pipeline)\n"
        "      2) multiset.STORE_DATA\n"
        "      3) default store/data_saved/multiSimulation_case.csv\n"
        "    \"\"\"\n"
        "    p_env = os.environ.get('EG_STORE_DATA', '').strip()\n"
        "    if p_env:\n"
        "        return p_env\n"
        "    p = getattr(glbs, 'STORE_DATA', None)\n"
        "    if not p or not isinstance(p, str):\n"
        "        p = os.path.join('store', 'data_saved', 'multiSimulation_case.csv')\n"
        "    return p\n"
    )
    s2 = re.sub(pat, new_fun, s, count=1, flags=re.S)
    p.write_text(s2, encoding="utf-8")
    print("[OK] patched multi_main.py (_safe_store_path uses EG_STORE_DATA)")

def patch_run_pipeline():
    p = Path("run_pipeline.py")
    if not p.exists():
        print("[SKIP] run_pipeline.py not found")
        return
    s = p.read_text(encoding="utf-8")

    # ensure shutil imported
    if "import shutil" not in s:
        s = s.replace("import subprocess\n", "import subprocess\nimport shutil\n")

    # add EG_RUN_ID if missing
    if 'env["EG_RUN_ID"]' not in s:
        s = s.replace(
            'env["EG_PROFILE"] = args.profile\n    env["EG_STORE_DATA"] = str(raw_csv)\n',
            'env["EG_PROFILE"] = args.profile\n    env["EG_STORE_DATA"] = str(raw_csv)\n    env["EG_RUN_ID"] = run_id\n'
        )

    # add fallback copy if raw_csv not created
    block_pat = r"run\(\[sys\.executable,\s*\"multi_main\.py\".*?\)\s*\n\s*if not raw_csv\.exists\(\):\s*\n\s*raise FileNotFoundError\(f\"Simulation did not produce: \{raw_csv\}\"\)\s*"
    if re.search(block_pat, s, flags=re.S):
        repl = (
            'run([sys.executable, "multi_main.py"], env=env)\n'
            '    if not raw_csv.exists():\n'
            "        # Fallback: multi_main may have written to default path\n"
            "        default_csv = Path('store') / 'data_saved' / 'multiSimulation_case.csv'\n"
            "        if default_csv.exists():\n"
            "            raw_csv.parent.mkdir(parents=True, exist_ok=True)\n"
            "            shutil.copy2(default_csv, raw_csv)\n"
            "    if not raw_csv.exists():\n"
            '        raise FileNotFoundError(f"Simulation did not produce: {raw_csv}")\n'
        )
        s = re.sub(block_pat, repl, s, count=1, flags=re.S)

    p.write_text(s, encoding="utf-8")
    print("[OK] patched run_pipeline.py (EG_RUN_ID + fallback copy)")

def patch_step_len():
    # Patch core multi sim to actually use INI_STEP/MIN_H
    for path in [r"core\multiMissileSimInstance.py", r"core\multiMissileSimInstance_MVE.py"]:
        p = Path(path)
        if not p.exists():
            continue
        s = p.read_text(encoding="utf-8")
        if "def step_len" in s:
            print(f"[OK] step_len already exists in {p}")
            continue

        candidates = [
            r"(class\s+MultiMisSimInstance[^\n]*:\n)",
            r"(class\s+MultiMissileSimInstance[^\n]*:\n)",
            r"(class\s+MultiMissileSim[^\n]*:\n)",
        ]
        rep = (
            r"\1"
            "    def step_len(self) -> float:\n"
            "        import multiset as glbs\n"
            "        h = float(getattr(glbs, 'INI_STEP', 1.0))\n"
            "        hmin = float(getattr(glbs, 'MIN_H', 1e-3))\n"
            "        return max(hmin, h)\n\n"
        )

        s2 = s
        patched = False
        for pat in candidates:
            s_try = re.sub(pat, rep, s, count=1)
            if s_try != s:
                s2 = s_try
                patched = True
                break

        if not patched:
            print(f"[ERR] Could not patch step_len (class not found) in: {p}")
            continue

        p.write_text(s2, encoding="utf-8")
        print(f"[OK] patched step_len into {p}")

if __name__ == "__main__":
    patch_multi_main()
    patch_run_pipeline()
    patch_step_len()
