import argparse
import numpy as np
import pandas as pd

def _num(s):
    return pd.to_numeric(s, errors="coerce")

def add_taem_columns(df: pd.DataFrame,
                     h_tol=500.0, v_tol=50.0, s_tol=5000.0,
                     dwell_sec=3.0,
                     h_ref_col="HTAEM", v_ref_col="VTAEM", s_ref_col="STAEM",
                     time_col_prefer=("global_t", "t")) -> pd.DataFrame:
    # --- time axis ---
    tcol = None
    for c in time_col_prefer:
        if c in df.columns and _num(df[c]).notna().any():
            tcol = c
            break
    if tcol is None:
        df["global_t"] = np.arange(len(df), dtype=float)
        tcol = "global_t"
    else:
        if tcol != "global_t":
            df["global_t"] = _num(df[tcol]).astype(float)

    # --- references from CSV (preferred) ---
    # Fallbacks: if ref cols not present, set NaN (then in_box always False)
    href = _num(df[h_ref_col]) if h_ref_col in df.columns else pd.Series(np.nan, index=df.index)
    vref = _num(df[v_ref_col]) if v_ref_col in df.columns else pd.Series(np.nan, index=df.index)
    sref = _num(df[s_ref_col]) if s_ref_col in df.columns else pd.Series(np.nan, index=df.index)

    # --- states ---
    h = _num(df["height"]) if "height" in df.columns else pd.Series(np.nan, index=df.index)
    v = _num(df["velocity"]) if "velocity" in df.columns else pd.Series(np.nan, index=df.index)
    sgo = _num(df["s_go"]) if "s_go" in df.columns else pd.Series(np.nan, index=df.index)

    df["taem_err_h_m"] = h - href
    df["taem_err_v_mps"] = v - vref
    df["taem_err_sgo_m"] = sgo - sref

    in_box = (
        df["taem_err_h_m"].abs() <= h_tol
    ) & (
        df["taem_err_v_mps"].abs() <= v_tol
    ) & (
        df["taem_err_sgo_m"].abs() <= s_tol
    )

    # If any ref/state missing, in_box must be False
    in_box = in_box & df["taem_err_h_m"].notna() & df["taem_err_v_mps"].notna() & df["taem_err_sgo_m"].notna()
    df["taem_in_box"] = in_box.astype(bool)

    # --- dwell-based reached (per mis_id if present) ---
    if "mis_id" in df.columns:
        groups = df.groupby("mis_id", sort=False)
    else:
        # single group
        groups = [(0, df)]

    df["taem_dwell_time_s"] = 0.0
    df["taem_reached"] = False
    df["taem_t_global"] = np.nan

    for gid, g in groups:
        idx = g.index
        gg = g.sort_values("global_t")
        t = _num(gg["global_t"]).to_numpy()
        ib = gg["taem_in_box"].to_numpy(dtype=bool)

        dwell = np.zeros(len(gg), dtype=float)
        reached = np.zeros(len(gg), dtype=bool)
        taem_t = np.full(len(gg), np.nan, dtype=float)

        acc = 0.0
        reached_flag = False
        reached_time = np.nan

        for i in range(len(gg)):
            dt = 0.0 if i == 0 else max(0.0, float(t[i] - t[i-1]))
            if reached_flag:
                reached[i] = True
                dwell[i] = acc
                taem_t[i] = reached_time
                continue

            if ib[i]:
                acc += dt
            else:
                acc = 0.0

            dwell[i] = acc

            if ib[i] and acc >= dwell_sec:
                reached_flag = True
                reached_time = float(t[i])
                reached[i] = True
                taem_t[i] = reached_time

        # “sticky after reach”: after first True, all subsequent rows True
        if reached_flag:
            first = np.argmax(reached)
            reached[first:] = True
            taem_t[first:] = reached_time

        # write back in original index order
        df.loc[gg.index, "taem_dwell_time_s"] = dwell
        df.loc[gg.index, "taem_reached"] = reached
        df.loc[gg.index, "taem_t_global"] = taem_t

    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--h_tol", type=float, default=500.0)
    ap.add_argument("--v_tol", type=float, default=50.0)
    ap.add_argument("--s_tol", type=float, default=5000.0)
    ap.add_argument("--dwell", type=float, default=3.0)
    args = ap.parse_args()

    df = pd.read_csv(args.input, low_memory=False)
    df = add_taem_columns(df,
                          h_tol=args.h_tol, v_tol=args.v_tol, s_tol=args.s_tol,
                          dwell_sec=args.dwell)

    df.to_csv(args.out, index=False)
    cols = [c for c in df.columns if c.startswith("taem_")]
    print("[OK] wrote:", args.out)
    print("[OK] taem cols:", cols)
    if "taem_reached" in df.columns:
        print("[OK] taem_reached unique:", pd.unique(df["taem_reached"]))

if __name__ == "__main__":
    main()