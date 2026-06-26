#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser(description='Generate TAEM ML sweep plan around the reference branch.')
    ap.add_argument('--n-runs', type=int, default=60)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    rows = []
    for run_idx in range(args.n_runs):
        row = {
            'run_name': f'run_{run_idx:04d}',
            'mis0_psi_bias_deg': rng.uniform(-13.5, -10.5),
            'mis0_psi_bias_sgo_on_m': rng.uniform(1.4e6, 2.0e6),
            'mis0_psi_bias_sgo_off_m': rng.uniform(2.0e5, 4.5e5),
            'mis0_beg_sgo_trigger_m': rng.uniform(6.5e5, 9.5e5),
            'mis1_terminal_alpha_boost_deg': rng.uniform(0.5, 2.5),
            'mis1_terminal_alpha_boost_sgo_on_m': rng.uniform(2.2e5, 5.5e5),
            'mis1_terminal_alpha_boost_sgo_full_m': rng.uniform(0.8e5, 1.6e5),
            'mis1_beg_sgo_trigger_m': rng.uniform(6.5e5, 1.0e6),
            'mis2_psi_bias_deg': rng.uniform(4.0, 10.0),
            'mis2_psi_bias_sgo_on_m': rng.uniform(1.4e6, 2.2e6),
            'mis2_psi_bias_sgo_off_m': rng.uniform(2.0e5, 4.5e5),
            'mis2_beg_sgo_trigger_m': rng.uniform(8.5e5, 1.4e6),
            'mis2_steady_sigma_cap_deg': rng.uniform(32.0, 42.0),
            'mis2_beg_sigma_cap_deg': rng.uniform(16.0, 24.0),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f'[OK] Wrote sweep plan: {args.out}')
    print(df.head())


if __name__ == '__main__':
    main()
