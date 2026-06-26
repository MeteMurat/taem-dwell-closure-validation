# taem_err_summary.py
import glob
import numpy as np
import pandas as pd
from pathlib import Path

def safe_num(s): 
    return pd.to_numeric(s, errors="coerce").astype(float)

def pick_idcol(df):
    for c in ("mis_id","vehicle_id","id"):
        if c in df.columns: return c
    df["mis_id"]=0
    return "mis_id"

def main():
    runs = glob.glob("store/data_saved/runs/*/multiSimulation_case.csv")
    rows=[]
    for p in runs:
        run_id = Path(p).parent.name
        df = pd.read_csv(p, low_memory=False)
        idcol = pick_idcol(df)

        need = ["taem_err_h_m","taem_err_v_mps","taem_err_sgo_m"]
        if not all(c in df.columns for c in need):
            rows.append({"run_id":run_id,"vehicle_id":None,"status":"missing_err_cols"})
            continue

        for vid,g in df.groupby(idcol):
            h = np.abs(safe_num(g["taem_err_h_m"]).to_numpy())
            v = np.abs(safe_num(g["taem_err_v_mps"]).to_numpy())
            s = np.abs(safe_num(g["taem_err_sgo_m"]).to_numpy())

            def q(x, qq):
                x = x[np.isfinite(x)]
                return float(np.quantile(x, qq)) if x.size else np.nan

            rows.append({
                "run_id": run_id,
                "vehicle_id": int(vid),
                "h_abs_min": float(np.nanmin(h)),
                "h_abs_p10": q(h,0.10),
                "h_abs_p50": q(h,0.50),
                "v_abs_min": float(np.nanmin(v)),
                "v_abs_p10": q(v,0.10),
                "v_abs_p50": q(v,0.50),
                "sgo_abs_min": float(np.nanmin(s)),
                "sgo_abs_p10": q(s,0.10),
                "sgo_abs_p50": q(s,0.50),
                "status":"ok",
            })

    outdir = Path("store/data_saved/taem_compare")
    outdir.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows)
    out.to_csv(outdir/"taem_err_summary_by_vehicle.csv", index=False)
    print("[OK] wrote", outdir/"taem_err_summary_by_vehicle.csv")

if __name__ == "__main__":
    main()