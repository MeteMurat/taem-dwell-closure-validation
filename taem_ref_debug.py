import numpy as np
import pandas as pd

RUN_CSV = r".\store\data_saved\runs\20260304_084135_smooth\multiSimulation_case.csv"
IDCOL   = "mis_id"

df = pd.read_csv(RUN_CSV, low_memory=False)

HT = float(df["HTAEM"].iloc[0])
VT = float(df["VTAEM"].iloc[0])
ST = float(df["STAEM"].iloc[0])

def safe_num(s):
    return pd.to_numeric(s, errors="coerce").astype(float)

df["t"] = safe_num(df["t"])
df["height"] = safe_num(df["height"])
df["velocity"] = safe_num(df["velocity"])
df["s_go"] = safe_num(df["s_go"])

print(f"TAEM refs: HTAEM={HT} m, VTAEM={VT} m/s, STAEM={ST} m")

for vid, g in df.groupby(IDCOL):
    g = g.sort_values("t")
    t = g["t"].to_numpy()
    h = g["height"].to_numpy()
    v = g["velocity"].to_numpy()
    s = g["s_go"].to_numpy()

    jS = int(np.nanargmin(np.abs(s - ST)))
    jH = int(np.nanargmin(np.abs(h - HT)))
    jV = int(np.nanargmin(np.abs(v - VT)))

    print(f"\nvehicle={vid}")

    print(f"  nearest STAEM (s_go≈{ST:.0f}) @ t={t[jS]:.1f}s:")
    print(f"    s_go={s[jS]:.1f}  (err={s[jS]-ST:+.1f})")
    print(f"    height={h[jS]:.1f} (err={h[jS]-HT:+.1f})")
    print(f"    velocity={v[jS]:.1f} (err={v[jS]-VT:+.1f})")

    print(f"  nearest HTAEM (height≈{HT:.0f}) @ t={t[jH]:.1f}s:")
    print(f"    height={h[jH]:.1f} (err={h[jH]-HT:+.1f})")
    print(f"    velocity={v[jH]:.1f} (err={v[jH]-VT:+.1f})")
    print(f"    s_go={s[jH]:.1f} (err={s[jH]-ST:+.1f})")

    print(f"  nearest VTAEM (velocity≈{VT:.0f}) @ t={t[jV]:.1f}s:")
    print(f"    velocity={v[jV]:.1f} (err={v[jV]-VT:+.1f})")
    print(f"    height={h[jV]:.1f} (err={h[jV]-HT:+.1f})")
    print(f"    s_go={s[jV]:.1f} (err={s[jV]-ST:+.1f})")