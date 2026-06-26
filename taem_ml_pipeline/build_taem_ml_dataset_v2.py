#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd


def _safe_read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def _load_params(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _extract_vehicle_config(params: dict, vid: int) -> dict:
    out = {'vehicle_id': int(vid), 'is_mis0': int(vid == 0), 'is_mis1': int(vid == 1), 'is_mis2': int(vid == 2)}
    # keep global configuration so cross-vehicle interactions remain available
    for k, v in params.items():
        if isinstance(v, (int, float, bool, str)):
            out[f'cfg_{k}'] = v
    # explicit per-vehicle convenience aliases used by stricter trainer
    prefixes = {0: 'mis0_', 1: 'mis1_', 2: 'mis2_'}
    pfx = prefixes.get(int(vid), f'mis{vid}_')
    for k, v in params.items():
        if str(k).startswith(pfx):
            out[f'own_{str(k)[len(pfx):]}'] = v
    return out


def main():
    ap = argparse.ArgumentParser(description='Build improved TAEM ML dataset from sweep run folders.')
    ap.add_argument('--runs-root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()

    rows = []
    run_dirs = sorted([p for p in args.runs_root.iterdir() if p.is_dir()])
    for run_dir in run_dirs:
        params_path = run_dir / 'run_params.json'
        q1_path = run_dir / 'q1_vehicle_metrics.csv'
        failure_path = run_dir / 'q1_failure_modes.csv'
        summary_path = run_dir / 'summary_by_vehicle.csv'
        taem_path = run_dir / 'taem_compare_by_vehicle.csv'
        if not all(p.exists() for p in [params_path, q1_path, failure_path, summary_path, taem_path]):
            continue

        params = _load_params(params_path)
        q1 = _safe_read_csv(q1_path).rename(columns={
            't_end': 'q1_t_end',
            'q_max': 'q1_q_max',
            'end_reason': 'q1_end_reason',
            'guide_phase_last': 'q1_guide_phase_last',
        })
        failure = _safe_read_csv(failure_path).rename(columns={
            'end_reason': 'failure_end_reason',
            'guide_phase_last': 'failure_guide_phase_last',
        })
        summary = _safe_read_csv(summary_path).rename(columns={
            'mis_id': 'vehicle_id',
            't_end': 'summary_t_end',
            'q_max': 'summary_q_max',
            's_go_min': 'summary_s_go_min',
            'h_min_m': 'summary_h_min_m',
            'h_end_m': 'summary_h_end_m',
            'v_min': 'summary_v_min',
            'v_end': 'summary_v_end',
            'L12D_min': 'summary_L12D_min',
            'taem_h_err_end': 'summary_taem_h_err_end',
            'taem_v_err_end': 'summary_taem_v_err_end',
            'taem_s_go_err_end': 'summary_taem_s_go_err_end',
            'taem_dwell_count_end': 'summary_taem_dwell_count_end',
            'taem_dwell_count_max': 'summary_taem_dwell_count_max',
            'taem_t_local': 'summary_taem_t_local',
            'taem_t_global': 'summary_taem_t_global',
            'lon_end_deg': 'summary_lon_end_deg',
            'lat_end_deg': 'summary_lat_end_deg',
        })
        taem = _safe_read_csv(taem_path).rename(columns={
            'run_id': 'taem_run_id',
            'csv': 'taem_csv',
            'time_col': 'taem_time_col',
            'detect_mode': 'taem_detect_mode',
            'detect_checks': 'taem_detect_checks',
            'dwell_min_s': 'taem_dwell_min_s',
            't_start': 'taem_t_start',
            't_end': 'taem_t_end',
            'end_reason_last': 'taem_end_reason_last',
        })

        merged = q1.merge(failure[['vehicle_id', 'failure_mode']], on='vehicle_id', how='left') \
                   .merge(summary, on='vehicle_id', how='left') \
                   .merge(taem, on='vehicle_id', how='left')

        for _, row in merged.iterrows():
            vid = int(row['vehicle_id'])
            rec = {
                'run_name': params.get('run_name', run_dir.name),
                'group_run_name': params.get('run_name', run_dir.name),
            }
            rec.update(_extract_vehicle_config(params, vid))

            # canonical target / labels
            rec['taem_lb_score'] = row.get('taem_lb_score', np.nan)
            rec['taem_end_score'] = row.get('taem_end_score', np.nan)
            rec['taem_reached'] = bool(row.get('taem_reached', False))
            rec['failure_mode'] = row.get('failure_mode', '')
            rec['end_reason'] = row.get('q1_end_reason', row.get('taem_end_reason_last', ''))
            rec['guide_phase_last'] = row.get('q1_guide_phase_last', row.get('guide_phase_last', ''))

            # q1 metrics retained for analysis but not for summary-feature training due leakage risk
            for col in [
                's_go_last_m', 'lon_end_deg', 'lat_end_deg',
                'h_err_minabs_m', 'v_err_minabs_mps', 's_go_err_minabs_m', 'psi_err_minabs_rad',
                'q1_t_end', 'q1_q_max', 'dwell_max_s'
            ]:
                rec[col] = row.get(col, np.nan)

            # summary features (run-end / low-cost descriptors)
            for col in [
                'summary_t_end', 'summary_q_max', 'summary_s_go_min', 'summary_h_min_m', 'summary_h_end_m',
                'summary_v_min', 'summary_v_end', 'summary_L12D_min',
                'summary_taem_h_err_end', 'summary_taem_v_err_end', 'summary_taem_s_go_err_end',
                'summary_taem_dwell_count_end', 'summary_taem_dwell_count_max',
                'summary_taem_t_local', 'summary_taem_t_global',
                'summary_lon_end_deg', 'summary_lat_end_deg'
            ]:
                rec[col] = row.get(col, np.nan)

            # taem compare features (end-state descriptors)
            for col in [
                'taem_t_end', 'taem_h_err_last', 'taem_h_err_minabs', 'taem_v_err_last', 'taem_v_err_minabs',
                'taem_s_go_err_last', 'taem_s_go_err_minabs', 'taem_psi_err_last', 'taem_psi_err_minabs',
                'taem_dwell_s', 'taem_dwell_max_s', 'height_last', 'velocity_last', 's_go_last',
                'heading_angle_last', 'touchdown_any', 'end_guide_any'
            ]:
                rec[col] = row.get(col, np.nan)

            rows.append(rec)

    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit('No valid run folders found; dataset is empty.')

    # normalize booleans
    for c in df.columns:
        if df[c].dtype == bool:
            df[c] = df[c].astype(int)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f'[OK] Wrote improved ML dataset: {args.out}')
    print(df.head())
    print(f'[INFO] n_rows={len(df)} n_runs={df["run_name"].nunique()} n_cols={len(df.columns)}')


if __name__ == '__main__':
    main()
