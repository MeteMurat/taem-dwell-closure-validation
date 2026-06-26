#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, KFold, cross_validate
from sklearn.metrics import make_scorer, mean_absolute_error, mean_squared_error, r2_score
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler
import joblib

TARGET = 'taem_lb_score'
NON_FEATURES = {
    'run_name', 'taem_lb_score', 'taem_end_score', 'taem_reached', 's_go_last_m',
    'failure_mode', 'end_reason', 'guide_phase_last'
}


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def main():
    ap = argparse.ArgumentParser(description='Train baseline model for taem_lb_score.')
    ap.add_argument('--dataset', type=Path, required=True)
    ap.add_argument('--outdir', type=Path, required=True)
    ap.add_argument('--feature-set', choices=['config_only', 'config_plus_summary'], default='config_only')
    args = ap.parse_args()

    df = pd.read_csv(args.dataset)
    y_series = pd.to_numeric(df[TARGET], errors='coerce')
    df = df[np.isfinite(y_series)].copy()
    if df.empty:
        raise SystemExit('No valid rows with finite taem_lb_score found.')

    feature_cols = [c for c in df.columns if c not in NON_FEATURES]
    if args.feature_set == 'config_only':
        feature_cols = [c for c in feature_cols if c.startswith('mis') or c.startswith('is_mis')]

    X = df[feature_cols].copy()
    y = pd.to_numeric(df[TARGET], errors='coerce').astype(float).to_numpy()
    groups = df['run_name'].astype(str).to_numpy() if 'run_name' in df.columns else None

    numeric_cols = list(X.columns)
    pre = ColumnTransformer([
        ('num', Pipeline([
            ('impute', SimpleImputer(strategy='median')),
            ('scale', StandardScaler()),
        ]), numeric_cols),
    ])

    models = {
        'ridge': Ridge(alpha=1.0),
        'gbr': GradientBoostingRegressor(random_state=42),
        'rf': RandomForestRegressor(n_estimators=400, random_state=42, min_samples_leaf=2, n_jobs=-1),
    }

    if groups is not None and len(np.unique(groups)) >= 5:
        cv = GroupKFold(n_splits=5)
        split_iter = list(cv.split(X, y, groups))
    else:
        cv = KFold(n_splits=min(5, len(df)), shuffle=True, random_state=42)
        split_iter = list(cv.split(X, y))

    scorers = {
        'mae': make_scorer(mean_absolute_error, greater_is_better=False),
        'rmse': make_scorer(rmse, greater_is_better=False),
        'r2': make_scorer(r2_score),
    }

    args.outdir.mkdir(parents=True, exist_ok=True)
    results = []
    best_name = None
    best_mae = np.inf
    best_pipe = None

    for name, model in models.items():
        pipe = Pipeline([('pre', pre), ('model', model)])
        scores = cross_validate(pipe, X, y, cv=split_iter, scoring=scorers, return_train_score=False)
        mae = -float(np.mean(scores['test_mae']))
        rmse_val = -float(np.mean(scores['test_rmse']))
        r2 = float(np.mean(scores['test_r2']))
        results.append({'model': name, 'mae': mae, 'rmse': rmse_val, 'r2': r2})
        if mae < best_mae:
            best_mae = mae
            best_name = name
            best_pipe = pipe

    res_df = pd.DataFrame(results).sort_values('mae')
    res_df.to_csv(args.outdir / 'cv_results.csv', index=False)

    best_pipe.fit(X, y)
    joblib.dump(best_pipe, args.outdir / f'best_model_{best_name}.joblib')

    if best_name == 'rf':
        model = best_pipe.named_steps['model']
        importances = model.feature_importances_
        pd.DataFrame({'feature': feature_cols, 'importance': importances}).sort_values('importance', ascending=False).to_csv(args.outdir / 'feature_importance.csv', index=False)

    summary = {
        'target': TARGET,
        'feature_set': args.feature_set,
        'n_samples': int(len(df)),
        'n_runs': int(df['run_name'].nunique()) if 'run_name' in df.columns else None,
        'best_model': best_name,
        'best_cv_mae': float(best_mae),
        'results': results,
    }
    (args.outdir / 'training_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(f'[OK] Wrote ML baseline outputs to: {args.outdir}')
    print(res_df)


if __name__ == '__main__':
    main()
