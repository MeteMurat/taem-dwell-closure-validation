import glob
import numpy as np
import pandas as pd
from pathlib import Path

def safe_num(s):
    # handle comma decimals + stray text
    s = s.astype(str).str.replace(",", ".", regex=False)
    s = s.str.replace(r"[^0-9eE\+\-\.]", "", regex=True)
    return pd.to_numeric(s, errors="coerce").astype(float)

def pick_col(df, candidates, forbid_contains=("taem",)):
    cols = []
    for c in df.columns:
        cl = c.lower()
        if any(f in cl for f in forbid_contains):
            continue
        if any(k in cl for k in candidates):
            x = safe_num(df[c])
            if np.isfinite(x).mean() > 0.5:
                cols.append((c, np.nanstd(x)))
    if not cols:
        return None
    # prefer higher variance (real signal)
    cols.sort(key=lambda t: t[1], reverse=True)
    return cols[0][0]

def main():
    runs = glob.glob("store/data_saved/runs/*/multiSimulation_case.csv")
    out_rows = []
    for p in runs:
        run_id = Path(p).parent.name
        df = pd.read_csv(p, low_memory=False)

        idcol = "mis_id" if "mis_id" in df.columns else ("vehicle_id" if "vehicle_id" in df.columns else None)
        if idcol is None:
            df["mis_id"] = 0
            idcol = "mis_id"

        # TAEM reference columns
        if not all(c in df.columns for c in ("HTAEM","VTAEM","STAEM")):
            out_rows.append({"run_id":run_id, "vehicle_id":None, "status":"missing_TAEM_refs"})
            continue

        # pick state columns (best-effort)
        h_col   = pick_col(df, candidates=("alt","h_","height","h"), forbid_contains=("taem",))
        v_col   = pick_col(df, candidates=("vel","speed","v_","v"), forbid_contains=("taem",))
        sgo_col = None
        for c in df.columns:
            cl=c.lower()
            if "s_go" in cl or cl in ("sgo","s_go_m"):
                if "taem" not in cl:
                    x=safe_num(df[c])
                    if np.isfinite(x).mean()>0.5:
                        sgo_col=c; break

        for vid, g in df.groupby(idcol):
            HT = safe_num(g["HTAEM"]).to_numpy()
            VT = safe_num(g["VTAEM"]).to_numpy()
            ST = safe_num(g["STAEM"]).to_numpy()

            status="ok"
            if h_col is None or v_col is None or sgo_col is None:
                status=f"missing_state_cols(h={h_col},v={v_col},sgo={sgo_col})"

            if status!="ok":
                out_rows.append({"run_id":run_id,"vehicle_id":vid,"status":status})
                continue

            h  = safe_num(g[h_col]).to_numpy()
            v  = safe_num(g[v_col]).to_numpy()
            sg = safe_num(g[sgo_col]).to_numpy()

            h_err = np.abs(h - HT)
            v_err = np.abs(v - VT)
            s_err = np.abs(sg - ST)

            def q(x, qq):
                x = x[np.isfinite(x)]
                return float(np.quantile(x, qq)) if x.size else np.nan

            out_rows.append({
                "run_id": run_id,
                "vehicle_id": int(vid),
                "h_col": h_col, "v_col": v_col, "sgo_col": sgo_col,
                "h_err_min_m": float(np.nanmin(h_err)),
                "h_err_p10_m": q(h_err, 0.10),
                "v_err_min_mps": float(np.nanmin(v_err)),
                "v_err_p10_mps": q(v_err, 0.10),
                "sgo_err_min_m": float(np.nanmin(s_err)),
                "sgo_err_p10_m": q(s_err, 0.10),
                "status": "ok"
            })

    outdir = Path("store/data_saved/taem_compare")
    outdir.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(out_rows)
    out.to_csv(outdir/"taem_proximity_by_vehicle.csv", index=False)
    print("[OK] wrote", outdir/"taem_proximity_by_vehicle.csv")

if __name__ == "__main__":
    main()