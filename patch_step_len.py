import pathlib, re, sys

def patch_file(path):
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[SKIP] not found: {p}")
        return

    s = p.read_text(encoding="utf-8")

    if "def step_len" in s:
        print(f"[OK] step_len already exists in {p}")
        return

    # Try several likely class names
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
    for pat in candidates:
        s2_try = re.sub(pat, rep, s, count=1)
        if s2_try != s:
            s2 = s2_try
            break

    if s2 == s:
        print(f"[ERR] Could not patch (class not found) in: {p}")
        return

    p.write_text(s2, encoding="utf-8")
    print(f"[OK] patched step_len into {p}")

if __name__ == "__main__":
    patch_file(r"core\multiMissileSimInstance.py")
    patch_file(r"core\multiMissileSimInstance_MVE.py")
