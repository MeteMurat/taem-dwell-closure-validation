#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, subprocess, sys, textwrap
from pathlib import Path
import pandas as pd

THIS_DIR = Path(__file__).resolve().parent


def first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.exists():
            return p
    return None


def resolve_reference_paths(project_root: Path) -> tuple[Path, Path, Path]:
    guidance_ref = first_existing([
        THIS_DIR / 'reference_best' / 'multiMissileGuideInstance_reference_best.py',
        project_root / 'guidance' / 'multiMissileGuideInstance.py',
        Path('/mnt/data/multiMissileGuideInstance_reference_best.py'),
    ])
    multiset_ref = first_existing([
        THIS_DIR / 'reference_best' / 'multiset_reference_best.py',
        project_root / 'multiset.py',
        Path('/mnt/data/multiset_reference_best.py'),
    ])
    q1_script = first_existing([
        project_root / 'q1_terminal_analysis_report.py',
        Path('/mnt/data/q1_terminal_analysis_report.py'),
    ])
    missing = []
    if guidance_ref is None:
        missing.append('guidance reference file')
    if multiset_ref is None:
        missing.append('multiset reference file')
    if q1_script is None:
        missing.append('q1_terminal_analysis_report.py')
    if missing:
        raise FileNotFoundError('Could not resolve: ' + ', '.join(missing))
    return guidance_ref, multiset_ref, q1_script


def build_path_specs(row: dict) -> str:
    vals = {k: float(v) if k != 'run_name' else v for k, v in row.items()}
    return textwrap.dedent("""
    _PATH_SPECS = [
        dict(
            name="route_left",
            psi_bias_deg={mis0_psi_bias_deg:.6f},
            psi_bias_sgo_on_m={mis0_psi_bias_sgo_on_m:.6f},
            psi_bias_sgo_off_m={mis0_psi_bias_sgo_off_m:.6f},
            psi_bias_alt_on_m=50000.0,
            psi_bias_alt_off_m=25000.0,
            sgn_ini_override=-1,
            beg_sgo_trigger_m={mis0_beg_sgo_trigger_m:.6f},
            terminal_alpha_boost_enable=False,
        ),
        dict(
            name="route_mid",
            psi_bias_deg=0.0,
            psi_bias_sgo_on_m=1.8e6,
            psi_bias_sgo_off_m=3.5e5,
            psi_bias_alt_on_m=50000.0,
            psi_bias_alt_off_m=25000.0,
            sgn_ini_override=None,
            beg_sgo_trigger_m={mis1_beg_sgo_trigger_m:.6f},
            terminal_alpha_boost_enable=True,
            terminal_alpha_boost_deg={mis1_terminal_alpha_boost_deg:.6f},
            terminal_alpha_boost_sgo_on_m={mis1_terminal_alpha_boost_sgo_on_m:.6f},
            terminal_alpha_boost_sgo_full_m={mis1_terminal_alpha_boost_sgo_full_m:.6f},
            terminal_alpha_boost_h_on_m=5.0e4,
            terminal_alpha_boost_h_full_m=3.0e4,
        ),
        dict(
            name="route_right",
            psi_bias_deg={mis2_psi_bias_deg:.6f},
            psi_bias_sgo_on_m={mis2_psi_bias_sgo_on_m:.6f},
            psi_bias_sgo_off_m={mis2_psi_bias_sgo_off_m:.6f},
            psi_bias_alt_on_m=50000.0,
            psi_bias_alt_off_m=25000.0,
            sgn_ini_override=+1,
            beg_sgo_trigger_m={mis2_beg_sgo_trigger_m:.6f},
            steady_sigma_cap_rad=np.deg2rad({mis2_steady_sigma_cap_deg:.6f}),
            beg_sigma_cap_rad=np.deg2rad({mis2_beg_sigma_cap_deg:.6f}),
            terminal_alpha_boost_enable=False,
        ),
    ]
    """).strip('\n').format(**vals)


def render_multiset_from_plan(reference_text: str, row: dict) -> str:
    replacement = build_path_specs(row)
    lines = reference_text.splitlines()
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip().startswith('_PATH_SPECS'):
            start = i
            break
    if start is None:
        raise RuntimeError('Could not find _PATH_SPECS start in reference multiset.')
    for j in range(start + 1, len(lines)):
        if lines[j].strip().startswith('# Simulation case parameters'):
            end = j
            break
    if end is None:
        raise RuntimeError('Could not find end marker (# Simulation case parameters) in reference multiset.')
    new_lines = lines[:start] + replacement.splitlines() + [''] + lines[end:]
    return '\n'.join(new_lines) + '\n'


def run_cmd(cmd, cwd: Path, logfh):
    logfh.write('$ ' + ' '.join(str(x) for x in cmd) + '\n')
    logfh.flush()
    proc = subprocess.run(cmd, cwd=str(cwd), stdout=logfh, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f'Command failed with exit code {proc.returncode}: {cmd}')


def safe_copy(src: Path, dst: Path):
    if src.resolve() == dst.resolve():
        return
    shutil.copyfile(src, dst)


def main():
    ap = argparse.ArgumentParser(description='Run multi-run TAEM sweep on the reference branch.')
    ap.add_argument('--project-root', type=Path, required=True)
    ap.add_argument('--plan', type=Path, required=True)
    ap.add_argument('--outdir', type=Path, required=True)
    ap.add_argument('--limit-runs', type=int, default=None)
    args = ap.parse_args()

    proj = args.project_root.resolve()
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    plan_df = pd.read_csv(args.plan)
    if args.limit_runs is not None:
        plan_df = plan_df.head(args.limit_runs)

    guidance_ref, multiset_ref, q1_script = resolve_reference_paths(proj)

    guidance_dst = proj / 'guidance' / 'multiMissileGuideInstance.py'
    multiset_dst = proj / 'multiset.py'

    orig_guidance = guidance_dst.read_text(encoding='utf-8', errors='ignore')
    orig_multiset = multiset_dst.read_text(encoding='utf-8', errors='ignore')
    ref_multiset_text = multiset_ref.read_text(encoding='utf-8', errors='ignore')

    try:
        safe_copy(guidance_ref, guidance_dst)
        for _, row in plan_df.iterrows():
            rowd = row.to_dict()
            run_name = str(rowd['run_name'])
            run_dir = outdir / run_name
            run_dir.mkdir(parents=True, exist_ok=True)
            rendered = render_multiset_from_plan(ref_multiset_text, rowd)
            multiset_dst.write_text(rendered, encoding='utf-8')
            (run_dir / 'run_params.json').write_text(json.dumps(rowd, indent=2), encoding='utf-8')

            with (run_dir / 'run.log').open('w', encoding='utf-8') as logfh:
                run_cmd([sys.executable, 'multi_main.py'], proj, logfh)
                run_cmd([sys.executable, 'plot_csv_report.py', '--input', 'store/data_saved/multiSimulation_case.csv', '--outdir', 'store/data_saved/plots_multi', '--idcol', 'mis_id'], proj, logfh)
                run_cmd([sys.executable, 'taem_compare_runs.py', '--inputs', 'store/data_saved/multiSimulation_case.csv', '--outdir', 'store/data_saved/taem_compare', '--idcol', 'mis_id'], proj, logfh)
                run_cmd([
                    sys.executable, str(q1_script),
                    '--summary', 'store/data_saved/plots_multi/summary_by_vehicle.csv',
                    '--vehicle', 'store/data_saved/taem_compare/taem_compare_by_vehicle.csv',
                    '--run', 'store/data_saved/taem_compare/taem_compare_by_run.csv',
                    '--outdir', 'q1_analysis',
                ], proj, logfh)

            artifacts = [
                proj / 'store' / 'data_saved' / 'multiSimulation_case.csv',
                proj / 'store' / 'data_saved' / 'plots_multi' / 'timeseries_plots.pdf',
                proj / 'store' / 'data_saved' / 'plots_multi' / 'summary_by_vehicle.csv',
                proj / 'store' / 'data_saved' / 'taem_compare' / 'taem_compare_by_vehicle.csv',
                proj / 'store' / 'data_saved' / 'taem_compare' / 'taem_compare_by_run.csv',
                proj / 'q1_analysis' / 'q1_vehicle_metrics.csv',
                proj / 'q1_analysis' / 'q1_failure_modes.csv',
                proj / 'q1_analysis' / 'q1_run_summary.csv',
                proj / 'q1_analysis' / 'q1_report.md',
            ]
            for src in artifacts:
                if src.exists():
                    shutil.copy2(src, run_dir / src.name)
            print(f'[OK] Completed {run_name}')
    finally:
        guidance_dst.write_text(orig_guidance, encoding='utf-8')
        multiset_dst.write_text(orig_multiset, encoding='utf-8')
        print('[INFO] Original project files restored.')


if __name__ == '__main__':
    main()
