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
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_FILE = (
    PROJECT_ROOT
    / "data"
    / "training_dataset.csv"
)

MODEL_DIR = (
    PROJECT_ROOT
    / "models"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def load_dataset() -> pd.DataFrame:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Training dataset not found:\n{DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE)

    if df.empty:
        raise ValueError(
            "Training dataset is empty."
        )

    print("=" * 80)
    print("DATASET LOADED")
    print("=" * 80)

    print(f"File       : {DATA_FILE}")
    print(f"Rows       : {len(df)}")
    print(f"Columns    : {len(df.columns)}")
    print(
        f"Scenarios  : "
        f"{df['traffic_scenario'].nunique()}"
    )

    print()
    print("Scenario distribution:")

    print(
        df["traffic_scenario"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    return df


# ---------------------------------------------------------------------------
# TARGET CONSTRUCTION
# ---------------------------------------------------------------------------

def create_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construct the observed future arrival-time target.

    For each ambulance/junction pair, the first observation
    at or within 3 meters of the junction is treated as the
    observed arrival event.

    Rows for which no future observed arrival exists receive
    the physically calculated ETA as a fallback. These rows
    are marked with target_is_observed = 0 and are excluded
    from ML training later.
    """

    required_columns = {
        "simulation_time",
        "ambulance_id",
        "junction_id",
        "distance_to_junction_m",
        "ambulance_eta_s",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(sorted(missing))
        )

    df = df.copy()

    df["target_arrival_time_s"] = np.nan
    df["target_is_observed"] = 0

    # Sort chronologically so future arrival events
    # are identified correctly.
    df = df.sort_values(
        [
            "ambulance_id",
            "simulation_time",
        ]
    ).reset_index(drop=True)

    # Process every ambulance/junction trajectory.
    for (
        ambulance_id,
        junction_id,
    ), group in df.groupby(
        [
            "ambulance_id",
            "junction_id",
        ],
        sort=False,
    ):

        indices = group.index.tolist()

        arrival_candidates = group[
            group["distance_to_junction_m"] <= 3.0
        ]

        if arrival_candidates.empty:
            continue

        arrival_time = (
            arrival_candidates[
                "simulation_time"
            ].min()
        )

        for index in indices:

            current_time = df.loc[
                index,
                "simulation_time",
            ]

            if arrival_time > current_time:

                target = (
                    arrival_time
                    - current_time
                )

                df.loc[
                    index,
                    "target_arrival_time_s",
                ] = target

                df.loc[
                    index,
                    "target_is_observed",
                ] = 1

    # Fallback values are retained in the ML dataset for
    # analysis, but NOT used for model training.
    missing_target = (
        df["target_arrival_time_s"]
        .isna()
    )

    df.loc[
        missing_target,
        "target_arrival_time_s",
    ] = df.loc[
        missing_target,
        "ambulance_eta_s",
    ]

    observed_count = int(
        df["target_is_observed"].sum()
    )

    fallback_count = int(
        (df["target_is_observed"] == 0).sum()
    )

    print()
    print("=" * 80)
    print("TARGET CONSTRUCTION")
    print("=" * 80)

    print(
        f"Observed future targets : "
        f"{observed_count}"
    )

    print(
        f"Fallback ETA targets    : "
        f"{fallback_count}"
    )

    print(
        f"Target range            : "
        f"{df['target_arrival_time_s'].min():.2f} - "
        f"{df['target_arrival_time_s'].max():.2f} s"
    )

    return df


# ---------------------------------------------------------------------------
# OBSERVED-TARGET FILTER
# ---------------------------------------------------------------------------

def filter_observed_targets(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Keep only observations for which the future arrival
    time was actually observed in the SUMO trajectory.

    Fallback ETA values are deliberately excluded from
    model training because they are calculated estimates,
    not ground-truth observations.
    """

    observed_df = df[
        df["target_is_observed"] == 1
    ].copy()

    observed_df = (
        observed_df
        .sort_values(
            [
                "ambulance_id",
                "simulation_time",
            ]
        )
        .reset_index(drop=True)
    )

    if observed_df.empty:
        raise ValueError(
            "No observed target samples are available "
            "for ML training."
        )

    print()
    print("=" * 80)
    print("TRAINING TARGET FILTER")
    print("=" * 80)

    print(
        f"Original samples       : {len(df)}"
    )

    print(
        f"Observed samples       : {len(observed_df)}"
    )

    print(
        f"Excluded fallback rows : "
        f"{len(df) - len(observed_df)}"
    )

    print(
        f"Observed target range  : "
        f"{observed_df['target_arrival_time_s'].min():.2f} - "
        f"{observed_df['target_arrival_time_s'].max():.2f} s"
    )

    return observed_df


# ---------------------------------------------------------------------------
# FEATURE SELECTION
# ---------------------------------------------------------------------------

def prepare_features(
    df: pd.DataFrame,
):
    """
    Select features available at prediction time.

    ambulance_eta_s is intentionally excluded because it is
    itself a manually calculated ETA and would introduce
    direct target information into the ML model.
    """

    feature_columns = [
        "ambulance_speed_mps",
        "ambulance_speed_kmh",
        "distance_to_junction_m",
        "vehicle_count",
        "halted_vehicle_count",
        "mean_speed_kmh",
        "occupancy_percent",
        "signal_phase",
        "signal_time_to_switch_s",
        "junction_id",
        "incoming_edge",
        "outgoing_edge",
    ]

    target_column = (
        "target_arrival_time_s"
    )

    missing = [
        column
        for column in feature_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing feature columns: "
            + ", ".join(missing)
        )

    X = df[
        feature_columns
    ].copy()

    y = df[
        target_column
    ].copy()

    return (
        X,
        y,
        feature_columns,
    )


# ---------------------------------------------------------------------------
# PREPROCESSING
# ---------------------------------------------------------------------------

def build_preprocessor(
    feature_columns,
):
    numeric_features = [
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

    categorical_features = [
        "junction_id",
        "incoming_edge",
        "outgoing_edge",
    ]

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
                    handle_unknown="ignore",
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                numeric_features,
            ),
            (
                "categorical",
                categorical_pipeline,
                categorical_features,
            ),
        ]
    )


# ---------------------------------------------------------------------------
# MODEL EVALUATION
# ---------------------------------------------------------------------------

def evaluate_model(
    name: str,
    model,
    X_train,
    X_test,
    y_train,
    y_test,
):
    print()
    print("=" * 80)
    print(f"TRAINING: {name}")
    print("=" * 80)

    model.fit(
        X_train,
        y_train,
    )

    predictions = model.predict(
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
        "model": model,
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
    }


# ---------------------------------------------------------------------------
# MAIN ML PIPELINE
# ---------------------------------------------------------------------------

def main():
    print()
    print("=" * 80)
    print("AI PREDICTIVE TRAFFIC - ML PIPELINE")
    print("=" * 80)

    # -------------------------------------------------------
    # 1. Load raw training dataset
    # -------------------------------------------------------

    df = load_dataset()

    # -------------------------------------------------------
    # 2. Construct future arrival target
    # -------------------------------------------------------

    df = create_target(
        df
    )

    # -------------------------------------------------------
    # 3. Keep ONLY observed targets
    # -------------------------------------------------------

    training_df = (
        filter_observed_targets(
            df
        )
    )

    # -------------------------------------------------------
    # 4. Prepare ML features and target
    # -------------------------------------------------------

    X, y, feature_columns = (
        prepare_features(
            training_df
        )
    )

    print()
    print("=" * 80)
    print("FEATURES")
    print("=" * 80)

    for feature in feature_columns:
        print(
            f"- {feature}"
        )

    print()
    print(
        f"Training samples: "
        f"{len(X)}"
    )

    # -------------------------------------------------------
    # 5. Train/test split
    # -------------------------------------------------------

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=42,
        )
    )

    print(
        f"Training set   : "
        f"{len(X_train)}"
    )

    print(
        f"Test set       : "
        f"{len(X_test)}"
    )

    # -------------------------------------------------------
    # 6. Preprocessor
    # -------------------------------------------------------

    preprocessor = (
        build_preprocessor(
            feature_columns
        )
    )

    # -------------------------------------------------------
    # 7. Candidate models
    # -------------------------------------------------------

    models = [
        (
            "Linear Regression",
            LinearRegression(),
        ),
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

    results = []

    # -------------------------------------------------------
    # 8. Train and evaluate
    # -------------------------------------------------------

    for name, estimator in models:

        pipeline = Pipeline(
            steps=[
                (
                    "preprocessor",
                    preprocessor,
                ),
                (
                    "model",
                    estimator,
                ),
            ]
        )

        result = evaluate_model(
            name,
            pipeline,
            X_train,
            X_test,
            y_train,
            y_test,
        )

        results.append(
            result
        )

    # -------------------------------------------------------
    # 9. Select best model
    # -------------------------------------------------------

    best = min(
        results,
        key=lambda result: result["mae"],
    )

    # -------------------------------------------------------
    # 10. Model comparison
    # -------------------------------------------------------

    print()
    print("=" * 80)
    print("MODEL COMPARISON")
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
    # 11. Best model
    # -------------------------------------------------------

    print()
    print("=" * 80)
    print("BEST MODEL")
    print("=" * 80)

    print(
        f"Model : "
        f"{best['name']}"
    )

    print(
        f"MAE   : "
        f"{best['mae']:.3f} seconds"
    )

    print(
        f"RMSE  : "
        f"{best['rmse']:.3f} seconds"
    )

    print(
        f"R²    : "
        f"{best['r2']:.4f}"
    )

    # -------------------------------------------------------
    # 12. Save best model
    # -------------------------------------------------------

    model_path = (
        MODEL_DIR
        / "eta_prediction_model.joblib"
    )

    joblib.dump(
        best["model"],
        model_path,
    )

    print()
    print(
        f"Saved model: "
        f"{model_path}"
    )

    # -------------------------------------------------------
    # 13. Save clean ML dataset
    # -------------------------------------------------------

    dataset_path = (
        PROJECT_ROOT
        / "data"
        / "ml_training_dataset.csv"
    )

    training_df.to_csv(
        dataset_path,
        index=False,
    )

    print(
        f"Saved ML dataset: "
        f"{dataset_path}"
    )

    # -------------------------------------------------------
    # 14. Completion
    # -------------------------------------------------------

    print()
    print("=" * 80)
    print("ML PIPELINE COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()