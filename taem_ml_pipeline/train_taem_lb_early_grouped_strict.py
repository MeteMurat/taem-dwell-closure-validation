#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

TARGET = "taem_lb_score"
NON_FEATURES = {
    "run_name", "group_run_name", "failure_mode", "end_reason", "guide_phase_last",
    TARGET, "taem_end_score", "taem_reached",
    "s_go_last_m", "lon_end_deg", "lat_end_deg", "h_err_minabs_m", "v_err_minabs_mps",
    "s_go_err_minabs_m", "psi_err_minabs_rad", "q1_t_end", "q1_q_max", "dwell_max_s",
    "taem_h_err_last", "taem_h_err_minabs", "taem_v_err_last", "taem_v_err_minabs",
    "taem_s_go_err_last", "taem_s_go_err_minabs", "taem_psi_err_last", "taem_psi_err_minabs",
    "taem_dwell_s", "taem_dwell_max_s", "height_last", "velocity_last", "s_go_last",
}


def rmse(y_true, y_pred):
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def _to_num_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def get_feature_cols(df: pd.DataFrame, feature_set: str) -> list[str]:
    candidate_cols = [c for c in df.columns if c not in NON_FEATURES]
    candidate_cols = [c for c in candidate_cols if not c.startswith("cfg_run_name")]
    if feature_set == "config_only":
        cols = [c for c in candidate_cols if c.startswith("cfg_") or c.startswith("own_") or c.startswith("is_mis") or c == "vehicle_id"]
    elif feature_set == "early_only":
        cols = [c for c in candidate_cols if c.startswith("early_")]
    elif feature_set == "config_plus_early":
        cols = [c for c in candidate_cols if c.startswith("cfg_") or c.startswith("own_") or c.startswith("is_mis") or c == "vehicle_id" or c.startswith("early_")]
    else:
        raise ValueError(feature_set)
    return cols


def build_preprocessor(X: pd.DataFrame) -> tuple[ColumnTransformer, list[str]]:
    Xn = _to_num_df(X)
    usable_cols = [c for c in Xn.columns if not Xn[c].isna().all()]
    pre = ColumnTransformer([
        (
            "num",
            Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]),
            usable_cols,
        )
    ], remainder="drop")
    return pre, usable_cols


def evaluate_grouped_cv(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, models: dict, usable_cols: list[str]):
    unique_groups = pd.unique(groups)
    n_splits = min(5, len(unique_groups))
    if n_splits < 3:
        raise SystemExit("Need at least 3 unique runs for grouped CV.")
    cv = GroupKFold(n_splits=n_splits)

    rows = []
    fold_rows = []
    for name, model in models.items():
        maes, rmses, r2s = [], [], []
        for fold_id, (tr, te) in enumerate(cv.split(X, y, groups=groups), start=1):
            pre, usable_cols_fold = build_preprocessor(X.iloc[tr][usable_cols])
            pipe = Pipeline([("pre", pre), ("model", clone(model))])
            pipe.fit(X.iloc[tr][usable_cols_fold], y[tr])
            pred = pipe.predict(X.iloc[te][usable_cols_fold])
            mae = mean_absolute_error(y[te], pred)
            rmse_val = rmse(y[te], pred)
            r2 = r2_score(y[te], pred) if len(np.unique(y[te])) > 1 else np.nan
            maes.append(mae); rmses.append(rmse_val); r2s.append(r2)
            fold_rows.append({"model": name, "fold": fold_id, "mae": mae, "rmse": rmse_val, "r2": r2, "n_test": int(len(te))})
        rows.append({"model": name, "mae": float(np.mean(maes)), "rmse": float(np.mean(rmses)), "r2": float(np.nanmean(r2s))})
    return pd.DataFrame(rows).sort_values("mae"), pd.DataFrame(fold_rows)


def fit_and_eval_holdout(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, model, usable_cols: list[str]):
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    tr, te = next(gss.split(X, y, groups=groups))
    pre, usable_cols_final = build_preprocessor(X.iloc[tr][usable_cols])
    pipe = Pipeline([("pre", pre), ("model", clone(model))])
    pipe.fit(X.iloc[tr][usable_cols_final], y[tr])
    pred = pipe.predict(X.iloc[te][usable_cols_final])
    holdout = {
        "mae": float(mean_absolute_error(y[te], pred)),
        "rmse": float(rmse(y[te], pred)),
        "r2": float(r2_score(y[te], pred)) if len(np.unique(y[te])) > 1 else np.nan,
        "n_train": int(len(tr)),
        "n_test": int(len(te)),
        "n_train_runs": int(pd.Series(groups[tr]).nunique()),
        "n_test_runs": int(pd.Series(groups[te]).nunique()),
    }
    return pipe, usable_cols_final, tr, te, holdout


def compute_permutation_importance_from_pipe(pipe: Pipeline, X_test: pd.DataFrame, y_test: np.ndarray) -> pd.DataFrame:
    pre = pipe.named_steps["pre"]
    model = pipe.named_steps["model"]
    Xt = pre.transform(X_test)
    if Xt.shape[0] < 3:
        try:
            feat_names = list(pre.get_feature_names_out())
        except Exception:
            feat_names = [f"f{i}" for i in range(Xt.shape[1])]
        return pd.DataFrame({
            "feature": feat_names,
            "perm_importance_mean_neg_mae": np.nan,
            "perm_importance_std": np.nan,
        })
    perm = permutation_importance(
        model,
        Xt,
        y_test,
        scoring="neg_mean_absolute_error",
        n_repeats=20,
        random_state=42,
    )
    try:
        feat_names = list(pre.get_feature_names_out())
    except Exception:
        feat_names = [f"f{i}" for i in range(Xt.shape[1])]
    if len(feat_names) != len(perm.importances_mean):
        feat_names = [f"f{i}" for i in range(len(perm.importances_mean))]
    return pd.DataFrame({
        "feature": feat_names,
        "perm_importance_mean_neg_mae": perm.importances_mean,
        "perm_importance_std": perm.importances_std,
    }).sort_values("perm_importance_mean_neg_mae", ascending=False)


def main():
    ap = argparse.ArgumentParser(description="Train early-phase-only stricter run-grouped TAEM surrogate models.")
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--feature-sets", nargs="+", default=["config_only", "early_only", "config_plus_early"])
    args = ap.parse_args()

    df = pd.read_csv(args.dataset, low_memory=False)
    y_series = pd.to_numeric(df[TARGET], errors="coerce")
    df = df[np.isfinite(y_series)].copy()
    if df.empty:
        raise SystemExit("No valid rows with finite taem_lb_score found.")
    if "group_run_name" not in df.columns and "run_name" in df.columns:
        df["group_run_name"] = df["run_name"]
    groups = df["group_run_name"].astype(str).to_numpy()
    y = pd.to_numeric(df[TARGET], errors="coerce").astype(float).to_numpy()

    models = {
        "ridge": Ridge(alpha=1.0),
        "gbr": GradientBoostingRegressor(random_state=42),
        "rf": RandomForestRegressor(n_estimators=500, random_state=42, min_samples_leaf=2, n_jobs=-1),
    }

    args.outdir.mkdir(parents=True, exist_ok=True)

    cv_tables = []
    fold_tables = []
    holdout_rows = []
    best_bundle = None

    for fs in args.feature_sets:
        feature_cols = get_feature_cols(df, fs)
        X = df[feature_cols].copy()
        Xn = _to_num_df(X)
        usable_cols = [c for c in Xn.columns if not Xn[c].isna().all()]
        X = Xn[usable_cols]
        cv_df, fold_df = evaluate_grouped_cv(X, y, groups, models, usable_cols)
        cv_df.insert(0, "feature_set", fs)
        fold_df.insert(0, "feature_set", fs)
        cv_tables.append(cv_df)
        fold_tables.append(fold_df)

        best_row = cv_df.iloc[0]
        best_model_name = str(best_row["model"])
        best_model = models[best_model_name]
        pipe, usable_cols_final, tr, te, holdout = fit_and_eval_holdout(X, y, groups, best_model, usable_cols)
        holdout_rows.append({"feature_set": fs, "model": best_model_name, **holdout})

        bundle = {
            "feature_set": fs,
            "model_name": best_model_name,
            "cv_mae": float(best_row["mae"]),
            "cv_rmse": float(best_row["rmse"]),
            "cv_r2": float(best_row["r2"]),
            "pipe": pipe,
            "X": X,
            "y": y,
            "groups": groups,
            "usable_cols": usable_cols_final,
            "test_idx": te,
            "holdout": holdout,
        }
        if best_bundle is None or bundle["cv_mae"] < best_bundle["cv_mae"]:
            best_bundle = bundle

    cv_all = pd.concat(cv_tables, ignore_index=True)
    fold_all = pd.concat(fold_tables, ignore_index=True)
    holdout_df = pd.DataFrame(holdout_rows).sort_values(["mae", "rmse"])

    cv_all.to_csv(args.outdir / "grouped_cv_results.csv", index=False)
    fold_all.to_csv(args.outdir / "grouped_cv_folds.csv", index=False)
    holdout_df.to_csv(args.outdir / "grouped_holdout_results.csv", index=False)

    joblib.dump(best_bundle["pipe"], args.outdir / f"best_model_{best_bundle['model_name']}_{best_bundle['feature_set']}.joblib")

    X_test = best_bundle["X"].iloc[best_bundle["test_idx"]][best_bundle["usable_cols"]]
    y_test = best_bundle["y"][best_bundle["test_idx"]]
    fi = compute_permutation_importance_from_pipe(best_bundle["pipe"], X_test, y_test)
    fi.to_csv(args.outdir / "feature_importance_permutation.csv", index=False)

    lines = []
    lines.append("# TAEM early-phase grouped-CV training report\n")
    lines.append(f"- Samples: **{len(df)}**")
    lines.append(f"- Runs: **{pd.Series(groups).nunique()}**")
    lines.append(f"- Target: **{TARGET}**")
    lines.append(f"- Best feature set: **{best_bundle['feature_set']}**")
    lines.append(f"- Best model: **{best_bundle['model_name']}**")
    lines.append(f"- Best grouped-CV MAE: **{best_bundle['cv_mae']:.4f}**")
    lines.append(f"- Best grouped-CV RMSE: **{best_bundle['cv_rmse']:.4f}**")
    lines.append(f"- Best grouped-CV R2: **{best_bundle['cv_r2']:.4f}**")
    lines.append(f"- Holdout MAE: **{best_bundle['holdout']['mae']:.4f}**")
    lines.append(f"- Holdout RMSE: **{best_bundle['holdout']['rmse']:.4f}**")
    lines.append(f"- Holdout R2: **{best_bundle['holdout']['r2']:.4f}**")
    lines.append("\n## Ablation summary\n")
    lines.append(holdout_df.to_markdown(index=False))
    lines.append("\n## Top permutation importances\n")
    lines.append(fi.head(20).to_markdown(index=False))
    (args.outdir / "training_report.md").write_text("\n".join(lines), encoding="utf-8")

    summary = {
        "target": TARGET,
        "n_samples": int(len(df)),
        "n_runs": int(pd.Series(groups).nunique()),
        "evaluation": "run_grouped_cv_plus_grouped_holdout",
        "feature_sets": args.feature_sets,
        "best_feature_set": best_bundle["feature_set"],
        "best_model": best_bundle["model_name"],
        "best_grouped_cv": {
            "mae": best_bundle["cv_mae"],
            "rmse": best_bundle["cv_rmse"],
            "r2": best_bundle["cv_r2"],
        },
        "best_holdout": best_bundle["holdout"],
    }
    (args.outdir / "training_summary_strict.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"[OK] Wrote early grouped-strict training outputs to: {args.outdir}")
    print(cv_all.sort_values(["mae"]).head())
    print("\n[HOLDOUT]")
    print(holdout_df)


if __name__ == "__main__":
    main()
