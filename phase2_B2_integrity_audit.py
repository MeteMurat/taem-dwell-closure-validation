import pandas as pd
from pathlib import Path
import json

csv = Path(r"store\data_saved\phase2_B2_exact_single_combined.csv")
outdir = Path(r"store\data_saved\phase2_B2_integrity_audit")
outdir.mkdir(parents=True, exist_ok=True)

if not csv.exists():
    raise FileNotFoundError(f"CSV not found: {csv}")

df = pd.read_csv(csv)

cols = [
    "mis_id", "global_t", "longitude", "latitude", "height", "velocity",
    "path_angle", "heading_angle", "s_go", "delta_psi",
    "taem_success_latched", "taem_reached_ever", "taem_reached_event",
    "taem_reached", "taem_in_box", "end_reason",
    "taem_h_err", "taem_v_err", "taem_s_go_err",
    "bank_angle", "attack_angle",
    "psi_bias_cmd", "psi_bias_w", "psi_bias_state",
    "guide_phase", "Phase2Role"
]
cols = [c for c in cols if c in df.columns]

lines = []
lines.append("PHASE 2 / B2 INTEGRITY AUDIT")
lines.append("=" * 72)
lines.append(f"csv: {csv}")
lines.append(f"rows: {len(df)}")
lines.append(f"columns: {len(df.columns)}")

if "mis_id" not in df.columns:
    lines.append("ERROR: mis_id column missing")
else:
    mids = sorted(df["mis_id"].dropna().unique().tolist())
    lines.append(f"mis_id unique: {mids}")

summary_rows = []
hash_rows = []

for mid, g in df.groupby("mis_id"):
    tcol = "global_t" if "global_t" in g.columns else None
    if tcol:
        g = g.sort_values(tcol)
    first = g.iloc[0]
    last = g.iloc[-1]

    lines.append("")
    lines.append(f"--- mis{mid} ---")
    lines.append(f"n_rows: {len(g)}")

    row = {"mis_id": mid, "n_rows": len(g)}
    for c in cols:
        if c == "mis_id":
            continue
        fv = first.get(c, None)
        lv = last.get(c, None)
        lines.append(f"{c:24s} first={fv} | last={lv}")
        row[f"{c}_first"] = fv
        row[f"{c}_last"] = lv
    summary_rows.append(row)

    use = g.drop(columns=["mis_id"], errors="ignore")
    try:
        h = int(pd.util.hash_pandas_object(use, index=False).sum())
    except Exception as e:
        h = None
        lines.append(f"hash_error: {e}")
    hash_rows.append({"mis_id": mid, "hash_without_mis_id": h})

lines.append("")
lines.append("=== QUICK HASH CHECK PER VEHICLE ===")
for r in hash_rows:
    lines.append(f"mis{r['mis_id']}: hash_without_mis_id={r['hash_without_mis_id']}")

# Pairwise equality check after dropping mis_id
lines.append("")
lines.append("=== PAIRWISE SHAPE/HASH WARNING ===")
groups = {mid: g.drop(columns=["mis_id"], errors="ignore").reset_index(drop=True)
          for mid, g in df.groupby("mis_id")}
mids = list(groups.keys())
for i in range(len(mids)):
    for j in range(i + 1, len(mids)):
        a, b = mids[i], mids[j]
        same_shape = groups[a].shape == groups[b].shape
        same_values = False
        if same_shape:
            try:
                same_values = groups[a].equals(groups[b])
            except Exception:
                same_values = False
        lines.append(f"mis{a} vs mis{b}: same_shape={same_shape}, identical_without_mis_id={same_values}")

summary_df = pd.DataFrame(summary_rows)
hash_df = pd.DataFrame(hash_rows)

summary_df.to_csv(outdir / "b2_integrity_first_last.csv", index=False)
hash_df.to_csv(outdir / "b2_integrity_hashes.csv", index=False)

with open(outdir / "b2_integrity_audit.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

with open(outdir / "b2_integrity_audit.json", "w", encoding="utf-8") as f:
    json.dump({
        "csv": str(csv),
        "rows": int(len(df)),
        "mis_ids": sorted([int(x) for x in df["mis_id"].dropna().unique().tolist()]) if "mis_id" in df.columns else [],
        "hashes": hash_rows,
    }, f, ensure_ascii=False, indent=2)

print("\n".join(lines))
print("")
print("[OK] wrote:", outdir / "b2_integrity_audit.txt")
print("[OK] wrote:", outdir / "b2_integrity_first_last.csv")
print("[OK] wrote:", outdir / "b2_integrity_hashes.csv")
