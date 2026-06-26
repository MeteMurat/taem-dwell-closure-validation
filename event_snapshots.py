import argparse
import numpy as np
import pandas as pd

def _num(s):
    return pd.to_numeric(s, errors="coerce")

def pick_row_nearest(g, col, target):
    x = _num(g[col])
    i = (x - target).abs().idxmin()
    return g.loc[i]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--h_tol", type=float, default=500.0)
    ap.add_argument("--v_tol", type=float, default=50.0)
    ap.add_argument("--s_tol", type=float, default=5000.0)
    args = ap.parse_args()

    df = pd.read_csv(args.input, low_memory=False)

    # time axis -> global_t
    if "global_t" not in df.columns:
        if "t" in df.columns and _num(df["t"]).notna().any():
            df["global_t"] = _num(df["t"])
        else:
            df["global_t"] = np.arange(len(df), dtype=float)

    # ensure errors exist (if not, compute from TAEM refs)
    if "taem_err_h_m" not in df.columns:
        df["taem_err_h_m"]   = _num(df["height"])   - _num(df["HTAEM"])
        df["taem_err_v_mps"] = _num(df["velocity"]) - _num(df["VTAEM"])
        df["taem_err_sgo_m"] = _num(df["s_go"])     - _num(df["STAEM"])

    dh = _num(df["taem_err_h_m"]) / args.h_tol
    dv = _num(df["taem_err_v_mps"]) / args.v_tol
    ds = _num(df["taem_err_sgo_m"]) / args.s_tol
    df["_taem_normdist"] = np.sqrt(dh*dh + dv*dv + ds*ds)

    groups = df.groupby("mis_id", sort=False) if "mis_id" in df.columns else [(0, df)]

    rows = []
    for mid, g in groups:
        g = g.sort_values("global_t")

        # TAEM refs (assume constant)
        HT = float(_num(g["HTAEM"]).dropna().iloc[0]) if "HTAEM" in g.columns else np.nan
        VT = float(_num(g["VTAEM"]).dropna().iloc[0]) if "VTAEM" in g.columns else np.nan

        r_taem = g.loc[g["_taem_normdist"].idxmin()]
        r_sgo  = g.loc[_num(g["s_go"]).idxmin()] if "s_go" in g.columns else r_taem
        r_v    = pick_row_nearest(g, "velocity", VT) if np.isfinite(VT) and "velocity" in g.columns else r_taem
        r_h    = pick_row_nearest(g, "height", HT) if np.isfinite(HT) and "height" in g.columns else r_taem

        def pack(tag, r):
            return {
                "mis_id": int(mid),
                "event": tag,
                "t": float(r["global_t"]),
                "height_m": float(r["height"]),
                "velocity_mps": float(r["velocity"]),
                "s_go_m": float(r["s_go"]) if "s_go" in r.index else np.nan,
                "taem_normdist": float(r["_taem_normdist"]),
                "err_h_m": float(r["taem_err_h_m"]),
                "err_v_mps": float(r["taem_err_v_mps"]),
                "err_sgo_m": float(r["taem_err_sgo_m"]),
            }

        rows += [
            pack("closest_TAEM", r_taem),
            pack("min_s_go", r_sgo),
            pack("v_near_VTAEM", r_v),
            pack("h_near_HTAEM", r_h),
        ]

    out = pd.DataFrame(rows).sort_values(["mis_id", "event"])
    out.to_csv(args.out, index=False)
    print("[OK] wrote:", args.out)

if __name__ == "__main__":
    main()