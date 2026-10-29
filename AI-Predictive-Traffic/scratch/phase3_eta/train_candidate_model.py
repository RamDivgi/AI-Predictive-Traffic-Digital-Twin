"""
PHASE 3: CANDIDATE ETA MODEL TRAINING & EVALUATION
==================================================
Trains a leakage-resistant candidate ETA model on the Phase 3 Mangaluru dataset
using strict GroupShuffleSplit and GroupKFold cross-validation grouped by trip_id.

Preservation:
- Strictly isolates model outputs to scratch/phase3_eta/models/.
- Never touches or overwrites models/eta_prediction_model.joblib.
- Compares:
  1. Mean Baseline
  2. Physics Baseline (distance / effective_speed)
  3. Linear Regression Baseline
  4. Random Forest Candidate (regularized)
"""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GroupShuffleSplit, GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, median_absolute_error, r2_score

DATA_PATH = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/data/mangaluru_eta_dataset_v1.csv")
MODEL_DIR = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic/scratch/phase3_eta/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATE_MODEL_PATH = MODEL_DIR / "mangaluru_eta_candidate.joblib"
SCHEMA_PATH = MODEL_DIR / "candidate_schema.json"
REPORT_PATH = MODEL_DIR / "model_evaluation_report.json"

FEATURE_COLUMNS = [
    "ambulance_speed_mps",
    "distance_to_junction_m",
    "vehicle_count",
    "halted_vehicle_count",
    "mean_speed_kmh",
    "occupancy_percent",
    "signal_phase",
    "signal_time_to_switch_s",
]

TARGET_COLUMN = "target_junction_eta_s"


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    errors = np.abs(y_true - y_pred)
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    medae = float(median_absolute_error(y_true, y_pred))
    p90 = float(np.percentile(errors, 90))
    p95 = float(np.percentile(errors, 95))
    r2 = float(r2_score(y_true, y_pred))
    return {
        "mae_s": round(mae, 4),
        "rmse_s": round(rmse, 4),
        "medae_s": round(medae, 4),
        "p90_error_s": round(p90, 4),
        "p95_error_s": round(p95, 4),
        "r2_score": round(r2, 4),
    }


def physics_predict(df_features: pd.DataFrame) -> np.ndarray:
    """
    Physical baseline: distance / max(current_speed, mean_speed, 3.0 m/s)
    """
    dist = df_features["distance_to_junction_m"].values
    spd_mps = df_features["ambulance_speed_mps"].values
    mean_spd_mps = df_features["mean_speed_kmh"].values / 3.6
    
    # Effective speed taking traffic flow and minimal movement into account
    eff_spd = np.maximum(spd_mps, np.maximum(mean_spd_mps, 3.0))
    return dist / eff_spd


def train_and_evaluate():
    print("=" * 85)
    print("PHASE 3: CANDIDATE ETA MODEL TRAINING & EVALUATION")
    print("=" * 85)

    print(f"Loading dataset: {DATA_PATH}")
    df = pd.read_csv(DATA_PATH)
    
    # Filter to valid observed junction targets
    df_valid = df[df["target_junction_observed"] == 1].copy()
    print(f"Loaded {len(df_valid)} valid samples across {df_valid['trip_id'].nunique()} unique trips.")

    X = df_valid[FEATURE_COLUMNS]
    y = df_valid[TARGET_COLUMN].values
    groups = df_valid["trip_id"].values

    # 1. Held-out Trip Split (80% train, 20% test strictly by trip_id)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=2026)
    train_idx, test_idx = next(gss.split(X, y, groups=groups))

    X_train, y_train = X.iloc[train_idx], y[train_idx]
    X_test, y_test = X.iloc[test_idx], y[test_idx]
    df_test = df_valid.iloc[test_idx].copy()

    train_trips = set(df_valid.iloc[train_idx]["trip_id"].unique())
    test_trips = set(df_valid.iloc[test_idx]["trip_id"].unique())
    overlap = len(train_trips.intersection(test_trips))

    print(f"Holdout Split: Train samples={len(X_train)} ({len(train_trips)} trips) | Test samples={len(X_test)} ({len(test_trips)} trips)")
    print(f"Trip Overlap: {overlap} (Strictly zero contamination)")

    # Baseline 1: Historical Mean
    y_mean_pred = np.full_like(y_test, fill_value=np.mean(y_train))
    mean_metrics = compute_metrics(y_test, y_mean_pred)

    # Baseline 2: Physics-based ETA
    y_phys_pred = physics_predict(X_test)
    phys_metrics = compute_metrics(y_test, y_phys_pred)

    # Baseline 3: Ridge Regression
    ridge_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=10.0))
    ])
    ridge_pipe.fit(X_train, y_train)
    y_ridge_pred = ridge_pipe.predict(X_test)
    ridge_metrics = compute_metrics(y_test, y_ridge_pred)

    # Candidate: Random Forest (Regularized to avoid memorization)
    rf_candidate = RandomForestRegressor(
        n_estimators=100,
        max_depth=12,
        min_samples_split=5,
        min_samples_leaf=3,
        max_features="sqrt",
        random_state=2026,
        n_jobs=-1,
    )
    rf_candidate.fit(X_train, y_train)
    y_rf_pred = rf_candidate.predict(X_test)
    rf_metrics = compute_metrics(y_test, y_rf_pred)

    print("\n" + "-" * 75)
    print("HOLDOUT EVALUATION RESULTS (Unseen Trips):")
    print(f"  {'Model / Baseline':<28} | {'MAE (s)':<8} | {'RMSE (s)':<8} | {'MedAE (s)':<9} | {'P90 (s)':<8} | {'R²':<7}")
    print("-" * 75)
    print(f"  {'1. Mean Baseline':<28} | {mean_metrics['mae_s']:<8.3f} | {mean_metrics['rmse_s']:<8.3f} | {mean_metrics['medae_s']:<9.3f} | {mean_metrics['p90_error_s']:<8.3f} | {mean_metrics['r2_score']:<7.4f}")
    print(f"  {'2. Physics Baseline (d/v)':<28} | {phys_metrics['mae_s']:<8.3f} | {phys_metrics['rmse_s']:<8.3f} | {phys_metrics['medae_s']:<9.3f} | {phys_metrics['p90_error_s']:<8.3f} | {phys_metrics['r2_score']:<7.4f}")
    print(f"  {'3. Ridge Regression':<28} | {ridge_metrics['mae_s']:<8.3f} | {ridge_metrics['rmse_s']:<8.3f} | {ridge_metrics['medae_s']:<9.3f} | {ridge_metrics['p90_error_s']:<8.3f} | {ridge_metrics['r2_score']:<7.4f}")
    print(f"  {'4. Random Forest Candidate':<28} | {rf_metrics['mae_s']:<8.3f} | {rf_metrics['rmse_s']:<8.3f} | {rf_metrics['medae_s']:<9.3f} | {rf_metrics['p90_error_s']:<8.3f} | {rf_metrics['r2_score']:<7.4f}")
    print("-" * 75)

    # 2. Breakdown by Traffic Scenario on Test Set
    df_test["rf_pred"] = y_rf_pred
    df_test["rf_abs_err"] = np.abs(y_test - y_rf_pred)
    df_test["phys_abs_err"] = np.abs(y_test - y_phys_pred)

    scenario_breakdown = {}
    for sc in df_test["traffic_scenario"].unique():
        sub = df_test[df_test["traffic_scenario"] == sc]
        y_sub_true = sub[TARGET_COLUMN].values
        y_sub_rf = sub["rf_pred"].values
        scenario_breakdown[sc] = {
            "samples": len(sub),
            "rf_mae_s": round(float(mean_absolute_error(y_sub_true, y_sub_rf)), 3),
            "rf_rmse_s": round(float(np.sqrt(mean_squared_error(y_sub_true, y_sub_rf))), 3),
            "rf_r2": round(float(r2_score(y_sub_true, y_sub_rf)), 4),
            "phys_mae_s": round(float(sub["phys_abs_err"].mean()), 3),
        }

    # 3. 5-Fold Group Cross-Validation
    print("\nRunning 5-Fold Group Cross-Validation across all 32 independent trips...")
    gkf = GroupKFold(n_splits=5)
    cv_rf_maes, cv_rf_rmses, cv_rf_r2s = [], [], []
    cv_phys_maes = []

    for fold, (f_tr_idx, f_val_idx) in enumerate(gkf.split(X, y, groups=groups), start=1):
        f_X_tr, f_y_tr = X.iloc[f_tr_idx], y[f_tr_idx]
        f_X_val, f_y_val = X.iloc[f_val_idx], y[f_val_idx]

        rf_fold = RandomForestRegressor(
            n_estimators=100,
            max_depth=12,
            min_samples_split=5,
            min_samples_leaf=3,
            max_features="sqrt",
            random_state=2026 + fold,
            n_jobs=-1,
        )
        rf_fold.fit(f_X_tr, f_y_tr)
        f_pred = rf_fold.predict(f_X_val)
        f_phys = physics_predict(f_X_val)

        f_mae = float(mean_absolute_error(f_y_val, f_pred))
        f_rmse = float(np.sqrt(mean_squared_error(f_y_val, f_pred)))
        f_r2 = float(r2_score(f_y_val, f_pred))
        p_mae = float(mean_absolute_error(f_y_val, f_phys))

        cv_rf_maes.append(f_mae)
        cv_rf_rmses.append(f_rmse)
        cv_rf_r2s.append(f_r2)
        cv_phys_maes.append(p_mae)

        print(f"  Fold {fold}: RF MAE={f_mae:.3f}s, RMSE={f_rmse:.3f}s, R²={f_r2:.4f} | Physics MAE={p_mae:.3f}s")

    cv_summary = {
        "mean_mae_s": round(float(np.mean(cv_rf_maes)), 4),
        "std_mae_s": round(float(np.std(cv_rf_maes)), 4),
        "mean_rmse_s": round(float(np.mean(cv_rf_rmses)), 4),
        "std_rmse_s": round(float(np.std(cv_rf_rmses)), 4),
        "mean_r2": round(float(np.mean(cv_rf_r2s)), 4),
        "mean_phys_mae_s": round(float(np.mean(cv_phys_maes)), 4),
    }
    print(f"\n5-Fold Group CV Average: RF MAE = {cv_summary['mean_mae_s']} ± {cv_summary['std_mae_s']}s | R² = {cv_summary['mean_r2']}")

    # 4. Feature Importances
    importances = dict(zip(FEATURE_COLUMNS, [round(float(x), 4) for x in rf_candidate.feature_importances_]))
    sorted_importances = dict(sorted(importances.items(), key=lambda item: item[1], reverse=True))

    # 5. Save Artifacts (Isolated Candidate)
    joblib.dump(rf_candidate, CANDIDATE_MODEL_PATH)
    print(f"\nCandidate model saved to: {CANDIDATE_MODEL_PATH}")

    schema_info = {
        "model_type": "RandomForestRegressor",
        "hyperparameters": {
            "n_estimators": 100,
            "max_depth": 12,
            "min_samples_split": 5,
            "min_samples_leaf": 3,
            "max_features": "sqrt",
            "random_state": 2026,
        },
        "target_column": TARGET_COLUMN,
        "feature_columns": FEATURE_COLUMNS,
        "feature_types": {col: str(X[col].dtype) for col in FEATURE_COLUMNS},
        "dataset_version": "mangaluru_eta_dataset_v1.csv",
        "training_samples": len(X_train),
        "test_samples": len(X_test),
        "trip_level_leakage_overlap": 0,
    }
    with open(SCHEMA_PATH, "w", encoding="utf-8") as f:
        json.dump(schema_info, f, indent=2)
    print(f"Feature schema saved to: {SCHEMA_PATH}")

    full_evaluation_report = {
        "holdout_results": {
            "mean_baseline": mean_metrics,
            "physics_baseline": phys_metrics,
            "ridge_regression": ridge_metrics,
            "random_forest_candidate": rf_metrics,
        },
        "scenario_breakdown": scenario_breakdown,
        "cross_validation_5fold": cv_summary,
        "feature_importances": sorted_importances,
        "data_provenance": {
            "dataset_file": str(DATA_PATH),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "train_trips": len(train_trips),
            "test_trips": len(test_trips),
        }
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(full_evaluation_report, f, indent=2)
    print(f"Full evaluation report saved to: {REPORT_PATH}")
    print("=" * 85)


if __name__ == "__main__":
    train_and_evaluate()
