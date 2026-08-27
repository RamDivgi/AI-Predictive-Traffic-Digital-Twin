from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    GradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = (
    PROJECT_ROOT
    / "data"
    / "ml_training_dataset.csv"
)

MODEL_FILE = (
    PROJECT_ROOT
    / "models"
    / "eta_prediction_model.joblib"
)


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

FEATURE_COLUMNS = (
    NUMERIC_FEATURES
    + CATEGORICAL_FEATURES
)

TARGET_COLUMN = "target_arrival_time_s"


def load_data() -> pd.DataFrame:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"ML dataset not found:\n{DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE)

    if df.empty:
        raise ValueError(
            "ML dataset is empty."
        )

    required = (
        FEATURE_COLUMNS
        + [
            TARGET_COLUMN,
            "target_is_observed",
            "ambulance_id",
            "simulation_time",
        ]
    )

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
        )

    # Never validate against fallback targets.
    df = df[
        df["target_is_observed"] == 1
    ].copy()

    if df.empty:
        raise ValueError(
            "No observed target rows available."
        )

    return df.reset_index(drop=True)


def build_preprocessor() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median"
                ),
            ),
            (
                "scaler",
                StandardScaler(),
            ),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="most_frequent"
                ),
            ),
            (
                "encoder",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                categorical_pipeline,
                CATEGORICAL_FEATURES,
            ),
        ]
    )


def build_models() -> list[tuple[str, object]]:
    return [
        (
            "Gradient Boosting",
            GradientBoostingRegressor(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=3,
                random_state=42,
            ),
        ),
        (
            "Random Forest",
            RandomForestRegressor(
                n_estimators=300,
                max_depth=12,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ]


def evaluate(
    name: str,
    estimator,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
):
    pipeline = Pipeline(
        steps=[
            (
                "preprocessor",
                build_preprocessor(),
            ),
            (
                "model",
                estimator,
            ),
        ]
    )

    pipeline.fit(
        X_train,
        y_train,
    )

    predictions = pipeline.predict(
        X_test
    )

    mae = mean_absolute_error(
        y_test,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions,
        )
    )

    r2 = r2_score(
        y_test,
        predictions,
    )

    print()
    print("=" * 80)
    print(f"MODEL: {name}")
    print("=" * 80)

    print(
        f"MAE  : {mae:.3f} seconds"
    )

    print(
        f"RMSE : {rmse:.3f} seconds"
    )

    print(
        f"R²   : {r2:.4f}"
    )

    return {
        "name": name,
        "pipeline": pipeline,
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
    }


def main() -> None:
    print()
    print("=" * 80)
    print("AI PREDICTIVE TRAFFIC - LEAKAGE-RESISTANT ML VALIDATION")
    print("=" * 80)

    df = load_data()

    print()
    print("=" * 80)
    print("VALIDATION DATA")
    print("=" * 80)

    print(
        f"Observed samples : {len(df)}"
    )

    print(
        f"Target range     : "
        f"{df[TARGET_COLUMN].min():.2f} - "
        f"{df[TARGET_COLUMN].max():.2f} s"
    )

    # -------------------------------------------------------
    # Group definition
    # -------------------------------------------------------
    #
    # All observations belonging to the same ambulance +
    # junction trajectory stay together.
    #
    # This prevents nearly identical sequential observations
    # from appearing in both training and testing.
    # -------------------------------------------------------

    df["validation_group"] = (
        df["ambulance_id"].astype(str)
        + "__"
        + df["junction_id"].astype(str)
        + "__"
        + df["traffic_scenario"].astype(str)
    )

    groups = df[
        "validation_group"
    ]

    print(
        f"Validation groups: "
        f"{groups.nunique()}"
    )

    X = df[
        FEATURE_COLUMNS
    ].copy()

    y = df[
        TARGET_COLUMN
    ].copy()

    # -------------------------------------------------------
    # Grouped 80/20 split
    # -------------------------------------------------------

    splitter = GroupShuffleSplit(
        n_splits=1,
        test_size=0.20,
        random_state=42,
    )

    train_indices, test_indices = next(
        splitter.split(
            X,
            y,
            groups=groups,
        )
    )

    X_train = X.iloc[
        train_indices
    ].copy()

    X_test = X.iloc[
        test_indices
    ].copy()

    y_train = y.iloc[
        train_indices
    ].copy()

    y_test = y.iloc[
        test_indices
    ].copy()

    train_groups = groups.iloc[
        train_indices
    ]

    test_groups = groups.iloc[
        test_indices
    ]

    print()
    print(
        f"Training samples : {len(X_train)}"
    )

    print(
        f"Test samples     : {len(X_test)}"
    )

    print(
        f"Training groups  : "
        f"{train_groups.nunique()}"
    )

    print(
        f"Test groups      : "
        f"{test_groups.nunique()}"
    )

    overlap = (
        set(train_groups)
        & set(test_groups)
    )

    print(
        f"Group overlap    : "
        f"{len(overlap)}"
    )

    if overlap:
        raise RuntimeError(
            "Validation leakage detected: "
            "train/test groups overlap."
        )

    # -------------------------------------------------------
    # Train candidate models
    # -------------------------------------------------------

    results = []

    for name, estimator in build_models():

        result = evaluate(
            name,
            estimator,
            X_train,
            X_test,
            y_train,
            y_test,
        )

        results.append(
            result
        )

    # -------------------------------------------------------
    # Comparison
    # -------------------------------------------------------

    print()
    print("=" * 80)
    print("LEAKAGE-RESISTANT MODEL COMPARISON")
    print("=" * 80)

    print(
        f"{'Model':25}"
        f"{'MAE':>12}"
        f"{'RMSE':>12}"
        f"{'R²':>12}"
    )

    print("-" * 61)

    for result in results:
        print(
            f"{result['name']:25}"
            f"{result['mae']:12.3f}"
            f"{result['rmse']:12.3f}"
            f"{result['r2']:12.4f}"
        )

    # -------------------------------------------------------
    # Best model
    # -------------------------------------------------------

    best = min(
        results,
        key=lambda result: result["mae"],
    )

    print()
    print("=" * 80)
    print("VALIDATION RESULT")
    print("=" * 80)

    print(
        f"Best model : "
        f"{best['name']}"
    )

    print(
        f"MAE        : "
        f"{best['mae']:.3f} seconds"
    )

    print(
        f"RMSE       : "
        f"{best['rmse']:.3f} seconds"
    )

    print(
        f"R²         : "
        f"{best['r2']:.4f}"
    )

    # -------------------------------------------------------
    # Compare with currently saved model
    # -------------------------------------------------------

    if MODEL_FILE.exists():
        try:
            saved_model = joblib.load(
                MODEL_FILE
            )

            saved_predictions = (
                saved_model.predict(
                    X_test
                )
            )

            saved_mae = (
                mean_absolute_error(
                    y_test,
                    saved_predictions,
                )
            )

            saved_rmse = np.sqrt(
                mean_squared_error(
                    y_test,
                    saved_predictions,
                )
            )

            saved_r2 = r2_score(
                y_test,
                saved_predictions,
            )

            print()
            print("=" * 80)
            print("CURRENT SAVED MODEL ON GROUPED TEST SET")
            print("=" * 80)

            print(
                f"MAE  : "
                f"{saved_mae:.3f} seconds"
            )

            print(
                f"RMSE : "
                f"{saved_rmse:.3f} seconds"
            )

            print(
                f"R²   : "
                f"{saved_r2:.4f}"
            )

        except Exception as exc:
            print()
            print(
                "WARNING: Could not evaluate "
                f"saved model: {exc}"
            )

    print()
    print("=" * 80)
    print("ML VALIDATION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()