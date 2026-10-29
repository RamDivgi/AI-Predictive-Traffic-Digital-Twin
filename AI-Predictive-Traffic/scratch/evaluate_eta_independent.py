"""
AI PREDICTIVE TRAFFIC - INDEPENDENT ETA MODEL EVALUATION
======================================================
Performs independent, leakage-resistant evaluation of the Random Forest
and baseline models on deduplicated and grouped simulation data.
"""

from __future__ import annotations

import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
DATASET_CSV = DATA_DIR / "ml_training_dataset.csv"
SAVED_MODEL_FILE = MODELS_DIR / "eta_prediction_model.joblib"

NUMERIC_FEATURES = [
    "ambulance_speed_mps",
    "ambulance_speed_kmh",
    "distance_to_junction_m",
    "vehicle_count",
    "halted_vehicle_count",
    "mean_speed_kmh",
    "occupancy_percent",
    "signal_phase",
    "signal_time_to_switch_s",
]

CATEGORICAL_FEATURES = [
    "junction_id",
    "incoming_edge",
    "outgoing_edge",
]

FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET_COLUMN = "target_arrival_time_s"


def build_preprocessor():
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])
    return ColumnTransformer([
        ("num", numeric_pipeline, NUMERIC_FEATURES),
        ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
    ])


def compute_metrics(y_true, y_pred):
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    abs_err = np.abs(y_true - y_pred)
    
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)
    median_ae = np.median(abs_err)
    p90 = np.percentile(abs_err, 90)
    p95 = np.percentile(abs_err, 95)
    # Target is strictly >= 1.0s, so MAPE is well-defined
    mape = np.mean(abs_err / y_true) * 100.0
    mean_bias = np.mean(y_pred - y_true)
    
    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "median_ae": median_ae,
        "p90": p90,
        "p95": p95,
        "mape": mape,
        "bias": mean_bias,
    }


def run_evaluation():
    print("=" * 80)
    print("AI PREDICTIVE TRAFFIC - INDEPENDENT ETA MODEL EVALUATION")
    print("=" * 80)

    df = pd.read_csv(DATASET_CSV)
    df = df[df["target_is_observed"] == 1].copy()

    # Deduplication analysis
    raw_len = len(df)
    df_dedup = df.drop_duplicates(subset=FEATURE_COLUMNS + [TARGET_COLUMN]).copy().reset_index(drop=True)
    dedup_len = len(df_dedup)
    print(f"Original dataset rows  : {raw_len}")
    print(f"Deduplicated rows      : {dedup_len} ({raw_len - dedup_len} exact duplicates removed)")

    # Group definition
    df_dedup["group_id"] = (
        df_dedup["ambulance_id"].astype(str)
        + "__"
        + df_dedup["junction_id"].astype(str)
        + "__"
        + df_dedup["traffic_scenario"].astype(str)
    )
    groups = df_dedup["group_id"]
    n_groups = groups.nunique()
    print(f"Independent groups     : {n_groups}")

    X = df_dedup[FEATURE_COLUMNS].copy()
    y = df_dedup[TARGET_COLUMN].copy()

    # 1. Evaluate on Held-out 20% GroupSplit (reproducing validation conditions cleanly)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))

    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

    test_groups = sorted(groups.iloc[test_idx].unique())
    train_groups = sorted(groups.iloc[train_idx].unique())
    print()
    print(f"Train samples: {len(X_train)} across {len(train_groups)} groups")
    print(f"Test samples : {len(X_test)} across {len(test_groups)} groups")
    print(f"Test groups  : {test_groups}")

    # Baseline 1: Historical Mean Predictor
    mean_val = y_train.mean()
    y_pred_mean = np.full_like(y_test, mean_val)
    m_mean = compute_metrics(y_test, y_pred_mean)

    # Baseline 2: Physics-Based Distance / Speed Predictor
    speed_mps = np.maximum(X_test["ambulance_speed_mps"].values, 5.0)
    dist_m = X_test["distance_to_junction_m"].values
    y_pred_physics = dist_m / speed_mps
    m_physics = compute_metrics(y_test, y_pred_physics)

    # Baseline 3: Linear Regression
    lr_pipe = Pipeline([("prep", build_preprocessor()), ("model", LinearRegression())])
    lr_pipe.fit(X_train, y_train)
    y_pred_lr = lr_pipe.predict(X_test)
    m_lr = compute_metrics(y_test, y_pred_lr)

    # Candidate 1: Gradient Boosting
    gbr_pipe = Pipeline([
        ("prep", build_preprocessor()),
        ("model", GradientBoostingRegressor(n_estimators=200, learning_rate=0.05, max_depth=3, random_state=42)),
    ])
    gbr_pipe.fit(X_train, y_train)
    y_pred_gbr = gbr_pipe.predict(X_test)
    m_gbr = compute_metrics(y_test, y_pred_gbr)

    # Candidate 2: Random Forest (Freshly trained on train_idx only)
    rf_pipe = Pipeline([
        ("prep", build_preprocessor()),
        ("model", RandomForestRegressor(n_estimators=300, max_depth=12, min_samples_leaf=2, random_state=42, n_jobs=-1)),
    ])
    rf_pipe.fit(X_train, y_train)
    y_pred_rf = rf_pipe.predict(X_test)
    m_rf = compute_metrics(y_test, y_pred_rf)

    # Current Saved Production Model
    m_saved = None
    if SAVED_MODEL_FILE.exists():
        saved_model = joblib.load(SAVED_MODEL_FILE)
        y_pred_saved = saved_model.predict(X_test)
        m_saved = compute_metrics(y_test, y_pred_saved)

    print()
    print("=" * 105)
    print("HELD-OUT GROUP TEST SET PERFORMANCE (Deduplicated Data, Disjoint Groups)")
    print("=" * 105)
    header = f"{'Estimator / Model':28} | {'MAE (s)':>8} | {'RMSE (s)':>8} | {'R²':>8} | {'MedAE (s)':>9} | {'P90 (s)':>8} | {'MAPE (%)':>8} | {'Bias (s)':>8}"
    print(header)
    print("-" * 105)

    models_to_print = [
        ("Historical Mean Baseline", m_mean),
        ("Physics (Dist / Speed) Baseline", m_physics),
        ("Linear Regression", m_lr),
        ("Gradient Boosting", m_gbr),
        ("Random Forest (Clean Split)", m_rf),
    ]
    if m_saved:
        models_to_print.append(("Production Saved Model*", m_saved))

    for name, m in models_to_print:
        print(f"{name:28} | {m['mae']:8.3f} | {m['rmse']:8.3f} | {m['r2']:8.4f} | {m['median_ae']:9.3f} | {m['p90']:8.3f} | {m['mape']:8.2f}% | {m['bias']:+8.3f}")

    print("-" * 105)
    print("* Note: Production Saved Model was originally trained on random row splits prior to group partitioning.")
    print()

    # 2. 5-Fold Group Cross Validation to measure generalization stability
    print("=" * 80)
    print("5-FOLD GROUP CROSS-VALIDATION (Random Forest Across All 15 Groups)")
    print("=" * 80)
    gkf = GroupKFold(n_splits=5)
    cv_maes = []
    cv_rmses = []
    cv_r2s = []

    fold = 1
    for tr_idx, te_idx in gkf.split(X, y, groups=groups):
        X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
        y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]
        fold_rf = Pipeline([
            ("prep", build_preprocessor()),
            ("model", RandomForestRegressor(n_estimators=100, max_depth=12, min_samples_leaf=2, random_state=42, n_jobs=-1)),
        ])
        fold_rf.fit(X_tr, y_tr)
        preds = fold_rf.predict(X_te)
        f_mae = mean_absolute_error(y_te, preds)
        f_rmse = np.sqrt(mean_squared_error(y_te, preds))
        f_r2 = r2_score(y_te, preds)
        cv_maes.append(f_mae)
        cv_rmses.append(f_rmse)
        cv_r2s.append(f_r2)
        test_grps = sorted(groups.iloc[te_idx].unique())
        print(f"  Fold {fold}: MAE={f_mae:.3f}s, RMSE={f_rmse:.3f}s, R²={f_r2:.4f} (Test Groups: {len(test_grps)})")
        fold += 1

    print("-" * 80)
    print(f"5-Fold CV Mean MAE : {np.mean(cv_maes):.3f} ± {np.std(cv_maes):.3f} s")
    print(f"5-Fold CV Mean RMSE: {np.mean(cv_rmses):.3f} ± {np.std(cv_rmses):.3f} s")
    print(f"5-Fold CV Mean R²  : {np.mean(cv_r2s):.4f} ± {np.std(cv_r2s):.4f}")
    print()

    # 3. Residual analysis on held-out test set
    residuals = y_pred_rf - y_test
    print("=" * 80)
    print("RESIDUAL ANALYSIS (Random Forest on Held-Out Test Set)")
    print("=" * 80)
    print(f"Mean Residual (Bias) : {residuals.mean():+.4f} s")
    print(f"Residual Std Dev     : {residuals.std():.4f} s")
    print(f"Min Residual         : {residuals.min():+.4f} s")
    print(f"Max Residual         : {residuals.max():+.4f} s")
    print(f"Under-prediction (< -0.5s): {(residuals < -0.5).sum()} samples ({(residuals < -0.5).mean()*100:.2f}%)")
    print(f"Over-prediction  (> +0.5s): {(residuals > +0.5).sum()} samples ({(residuals > +0.5).mean()*100:.2f}%)")
    print(f"Accurate within ±0.2s     : {(np.abs(residuals) <= 0.2).sum()} samples ({(np.abs(residuals) <= 0.2).mean()*100:.2f}%)")
    print()


if __name__ == "__main__":
    run_evaluation()
