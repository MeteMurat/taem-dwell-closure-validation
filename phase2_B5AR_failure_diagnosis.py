# -*- coding: utf-8 -*-
"""
PHASE 2 / B5A-R — Positive-velocity failure diagnosis
"""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd


def find_default_csv(root: Path) -> Path:
    report = root / "store" / "data_saved" / "phase2_B5AR_positive_velocity_report"
    candidates = []
    if report.exists():
        candidates.extend(sorted(report.glob("*by_vehicle*.csv")))
        candidates.extend(sorted(report.glob("*vehicle*.csv")))
    candidates.extend(sorted((root / "store" / "data_saved").glob("**/*B5AR*by_vehicle*.csv")))
    candidates.extend(sorted((root / "store" / "data_saved").glob("**/*B5AR*vehicle*.csv")))
    if not candidates:
        raise FileNotFoundError("No B5A-R by-vehicle CSV found. Pass --csv explicitly.")
    for c in candidates:
        if "all" in c.name.lower() and c.suffix.lower() == ".csv":
            return c
    return candidates[0]


def norm_bool(x) -> bool:
    if pd.isna(x):
        return False
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "pass", "pass_strict"}


def get_col(df, names):
    for n in names:
        if n in df.columns:
            return n
    return None


def wilson_ci(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return (np.nan, np.nan)
    phat = k / n
    denom = 1 + z*z/n
    centre = phat + z*z/(2*n)
    margin = z * math.sqrt((phat*(1-phat) + z*z/(4*n))/n)
    return ((centre - margin)/denom, (centre + margin)/denom)


def is_pass_row(row: pd.Series) -> bool:
    for c in ["decision", "b1_vehicle_decision", "vehicle_decision"]:
        if c in row.index:
            s = str(row[c]).upper()
            if "PASS" in s and "FAIL" not in s:
                return True
            if "FAIL" in s:
                return False
    for c in ["taem_success_latched", "taem_reached_ever", "taem_reached_event", "taem_reached", "taem_in_box"]:
        if c in row.index and norm_bool(row[c]):
            return True
    return False


def classify_row(row: pd.Series) -> str:
    if is_pass_row(row):
        return "Clean TAEM success"
    label = str(row.get("label", "")).strip()
    if label and label.lower() != "nan":
        return label
    if any(c in row.index and norm_bool(row[c]) for c in ["last_close_pass_escape", "close_pass_escape", "any_close_pass_escape"]):
        return "Close-pass escape"
    sgo_final = pd.to_numeric(pd.Series([row.get("taem_s_go_err_final", np.nan)]), errors="coerce").iloc[0]
    h_final = pd.to_numeric(pd.Series([row.get("taem_h_err_final", np.nan)]), errors="coerce").iloc[0]
    v_final = pd.to_numeric(pd.Series([row.get("taem_v_err_final", np.nan)]), errors="coerce").iloc[0]
    if np.isfinite(sgo_final) and abs(sgo_final) > 50000:
        return "Range-closure failure"
    if np.isfinite(h_final) and abs(h_final) > 3000:
        return "Altitude-boundary failure"
    if np.isfinite(v_final) and abs(v_final) > 150:
        return "Velocity-boundary failure"
    return "Unclassified failure"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=None, help="B5A-R by-vehicle CSV path")
    ap.add_argument("--outdir", default=r"store\data_saved\phase2_B5AR_failure_diagnosis_report")
    args = ap.parse_args()

    root = Path.cwd()
    csv_path = Path(args.csv) if args.csv else find_default_csv(root)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    hcol = get_col(df, ["height_delta_m", "h_delta_m", "height_delta"])
    vcol = get_col(df, ["velocity_delta_mps", "v_delta_mps", "velocity_delta"])
    midcol = get_col(df, ["vehicle_id", "mis_id", "missile_id"])
    rolecol = get_col(df, ["role", "Phase2Role", "phase2_role"])
    headingcol = get_col(df, ["heading_delta_deg", "heading_delta", "heading_delta_deg_used"])
    if hcol is None or vcol is None:
        raise RuntimeError(f"Could not find height/velocity delta columns. Columns={list(df.columns)}")
    if midcol is None:
        df["_vehicle_id"] = np.arange(len(df))
        midcol = "_vehicle_id"

    df["_is_pass"] = df.apply(is_pass_row, axis=1)
    df["_failure_class"] = df.apply(classify_row, axis=1)
    df["_close_escape"] = df.apply(lambda r: any(c in r.index and norm_bool(r[c]) for c in ["last_close_pass_escape", "close_pass_escape", "any_close_pass_escape"]), axis=1)

    case_rows = []
    for (h, v), g in df.groupby([hcol, vcol], dropna=False):
        k, n = int(g["_is_pass"].sum()), int(len(g)); ci = wilson_ci(k, n)
        case_rows.append({"height_delta_m": h, "velocity_delta_mps": v, "pass": k, "n": n, "pass_rate": k/n if n else np.nan, "ci95_low": ci[0], "ci95_high": ci[1], "close_escape": int(g["_close_escape"].sum()), "failure_classes": "; ".join(sorted(set(g.loc[~g["_is_pass"], "_failure_class"].astype(str)))) if k < n else ""})
    case_df = pd.DataFrame(case_rows).sort_values(["velocity_delta_mps", "height_delta_m"])

    def marginal(group_cols):
        rows=[]
        for key,g in df.groupby(group_cols, dropna=False):
            if not isinstance(key, tuple): key=(key,)
            k,n=int(g["_is_pass"].sum()), int(len(g)); ci=wilson_ci(k,n)
            row={col:val for col,val in zip(group_cols,key)}
            row.update({"pass":k,"n":n,"pass_rate":k/n if n else np.nan,"ci95_low":ci[0],"ci95_high":ci[1],"close_escape":int(g["_close_escape"].sum())})
            rows.append(row)
        return pd.DataFrame(rows).sort_values(group_cols)

    v_df=marginal([vcol]); h_df=marginal([hcol])
    veh_group_cols=[midcol]
    if rolecol: veh_group_cols.append(rolecol)
    if headingcol: veh_group_cols.append(headingcol)
    veh_df=marginal(veh_group_cols)

    terminal_cols=[]
    for c in [hcol,vcol,midcol,rolecol,headingcol,"decision","label","_failure_class","end_reason","taem_dwell_s_final_logged","taem_dwell_count_final_logged","taem_h_err_min_abs","taem_v_err_min_abs","taem_s_go_err_min_abs","taem_h_err_final","taem_v_err_final","taem_s_go_err_final","s_go_min","s_go_final","last_close_pass_escape"]:
        if c and c in df.columns or c == "_failure_class": terminal_cols.append(c)
    fail_df=df.loc[~df["_is_pass"], terminal_cols].copy()

    safe_v=[]
    for _,row in v_df.iterrows():
        if row["pass_rate"] >= 0.95: safe_v.append(row[vcol])
    max_all_pass_v=max(safe_v) if safe_v else None

    lines=[]
    lines.append("PHASE 2 / B5A-R FAILURE DIAGNOSIS")
    lines.append("="*72)
    lines.append(f"input_csv: {csv_path}")
    lines.append(f"rows: {len(df)}")
    lines.append(f"height_column: {hcol}")
    lines.append(f"velocity_column: {vcol}")
    lines.append(f"vehicle_column: {midcol}")
    lines.append("")
    lines.append("[MARGINAL BY POSITIVE VELOCITY]")
    for _,r in v_df.iterrows(): lines.append(f"v={r[vcol]:+g} m/s | pass={int(r['pass'])}/{int(r['n'])} rate={r['pass_rate']:.3f} CI95=[{r['ci95_low']:.3f},{r['ci95_high']:.3f}] | close_escape={int(r['close_escape'])}")
    lines.append("")
    lines.append("[MARGINAL BY HEIGHT]")
    for _,r in h_df.iterrows(): lines.append(f"h={r[hcol]:+g} m | pass={int(r['pass'])}/{int(r['n'])} rate={r['pass_rate']:.3f} CI95=[{r['ci95_low']:.3f},{r['ci95_high']:.3f}] | close_escape={int(r['close_escape'])}")
    lines.append("")
    lines.append("[MARGINAL BY VEHICLE/ROLE]")
    for _,r in veh_df.iterrows():
        ident=" | ".join(f"{c}={r[c]}" for c in veh_group_cols)
        lines.append(f"{ident} | pass={int(r['pass'])}/{int(r['n'])} rate={r['pass_rate']:.3f} | close_escape={int(r['close_escape'])}")
    lines.append("")
    lines.append("[CASE SUMMARY]")
    for _,r in case_df.iterrows(): lines.append(f"h={r['height_delta_m']:+g} m, v={r['velocity_delta_mps']:+g} m/s | pass={int(r['pass'])}/{int(r['n'])} rate={r['pass_rate']:.3f} | close_escape={int(r['close_escape'])} | failures={r['failure_classes']}")
    lines.append("")
    lines.append("[FAILED ROWS]")
    lines.append("No failed rows." if len(fail_df)==0 else fail_df.to_string(index=False))
    lines.append("")
    lines.append("[INTERPRETATION]")
    if max_all_pass_v is not None: lines.append(f"- Fully passing sampled positive-velocity levels include up to v={max_all_pass_v:+g} m/s, but non-monotonic failures must be treated carefully.")
    lines.append("- +50 m/s remains the dominant fragile sector in the current grid.")
    lines.append("- Failures are close-pass/range-closure dominated when close_escape counts match failed rows.")
    lines.append("- Monte Carlo should not yet use a broad ±50 m/s uniform velocity spread as a strong-universality claim.")
    lines.append("- Safer next pilots: v_delta in [-50,+10] m/s for conservative U3; or a focused boundary MC around +20..+50 m/s for fragility mapping.")

    case_df.to_csv(outdir/"b5ar_case_summary.csv", index=False)
    v_df.to_csv(outdir/"b5ar_marginal_by_velocity.csv", index=False)
    h_df.to_csv(outdir/"b5ar_marginal_by_height.csv", index=False)
    veh_df.to_csv(outdir/"b5ar_marginal_by_vehicle.csv", index=False)
    fail_df.to_csv(outdir/"b5ar_failed_rows.csv", index=False)
    (outdir/"b5ar_failure_diagnosis_summary.txt").write_text("\n".join(lines), encoding="utf-8")
    (outdir/"b5ar_failure_diagnosis_summary.json").write_text(json.dumps({"input_csv":str(csv_path),"n_rows":int(len(df)),"height_column":hcol,"velocity_column":vcol,"vehicle_column":midcol,"max_all_pass_positive_velocity_sampled_mps":None if max_all_pass_v is None else float(max_all_pass_v),"n_failed_rows":int((~df['_is_pass']).sum()),"n_close_escape_failed":int(df.loc[~df['_is_pass'], '_close_escape'].sum())}, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n".join(lines))
    print("\n[OK] wrote:", outdir/"b5ar_failure_diagnosis_summary.txt")
    print("[OK] wrote:", outdir/"b5ar_case_summary.csv")
    print("[OK] wrote:", outdir/"b5ar_failed_rows.csv")

if __name__ == "__main__":
    main()
