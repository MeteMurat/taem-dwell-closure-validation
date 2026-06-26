import argparse
import numpy as np
import pandas as pd

def _num(s):
    return pd.to_numeric(s, errors="coerce")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--h_tol", type=float, default=500.0)
    ap.add_argument("--v_tol", type=float, default=50.0)
    ap.add_argument("--s_tol", type=float, default=5000.0)
    args = ap.parse_args()

    df = pd.read_csv(args.input, low_memory=False)

    # time axis
    if "global_t" not in df.columns:
        if "t" in df.columns:
            df["global_t"] = _num(df["t"])
        else:
            df["global_t"] = np.arange(len(df), dtype=float)

    # required columns
    need = ["taem_err_h_m","taem_err_v_mps","taem_err_sgo_m","global_t"]
    for c in need:
        if c not in df.columns:
            raise SystemExit(f"Missing column: {c}. Run add_taem_event_columns.py first.")

    # normalized distance to TAEM box center (NOT reached metric, just closeness)
    dh = _num(df["taem_err_h_m"]) / float(args.h_tol)
    dv = _num(df["taem_err_v_mps"]) / float(args.v_tol)
    ds = _num(df["taem_err_sgo_m"]) / float(args.s_tol)
    df["_taem_normdist"] = np.sqrt(dh*dh + dv*dv + ds*ds)

    # group
    idcol = "mis_id" if "mis_id" in df.columns else None
    groups = df.groupby(idcol, sort=False) if idcol else [(0, df)]

    rows = []
    for gid, g in groups:
        g = g.sort_values("global_t")

        # closest to TAEM (min normdist)
        i1 = g["_taem_normdist"].idxmin()
        r1 = g.loc[i1]

        # closest approach to target (min s_go) if available
        if "s_go" in g.columns and _num(g["s_go"]).notna().any():
            i2 = _num(g["s_go"]).idxmin()
            r2 = g.loc[i2]
        else:
            i2 = None
            r2 = None

        rows.append({
            "mis_id": gid,
            "t_closest_taem": float(r1["global_t"]),
            "taem_normdist_min": float(r1["_taem_normdist"]),
            "err_h_m_at_closest": float(r1["taem_err_h_m"]),
            "err_v_mps_at_closest": float(r1["taem_err_v_mps"]),
            "err_sgo_m_at_closest": float(r1["taem_err_sgo_m"]),
            "t_min_sgo": (float(r2["global_t"]) if r2 is not None else np.nan),
            "s_go_min": (float(r2["s_go"]) if r2 is not None and "s_go" in r2 else np.nan),
            "err_h_m_at_min_sgo": (float(r2["taem_err_h_m"]) if r2 is not None else np.nan),
            "err_v_mps_at_min_sgo": (float(r2["taem_err_v_mps"]) if r2 is not None else np.nan),
            "err_sgo_m_at_min_sgo": (float(r2["taem_err_sgo_m"]) if r2 is not None else np.nan),
        })

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)
    print("[OK] wrote:", args.out)

if __name__ == "__main__":
    main()