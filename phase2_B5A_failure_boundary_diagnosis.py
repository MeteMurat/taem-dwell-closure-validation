# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd

def wilson_ci(k,n,z=1.959963984540054):
    if n<=0: return (float("nan"), float("nan"))
    p=k/n; denom=1+z*z/n
    center=(p+z*z/(2*n))/denom
    margin=z*math.sqrt((p*(1-p)+z*z/(4*n))/n)/denom
    return max(0.0, center-margin), min(1.0, center+margin)

def pick_col(df, cands):
    return next((c for c in cands if c in df.columns), None)

def is_pass(x):
    return str(x).strip().upper() in {"PASS","PASS_STRICT","TRUE","1","B5A_CASE_PASS_ROLE_DISTINCT"}

def boolish(x):
    return str(x).strip().lower() in {"true","1","yes","y"}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input", default=r"store\data_saved\phase2_B5A_dispersion_grid_report\phase2_B5A_by_vehicle_all.csv")
    ap.add_argument("--outdir", default=r"store\data_saved\phase2_B5A_failure_boundary_report")
    args=ap.parse_args()
    inp=Path(args.input); outdir=Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    if not inp.exists(): raise FileNotFoundError(inp)
    df=pd.read_csv(inp)
    hcol=pick_col(df,["height_delta_m","h_delta_m","height_delta"])
    vcol=pick_col(df,["velocity_delta_mps","v_delta_mps","velocity_delta"])
    dcol=pick_col(df,["decision","b1_vehicle_decision","vehicle_decision"])
    lcol=pick_col(df,["label","failure_label","classification"])
    casecol=pick_col(df,["case_id","case","run_id"])
    vidcol=pick_col(df,["vehicle_id","mis_id","id","vehicle"])
    if not hcol or not vcol or not dcol:
        raise RuntimeError(f"Required columns missing. Available: {list(df.columns)}")
    d=df.copy()
    d["_h"]=pd.to_numeric(d[hcol], errors="coerce")
    d["_v"]=pd.to_numeric(d[vcol], errors="coerce")
    d["_pass"]=d[dcol].map(is_pass)
    if casecol is None:
        d["_case_id"]=d.apply(lambda r: f"h{r['_h']:+.0f}_v{r['_v']:+.0f}", axis=1); casecol="_case_id"
    if vidcol is None:
        d["_vehicle_slot_in_case"]=d.groupby([hcol,vcol]).cumcount(); vidcol="_vehicle_slot_in_case"
    metric_cols=["taem_dwell_s_final_logged","taem_dwell_count_final_logged","taem_h_err_final","taem_v_err_final","taem_s_go_err_final","taem_h_err_min_abs","taem_v_err_min_abs","taem_s_go_err_min_abs","s_go_min","s_go_final","last_close_pass_escape"]
    present=[c for c in metric_cols if c in d.columns]
    case_rows=[]
    for (h,v),g in d.groupby(["_h","_v"], dropna=False):
        n=len(g); k=int(g["_pass"].sum()); lo,hi=wilson_ci(k,n)
        close=int(g["last_close_pass_escape"].map(boolish).sum()) if "last_close_pass_escape" in g else 0
        labels="; ".join(sorted(set(str(x) for x in g[lcol].dropna().tolist()))) if lcol else ""
        case_rows.append({"height_delta_m":h,"velocity_delta_mps":v,"n":n,"n_pass":k,"pass_rate":k/n if n else np.nan,"pass_rate_ci_low":lo,"pass_rate_ci_high":hi,"n_fail":n-k,"n_close_pass_escape":close,"labels_seen":labels})
    case_summary=pd.DataFrame(case_rows).sort_values(["velocity_delta_mps","height_delta_m"])
    def marginal(col,label):
        rows=[]
        for val,g in d.groupby(col, dropna=False):
            n=len(g); k=int(g["_pass"].sum()); lo,hi=wilson_ci(k,n)
            rows.append({label:val,"n":n,"n_pass":k,"pass_rate":k/n if n else np.nan,"pass_rate_ci_low":lo,"pass_rate_ci_high":hi,"n_fail":n-k})
        return pd.DataFrame(rows).sort_values(label)
    by_v=marginal("_v","velocity_delta_mps")
    by_h=marginal("_h","height_delta_m")
    rows=[]
    for vid,g in d.groupby(vidcol, dropna=False):
        n=len(g); k=int(g["_pass"].sum()); lo,hi=wilson_ci(k,n)
        rows.append({"vehicle_or_slot":vid,"n":n,"n_pass":k,"pass_rate":k/n if n else np.nan,"pass_rate_ci_low":lo,"pass_rate_ci_high":hi,"n_fail":n-k})
    by_vehicle=pd.DataFrame(rows)
    failures=d.loc[~d["_pass"]].copy()
    show=[]
    for c in [casecol,hcol,vcol,vidcol,"role","heading_delta_deg",dcol,lcol]+present:
        if c and c in failures.columns and c not in show: show.append(c)
    failures_out=failures[show].copy() if len(failures) else pd.DataFrame(columns=show)
    lines=[]
    lines.append("PHASE 2 / B5A FAILURE-BOUNDARY DIAGNOSIS")
    lines.append("="*72)
    lines.append(f"input_csv: {inp}")
    lines.append(f"rows: {len(d)}")
    lines.append(f"vehicle_id_column_used: {vidcol}")
    lines.append("")
    lines.append("[CASE SUMMARY]")
    for _,r in case_summary.iterrows():
        lines.append(f"h={r['height_delta_m']:+.0f} m, v={r['velocity_delta_mps']:+.0f} m/s | pass={int(r['n_pass'])}/{int(r['n'])} | rate={r['pass_rate']:.3f} | close_escape={int(r['n_close_pass_escape'])} | labels={r['labels_seen']}")
    lines.append("")
    lines.append("[MARGINAL BY VELOCITY]")
    for _,r in by_v.iterrows():
        lines.append(f"v={r['velocity_delta_mps']:+.0f} m/s | pass={int(r['n_pass'])}/{int(r['n'])} rate={r['pass_rate']:.3f} CI95=[{r['pass_rate_ci_low']:.3f},{r['pass_rate_ci_high']:.3f}]")
    lines.append("")
    lines.append("[MARGINAL BY HEIGHT]")
    for _,r in by_h.iterrows():
        lines.append(f"h={r['height_delta_m']:+.0f} m | pass={int(r['n_pass'])}/{int(r['n'])} rate={r['pass_rate']:.3f} CI95=[{r['pass_rate_ci_low']:.3f},{r['pass_rate_ci_high']:.3f}]")
    lines.append("")
    v_rates={float(r["velocity_delta_mps"]):float(r["pass_rate"]) for _,r in by_v.iterrows() if pd.notna(r["velocity_delta_mps"])}
    positive_fragile=any(v>0 and rate<0.5 for v,rate in v_rates.items())
    nonpos_ok=all(rate>=0.75 for v,rate in v_rates.items() if v<=0)
    lines.append("[DIAGNOSIS]")
    if positive_fragile: lines.append("- Positive initial velocity perturbation is the dominant fragile direction in the tested grid.")
    if nonpos_ok: lines.append("- Non-positive velocity perturbations are comparatively stable in the tested grid.")
    if "last_close_pass_escape" in d.columns:
        lines.append(f"- Failure rows with close_pass_escape=True: {int(failures['last_close_pass_escape'].map(boolish).sum())}/{len(failures)}")
    if lcol:
        lines.append(f"- Failure labels observed: {sorted(set(str(x) for x in failures[lcol].dropna().tolist()))}")
    lines.append("")
    lines.append("[RECOMMENDED NEXT STEP]")
    lines.append("Do not move directly to broad Monte Carlo over ±50 m/s velocity before resolving the positive-velocity boundary.")
    lines.append("Recommended B5A-R boundary refinement:")
    lines.append("  heading_spread = [-2, 0, +2] deg")
    lines.append("  height_delta_m = [-500, 0, +500]")
    lines.append("  velocity_delta_mps = [+10, +20, +30, +40, +50]")
    lines.append("This will locate the positive-velocity robustness threshold before B5B Monte Carlo.")
    case_summary.to_csv(outdir/"b5a_failure_boundary_by_case.csv", index=False)
    by_v.to_csv(outdir/"b5a_failure_boundary_by_velocity.csv", index=False)
    by_h.to_csv(outdir/"b5a_failure_boundary_by_height.csv", index=False)
    by_vehicle.to_csv(outdir/"b5a_failure_boundary_by_vehicle_or_slot.csv", index=False)
    failures_out.to_csv(outdir/"b5a_failure_rows.csv", index=False)
    summary="\n".join(lines)
    (outdir/"b5a_failure_boundary_summary.txt").write_text(summary, encoding="utf-8")
    (outdir/"b5a_failure_boundary_summary.json").write_text(json.dumps({"input_csv":str(inp),"rows":int(len(d)),"vehicle_id_column_used":vidcol,"positive_velocity_fragile":positive_fragile,"nonpositive_velocity_comparatively_stable":nonpos_ok,"n_failures":int(len(failures)),"recommendation":"B5A-R positive-velocity boundary refinement before broad Monte Carlo"},ensure_ascii=False,indent=2), encoding="utf-8")
    print(summary)
    print("\n[OK] wrote:", outdir/"b5a_failure_boundary_summary.txt")
    print("[OK] wrote:", outdir/"b5a_failure_rows.csv")
if __name__=="__main__":
    main()
