# -*- coding: utf-8 -*-
"""
Phase 2 / B5C-F — Local-envelope Monte Carlo failure diagnosis.

Reads B5C independent local-envelope validation outputs and produces a concise
failure-mode diagnosis for the residual close-pass/range-closure failures.
No new simulation is run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from math import sqrt

import numpy as np
import pandas as pd


def wilson_ci(k: int, n: int, z: float = 1.96):
    if n <= 0:
        return (float('nan'), float('nan'))
    p = k / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    margin = z * sqrt((p*(1-p) + z*z/(4*n)) / n) / denom
    return (max(0.0, center-margin), min(1.0, center+margin))


def find_col(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def is_pass(x):
    s = str(x).strip().upper()
    return s in {"PASS", "PASS_STRICT", "TRUE", "1", "SUCCESS"} or s.startswith("PASS")


def truthy(x):
    if pd.isna(x):
        return False
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y", "close_pass_escape"}


def classify(row, colmap):
    label_col = colmap.get('label')
    end_col = colmap.get('end_reason')
    close_col = colmap.get('close')
    h_final = colmap.get('h_final_err')
    v_final = colmap.get('v_final_err')
    sgo_final = colmap.get('sgo_final_err')
    sgo_min_abs = colmap.get('sgo_min_abs')

    label = str(row.get(label_col, '') if label_col else '')
    end_reason = str(row.get(end_col, '') if end_col else '')
    close = truthy(row.get(close_col, False)) if close_col else False

    if 'range' in label.lower():
        return 'Close-pass escape / range-closure failure'
    if close or 'close-pass' in label.lower() or 'escape' in end_reason.lower():
        return 'Close-pass escape'

    try:
        hv = abs(float(row.get(h_final, np.nan))) if h_final else np.nan
        vv = abs(float(row.get(v_final, np.nan))) if v_final else np.nan
        sf = abs(float(row.get(sgo_final, np.nan))) if sgo_final else np.nan
        sm = abs(float(row.get(sgo_min_abs, np.nan))) if sgo_min_abs else np.nan
    except Exception:
        hv = vv = sf = sm = np.nan
    if np.isfinite(sf) and sf > 100000:
        return 'Range-closure failure'
    if np.isfinite(vv) and vv > 150:
        return 'Energy/speed closure failure'
    if np.isfinite(hv) and hv > 3000:
        return 'Altitude closure failure'
    if np.isfinite(sm) and sm < 5000:
        return 'Near TAEM but no dwell'
    return 'Other/unknown failure'


def rate_line(name, k, n, close=None):
    lo, hi = wilson_ci(k, n)
    if close is None:
        return f"{name} | pass={k}/{n} rate={k/n if n else float('nan'):.3f} CI95=[{lo:.3f},{hi:.3f}]"
    return f"{name} | pass={k}/{n} rate={k/n if n else float('nan'):.3f} CI95=[{lo:.3f},{hi:.3f}] close_escape={close}"


def bin_velocity(v):
    # specific to B5C range [-20,+10]
    if pd.isna(v): return 'NA'
    if v <= -15: return '[-20,-15]'
    if v <= -10: return '(-15,-10]'
    if v <= -5: return '(-10,-5]'
    if v <= 0: return '(-5,0]'
    if v <= 5: return '(0,+5]'
    return '(+5,+10]'


def bin_height(h):
    if pd.isna(h): return 'NA'
    if h <= 100: return '[0,+100]'
    if h <= 250: return '(+100,+250]'
    if h <= 400: return '(+250,+400]'
    return '(+400,+500]'


def summarize_group(df, group_col, pass_col, close_col):
    rows=[]
    for key, g in df.groupby(group_col, dropna=False):
        n=len(g); k=int(g[pass_col].sum())
        close=int(g[close_col].sum()) if close_col in g.columns else 0
        lo,hi=wilson_ci(k,n)
        rows.append({group_col:key,'n':n,'pass':k,'pass_rate':k/n if n else np.nan,'ci95_low':lo,'ci95_high':hi,'close_escape':close})
    return pd.DataFrame(rows).sort_values(['pass_rate','n'], ascending=[True,False])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--vehicle-csv', default=r'store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_vehicle_all.csv')
    ap.add_argument('--case-csv', default=r'store\data_saved\phase2_B5C_local_envelope_validation_report\phase2_B5C_by_case_all.csv')
    ap.add_argument('--outdir', default=r'store\data_saved\phase2_B5C_failure_diagnosis_report')
    args = ap.parse_args()

    vehicle_csv = Path(args.vehicle_csv)
    case_csv = Path(args.case_csv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not vehicle_csv.exists():
        raise FileNotFoundError(vehicle_csv)
    df = pd.read_csv(vehicle_csv)
    casedf = pd.read_csv(case_csv) if case_csv.exists() else pd.DataFrame()

    colmap = {
        'case': find_col(df, ['mc_case_id','case_id','case','b5b_case_id','b5c_case_id']),
        'h': find_col(df, ['height_delta_m','h_delta_m','height_delta']),
        'v': find_col(df, ['velocity_delta_mps','v_delta_mps','velocity_delta']),
        'vehicle': find_col(df, ['mis_id','vehicle_id','target_mis_id']),
        'role': find_col(df, ['phase2_role','role','Phase2Role']),
        'decision': find_col(df, ['decision','b1_vehicle_decision','vehicle_decision']),
        'label': find_col(df, ['label','failure_label','classification']),
        'end_reason': find_col(df, ['end_reason_last','end_reason']),
        'close': find_col(df, ['last_close_pass_escape','close_pass_escape','any_close_pass_escape']),
        'sgo_min_abs': find_col(df, ['taem_s_go_err_min_abs','taem_sgo_err_min_abs']),
        'sgo_final_err': find_col(df, ['taem_s_go_err_final','taem_sgo_err_final']),
        'h_final_err': find_col(df, ['taem_h_err_final']),
        'v_final_err': find_col(df, ['taem_v_err_final']),
        'sgo_min_state': find_col(df, ['s_go_min']),
        'sgo_final_state': find_col(df, ['s_go_final']),
        'dwell_s': find_col(df, ['taem_dwell_s_final_logged','taem_dwell_s']),
        'dwell_count': find_col(df, ['taem_dwell_count_final_logged','taem_dwell_count']),
    }

    dec = colmap['decision']
    if not dec:
        raise RuntimeError('decision column not found')
    df['_pass'] = df[dec].map(is_pass)
    close_col = colmap['close']
    df['_close_escape'] = df[close_col].map(truthy) if close_col else False
    df['_failure_class'] = df.apply(lambda r: 'Clean TAEM success' if r['_pass'] else classify(r, colmap), axis=1)

    if colmap['v']:
        df['_v_bin'] = pd.to_numeric(df[colmap['v']], errors='coerce').map(bin_velocity)
    else:
        df['_v_bin'] = 'NA'
    if colmap['h']:
        df['_h_bin'] = pd.to_numeric(df[colmap['h']], errors='coerce').map(bin_height)
    else:
        df['_h_bin'] = 'NA'

    n=len(df); k=int(df['_pass'].sum())
    failure = df[~df['_pass']].copy()
    close_fail = int(failure['_close_escape'].sum()) if len(failure) else 0
    case_col = colmap['case']
    if case_col:
        case_group = df.groupby(case_col)['_pass'].all().reset_index(name='_case_pass')
        case_n=len(case_group); case_k=int(case_group['_case_pass'].sum())
    else:
        case_n=case_k=0

    vbin = summarize_group(df, '_v_bin', '_pass', '_close_escape')
    hbin = summarize_group(df, '_h_bin', '_pass', '_close_escape')
    veh = summarize_group(df, colmap['vehicle'], '_pass', '_close_escape') if colmap['vehicle'] else pd.DataFrame()
    role = summarize_group(df, colmap['role'], '_pass', '_close_escape') if colmap['role'] else pd.DataFrame()
    mode_counts = df['_failure_class'].value_counts(dropna=False).rename_axis('failure_class').reset_index(name='n')
    mode_counts['rate'] = mode_counts['n']/len(df)

    # case compact summary
    if case_col:
        agg = df.groupby(case_col).agg(
            n_vehicle=('_pass','size'),
            vehicle_pass=('_pass','sum'),
            close_escape=('_close_escape','sum'),
        ).reset_index()
        if colmap['h']:
            agg['height_delta_m'] = df.groupby(case_col)[colmap['h']].first().values
        if colmap['v']:
            agg['velocity_delta_mps'] = df.groupby(case_col)[colmap['v']].first().values
        agg['case_pass'] = agg['vehicle_pass'] == agg['n_vehicle']
        case_summary = agg.sort_values(['case_pass','vehicle_pass'])
    else:
        case_summary = pd.DataFrame()

    # Save csv outputs
    enriched = df.copy()
    enriched.to_csv(outdir/'b5c_enriched_by_vehicle.csv', index=False)
    failure.to_csv(outdir/'b5c_failure_rows.csv', index=False)
    vbin.to_csv(outdir/'b5c_marginal_by_velocity_bin.csv', index=False)
    hbin.to_csv(outdir/'b5c_marginal_by_height_bin.csv', index=False)
    if not veh.empty: veh.to_csv(outdir/'b5c_marginal_by_vehicle.csv', index=False)
    if not role.empty: role.to_csv(outdir/'b5c_marginal_by_role.csv', index=False)
    mode_counts.to_csv(outdir/'b5c_failure_mode_counts.csv', index=False)
    if not case_summary.empty: case_summary.to_csv(outdir/'b5c_case_failure_summary.csv', index=False)

    # Decision/recommendation
    case_rate = case_k/case_n if case_n else np.nan
    vehicle_rate = k/n if n else np.nan
    if case_rate >= 0.8 and vehicle_rate >= 0.85:
        recommendation = 'LOCAL_ENVELOPE_SUPPORTED_BUT_NOT_U4'
    elif case_rate >= 0.6:
        recommendation = 'LOCAL_ENVELOPE_PARTIAL_SUPPORT_RANGE_CLOSURE_RECOVERY_RECOMMENDED'
    else:
        recommendation = 'LOCAL_ENVELOPE_FRAGILE_RANGE_CLOSURE_RECOVERY_REQUIRED'

    lines=[]
    lines.append('PHASE 2 / B5C-F — LOCAL-ENVELOPE FAILURE DIAGNOSIS')
    lines.append('='*72)
    lines.append(f'vehicle_csv        : {vehicle_csv}')
    lines.append(f'case_csv           : {case_csv}')
    lines.append(f'rows               : {n}')
    lines.append(f'decision           : {recommendation}')
    vlo,vhi=wilson_ci(k,n)
    lines.append(f'vehicle_pass_rate  : {k}/{n} = {vehicle_rate:.6f} CI95=[{vlo:.3f},{vhi:.3f}]')
    if case_n:
        clo,chi=wilson_ci(case_k,case_n)
        lines.append(f'case_pass_rate     : {case_k}/{case_n} = {case_rate:.6f} CI95=[{clo:.3f},{chi:.3f}]')
    lines.append(f'failure_rows       : {len(failure)}')
    lines.append(f'close_escape_failures: {close_fail}/{len(failure)} = {close_fail/len(failure) if len(failure) else float("nan"):.6f}')
    lines.append('')
    lines.append('[COLUMN MAP]')
    for key,val in colmap.items():
        lines.append(f'  {key:15s}: {val}')
    lines.append('')
    lines.append('[MARGINAL BY VELOCITY BIN]')
    for _,r in vbin.iterrows():
        lines.append(rate_line(str(r['_v_bin']), int(r['pass']), int(r['n']), int(r['close_escape'])))
    lines.append('')
    lines.append('[MARGINAL BY HEIGHT BIN]')
    for _,r in hbin.iterrows():
        lines.append(rate_line(str(r['_h_bin']), int(r['pass']), int(r['n']), int(r['close_escape'])))
    if not veh.empty:
        lines.append('')
        lines.append('[MARGINAL BY VEHICLE]')
        for _,r in veh.iterrows():
            lines.append(rate_line(f"vehicle={r[colmap['vehicle']]}", int(r['pass']), int(r['n']), int(r['close_escape'])))
    if not role.empty:
        lines.append('')
        lines.append('[MARGINAL BY ROLE]')
        for _,r in role.iterrows():
            lines.append(rate_line(f"role={r[colmap['role']]}", int(r['pass']), int(r['n']), int(r['close_escape'])))
    lines.append('')
    lines.append('[FAILURE MODE COUNTS]')
    for _,r in mode_counts.iterrows():
        lines.append(f"{r['failure_class']} | n={int(r['n'])} rate={r['rate']:.3f}")
    if not case_summary.empty:
        lines.append('')
        lines.append('[WORST CASES]')
        for _,r in case_summary.head(15).iterrows():
            hstr = f"h={r.get('height_delta_m', np.nan):+.3f} m" if 'height_delta_m' in r else ''
            vstr = f"v={r.get('velocity_delta_mps', np.nan):+.3f} m/s" if 'velocity_delta_mps' in r else ''
            lines.append(f"{r[case_col]} | {hstr} | {vstr} | pass={int(r['vehicle_pass'])}/{int(r['n_vehicle'])} | close_escape={int(r['close_escape'])}")
    lines.append('')
    lines.append('[FAILED ROWS — COMPACT]')
    compact_cols = [c for c in [case_col, colmap['h'], colmap['v'], colmap['vehicle'], colmap['role'], dec, colmap['label'], colmap['end_reason'], close_col, colmap['dwell_s'], colmap['dwell_count'], colmap['sgo_min_abs'], colmap['h_final_err'], colmap['v_final_err'], colmap['sgo_final_err'], colmap['sgo_min_state'], colmap['sgo_final_state'], '_failure_class'] if c]
    if len(failure):
        lines.append(failure[compact_cols].to_string(index=False))
    else:
        lines.append('No failed rows.')
    lines.append('')
    lines.append('[INTERPRETATION]')
    lines.append('- B5C is an independent validation of a narrow local envelope, not a U4 universality test.')
    lines.append('- If failures are close-pass dominated, the next technical barrier remains range-closure robustness.')
    lines.append('- Use this diagnosis to decide whether the local envelope is publishable as U3-local support or whether a range-closure recovery patch is required first.')
    lines.append('')
    lines.append('[GENERATED FILES]')
    for name in ['b5c_enriched_by_vehicle.csv','b5c_failure_rows.csv','b5c_case_failure_summary.csv','b5c_marginal_by_velocity_bin.csv','b5c_marginal_by_height_bin.csv','b5c_marginal_by_vehicle.csv','b5c_marginal_by_role.csv','b5c_failure_mode_counts.csv','b5c_failure_diagnosis_summary.json']:
        lines.append(f'  - {outdir/name}')

    summary = '\n'.join(lines)
    (outdir/'b5c_failure_diagnosis_summary.txt').write_text(summary, encoding='utf-8')
    json.dump({
        'vehicle_csv': str(vehicle_csv),
        'case_csv': str(case_csv),
        'decision': recommendation,
        'vehicle_pass': int(k),
        'vehicle_n': int(n),
        'vehicle_pass_rate': float(vehicle_rate),
        'case_pass': int(case_k),
        'case_n': int(case_n),
        'case_pass_rate': float(case_rate) if case_n else None,
        'failure_rows': int(len(failure)),
        'close_escape_failures': int(close_fail),
        'colmap': colmap,
    }, open(outdir/'b5c_failure_diagnosis_summary.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print(summary)
    print('\n[OK] wrote:', outdir/'b5c_failure_diagnosis_summary.txt')

if __name__ == '__main__':
    main()
