import pandas as pd
import numpy as np
from pathlib import Path

csv = Path(r"store\data_saved\phase2_B2_exact_single_combined.csv")
outdir = Path(r"store\data_saved\phase2_B2_numeric_diff_audit")
outdir.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(csv)
if "mis_id" not in df.columns:
    raise RuntimeError("mis_id column missing")

def to_numeric_safe(s):
    """
    Numeric + boolean-safe conversion.
    True/False and string true/false are converted to 1/0.
    Other nonnumeric values become NaN.
    """
    if s.dtype == bool:
        return s.astype(float)

    ss = s.copy()

    if ss.dtype == object:
        lower = ss.astype(str).str.strip().str.lower()
        mapped = lower.map({
            "true": 1.0,
            "false": 0.0,
            "yes": 1.0,
            "no": 0.0,
            "y": 1.0,
            "n": 0.0,
            "1": 1.0,
            "0": 0.0,
        })
        numeric = pd.to_numeric(ss, errors="coerce")
        numeric = numeric.where(numeric.notna(), mapped)
        return numeric.astype(float)

    return pd.to_numeric(ss, errors="coerce").astype(float)

groups = {int(k): v.reset_index(drop=True) for k, v in df.groupby("mis_id")}
mids = sorted(groups.keys())

important = [
    "global_t", "longitude", "latitude", "height", "velocity",
    "path_angle", "heading_angle", "s_go", "delta_psi",
    "bank_angle", "attack_angle", "L12D", "E",
    "taem_h_err", "taem_v_err", "taem_s_go_err",
    "taem_in_box", "taem_reached", "taem_success_latched"
]
important = [c for c in important if c in df.columns]

rows = []
lines = []
lines.append("PHASE 2 / B2 NUMERIC DIFFERENCE AUDIT")
lines.append("=" * 72)
lines.append(f"csv: {csv}")
lines.append(f"mis_ids: {mids}")
lines.append("")

for i in range(len(mids)):
    for j in range(i + 1, len(mids)):
        a, b = mids[i], mids[j]
        ga, gb = groups[a], groups[b]
        lines.append(f"--- mis{a} vs mis{b} ---")
        lines.append(f"same_shape: {ga.shape == gb.shape}")

        for c in important:
            if c not in ga.columns or c not in gb.columns:
                continue

            xa = to_numeric_safe(ga[c])
            xb = to_numeric_safe(gb[c])
            n = min(len(xa), len(xb))

            arr_a = xa.iloc[:n].to_numpy(dtype=float)
            arr_b = xb.iloc[:n].to_numpy(dtype=float)
            d = arr_a - arr_b

            finite = np.isfinite(d)
            if finite.any():
                max_abs = float(np.nanmax(np.abs(d[finite])))
                mean_abs = float(np.nanmean(np.abs(d[finite])))
            else:
                max_abs = np.nan
                mean_abs = np.nan

            rows.append({
                "pair": f"mis{a}_vs_mis{b}",
                "column": c,
                "max_abs_diff": max_abs,
                "mean_abs_diff": mean_abs
            })
            lines.append(f"{c:24s} max_abs_diff={max_abs:.12g} mean_abs_diff={mean_abs:.12g}")
        lines.append("")

out = pd.DataFrame(rows)
out.to_csv(outdir / "b2_numeric_diff_by_pair.csv", index=False)

with open(outdir / "b2_numeric_diff_audit.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print("")
print("[OK] wrote:", outdir / "b2_numeric_diff_audit.txt")
print("[OK] wrote:", outdir / "b2_numeric_diff_by_pair.csv")
