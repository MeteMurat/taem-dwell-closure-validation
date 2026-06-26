# Next-step package: stricter grouped training + improved dataset builder

Files included:
- `build_taem_ml_dataset_v2.py`: improved dataset builder with explicit summary/TAEM merges and reduced NaN contamination.
- `train_taem_lb_grouped_strict.py`: grouped-CV + grouped-holdout trainer with ablation (`config_only` vs `config_plus_summary`) and permutation importance.
- `q1_updated_abstract_and_contributions.md`: updated abstract draft and contribution set aligned with the current ML results.

## Recommended order

1. Build improved dataset:
```powershell
python .\taem_ml_pipeline\build_taem_ml_dataset_v2.py --runs-root .\taem_ml_runs\runs_60 --out .\taem_ml_runs\taem_ml_dataset_60_v2.csv
```

2. Train stricter grouped models:
```powershell
python .\taem_ml_pipeline\train_taem_lb_grouped_strict.py --dataset .\taem_ml_runs\taem_ml_dataset_60_v2.csv --outdir .\taem_ml_runs\ml_grouped_strict_60
```

3. Inspect outputs:
- `grouped_cv_results.csv`
- `grouped_holdout_results.csv`
- `feature_importance_permutation.csv`
- `training_report.md`
- `training_summary_strict.json`

## Why this matters

The earlier trainer already showed strong pilot performance, but grouped CV and grouped holdout are more defensible for publication because all vehicle rows from the same run remain together during evaluation.
