import numpy as np
import pandas as pd

def safe_num(s):
    s = s.astype(str).str.replace(",", ".", regex=False)
    s = s.str.replace(r"[^0-9eE\+\-\.]", "", regex=True)
    return pd.to_numeric(s, errors="coerce").astype(float)

RUN_CSV = r".\store\data_saved\runs\20260304_084135_smooth\multiSimulation_case.csv"
IDCOL   = "mis_id"
TOL_H   = 5.0     # m  (kendi box tanımın neyse onu yaz)
TOL_V   = 1.0     # m/s
TOL_SGO = 100.0   # m

df = pd.read_csv(RUN_CSV, low_memory=False)

# state kolonlarını otomatik yakala (taem_* hariç)
def pick_col(cands):
    best = None
    for c in df.columns:
        cl = c.lower()
        if "taem" in cl: 
            continue
        if any(k in cl for k in cands):
            x = safe_num(df[c])
            if np.isfinite(x).mean() > 0.5:
                best = c
                break
    return best

h_col   = pick_col(("alt", "h_", "height", "h"))
v_col   = pick_col(("vel", "speed", "v_", "v"))
sgo_col = None
for c in df.columns:
    cl = c.lower()
    if ("s_go" in cl or cl in ("sgo","s_go_m")) and ("taem" not in cl):
        x = safe_num(df[c])
        if np.isfinite(x).mean() > 0.5:
            sgo_col = c
            break

print("picked:", {"h_col": h_col, "v_col": v_col, "sgo_col": sgo_col})

for vid, g in df.groupby(IDCOL):
    t  = safe_num(g["t"]).to_numpy()
    h  = safe_num(g[h_col]).to_numpy()
    v  = safe_num(g[v_col]).to_numpy()
    sg = safe_num(g[sgo_col]).to_numpy()

    HT = safe_num(g["HTAEM"]).to_numpy()
    VT = safe_num(g["VTAEM"]).to_numpy()
    ST = safe_num(g["STAEM"]).to_numpy()

    h_err = np.abs(h - HT)
    v_err = np.abs(v - VT)
    s_err = np.abs(sg - ST)

    score = np.maximum.reduce([h_err/TOL_H, v_err/TOL_V, s_err/TOL_SGO])
    j = int(np.nanargmin(score))

    print(f"\nvehicle={vid}  t*={t[j]:.1f}  score_min={score[j]:.2f}")
    print(f"  h_err={h_err[j]:.3f} m   (ratio={h_err[j]/TOL_H:.2f})")
    print(f"  v_err={v_err[j]:.3f} m/s (ratio={v_err[j]/TOL_V:.2f})")
    print(f"  sgo_err={s_err[j]:.3f} m (ratio={s_err[j]/TOL_SGO:.2f})")