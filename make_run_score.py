import argparse
import pandas as pd
import numpy as np

def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _clean_event(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "event" in df.columns:
        df["event"] = df["event"].astype(str).str.strip()
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--closest", required=True)
    ap.add_argument("--taem_closest", required=True)
    ap.add_argument("--event_snapshots", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    car = _clean_cols(pd.read_csv(args.closest, low_memory=False))
    tcr = _clean_cols(pd.read_csv(args.taem_closest, low_memory=False))
    ev  = _clean_event(_clean_cols(pd.read_csv(args.event_snapshots, low_memory=False)))

    # mis_id type normalize
    for df in (car, tcr, ev):
        if "mis_id" in df.columns:
            df["mis_id"] = pd.to_numeric(df["mis_id"], errors="coerce").astype("Int64")

    # Overfly ratio: post_s_go / ca_s_go
    if ("ca_s_go" in car.columns) and ("post_s_go" in car.columns):
        car["overfly_ratio"] = np.where(
            pd.to_numeric(car["ca_s_go"], errors="coerce") != 0,
            pd.to_numeric(car["post_s_go"], errors="coerce") / pd.to_numeric(car["ca_s_go"], errors="coerce"),
            np.nan
        )
    else:
        car["overfly_ratio"] = np.nan

    # Pull h_near_HTAEM time from event_snapshots (best for phase dt)
    # (If missing, we'll leave NaN and still write the score table.)
    t_h = None
    if "event" in ev.columns:
        # be tolerant to case
        ev["event_l"] = ev["event"].astype(str).str.lower()
        # canonical match
        hmask = ev["event_l"].isin(["h_near_htaem", "h_near_htAEM".lower(), "h_near_htAEM".lower()])
        if hmask.any():
            t_h = ev.loc[hmask, ["mis_id"] + ([c for c in ["t", "global_t", "t_local"] if c in ev.columns][:1])]
            tcol = [c for c in ["t", "global_t", "t_local"] if c in ev.columns][:1][0]
            t_h = t_h.rename(columns={tcol: "t_h_near"})

    # Base merge: closest approach + TAEM-closest report
    out = car.merge(tcr, on="mis_id", how="left")

    # Bring t_h_near (optional)
    if t_h is not None and "t_h_near" in t_h.columns:
        out = out.merge(t_h[["mis_id", "t_h_near"]], on="mis_id", how="left")
    else:
        out["t_h_near"] = np.nan

    # Phase dt: use t_min_sgo from taem_closest_report (always available there)
    if "t_min_sgo" in out.columns:
        out["phase_dt_h_minus_min_sgo_s"] = pd.to_numeric(out["t_h_near"], errors="coerce") - pd.to_numeric(out["t_min_sgo"], errors="coerce")
    else:
        out["phase_dt_h_minus_min_sgo_s"] = np.nan

    # Keep a compact score table
    keep = [c for c in [
        "mis_id",
        "t_ca_s", "ca_s_go", "post_s_go", "overfly_ratio",
        "t_closest_taem", "taem_normdist_min",
        "err_h_m_at_closest", "err_v_mps_at_closest", "err_sgo_m_at_closest",
        "t_min_sgo", "s_go_min",
        "t_h_near", "phase_dt_h_minus_min_sgo_s",
        "sgo_h_near"  # may not exist; will be ignored below
    ] if c in out.columns]

    out = out[keep].sort_values("mis_id")
    out.to_csv(args.out, index=False)
    print("[OK] wrote:", args.out)
    if "event" in ev.columns:
        print("[INFO] event types:", sorted(set(ev["event"].astype(str).str.strip().tolist())))

if __name__ == "__main__":
    main()