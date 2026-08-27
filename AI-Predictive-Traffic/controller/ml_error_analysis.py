from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import GroupShuffleSplit


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

ANALYSIS_COLUMNS = (
    FEATURE_COLUMNS
    + [
        "traffic_scenario",
        "ambulance_id",
        "simulation_time",
    ]
)


def load_data() -> pd.DataFrame:
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"ML dataset not found:\n{DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE)

    df = df[
        df["target_is_observed"] == 1
    ].copy()

    if df.empty:
        raise ValueError(
            "No observed target rows found."
        )

    required_analysis_columns = [
        *FEATURE_COLUMNS,
        TARGET_COLUMN,
        "target_is_observed",
        "ambulance_id",
        "simulation_time",
        "traffic_scenario",
    ]

    missing = [
        column
        for column in required_analysis_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing)
        )

    return df.reset_index(drop=True)


def create_grouped_split(
    df: pd.DataFrame,
):
    """
    Create a trajectory-aware grouped test set.

    traffic_scenario is used only to define validation groups.
    It is NOT supplied to the ML model.
    """

    df = df.copy()

    df["validation_group"] = (
        df["ambulance_id"].astype(str)
        + "__"
        + df["junction_id"].astype(str)
        + "__"
        + df["traffic_scenario"].astype(str)
    )

    X = df[
        FEATURE_COLUMNS
    ]

    y = df[
        TARGET_COLUMN
    ]

    groups = df[
        "validation_group"
    ]

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

    test_df = df.iloc[
        test_indices
    ].copy()

    X_test = test_df[
        FEATURE_COLUMNS
    ].copy()

    y_test = test_df[
        TARGET_COLUMN
    ].copy()

    return (
        df,
        X_test,
        y_test,
        test_df,
    )


def get_feature_importance(
    model,
):
    """
    Extract Random Forest feature importance.

    One-hot encoded categorical features are grouped back
    into their original logical feature names.
    """

    preprocessor = (
        model.named_steps[
            "preprocessor"
        ]
    )

    estimator = (
        model.named_steps[
            "model"
        ]
    )

    importances = (
        estimator.feature_importances_
    )

    transformed_names = (
        preprocessor
        .get_feature_names_out()
    )

    grouped_importance = {}

    categorical_names = {
        "junction_id",
        "incoming_edge",
        "outgoing_edge",
    }

    for transformed_name, importance in zip(
        transformed_names,
        importances,
    ):

        original_name = transformed_name

        if original_name.startswith(
            "numeric__"
        ):
            original_name = (
                original_name[
                    len("numeric__") :
                ]
            )

        elif original_name.startswith(
            "categorical__"
        ):
            original_name = (
                original_name[
                    len("categorical__") :
                ]
            )

            for category in categorical_names:
                if original_name.startswith(
                    category + "_"
                ):
                    original_name = category
                    break

        grouped_importance[
            original_name
        ] = (
            grouped_importance.get(
                original_name,
                0.0,
            )
            + importance
        )

    result = pd.DataFrame(
        [
            {
                "feature": feature,
                "importance": importance,
            }
            for feature, importance
            in grouped_importance.items()
        ]
    )

    return result.sort_values(
        "importance",
        ascending=False,
    ).reset_index(drop=True)


def analyze_predictions(
    model,
    X_test,
    y_test,
    test_df,
):
    predictions = model.predict(
        X_test
    )

    analysis = test_df.copy()

    analysis[
        "actual_eta_s"
    ] = y_test.values

    analysis[
        "predicted_eta_s"
    ] = predictions

    analysis[
        "absolute_error_s"
    ] = np.abs(
        analysis["actual_eta_s"]
        - analysis["predicted_eta_s"]
    )

    analysis[
        "signed_error_s"
    ] = (
        analysis["predicted_eta_s"]
        - analysis["actual_eta_s"]
    )

    return analysis


def print_overall_metrics(
    analysis: pd.DataFrame,
):
    actual = analysis[
        "actual_eta_s"
    ]

    predicted = analysis[
        "predicted_eta_s"
    ]

    mae = mean_absolute_error(
        actual,
        predicted,
    )

    rmse = np.sqrt(
        mean_squared_error(
            actual,
            predicted,
        )
    )

    r2 = r2_score(
        actual,
        predicted,
    )

    print()
    print("=" * 80)
    print("VALIDATION METRICS")
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


def print_eta_range_analysis(
    analysis: pd.DataFrame,
):
    analysis = analysis.copy()

    analysis["eta_range"] = pd.cut(
        analysis["actual_eta_s"],
        bins=[
            0,
            5,
            10,
            15,
            20,
            30,
            np.inf,
        ],
        labels=[
            "0-5s",
            "5-10s",
            "10-15s",
            "15-20s",
            "20-30s",
            "30s+",
        ],
        include_lowest=True,
    )

    print()
    print("=" * 80)
    print("ERROR BY ETA RANGE")
    print("=" * 80)

    print(
        f"{'ETA Range':12}"
        f"{'Samples':>10}"
        f"{'MAE':>12}"
        f"{'Max Error':>14}"
    )

    print("-" * 50)

    for eta_range, group in (
        analysis.groupby(
            "eta_range",
            observed=False,
        )
    ):

        if group.empty:
            continue

        mae = mean_absolute_error(
            group["actual_eta_s"],
            group["predicted_eta_s"],
        )

        max_error = (
            group["absolute_error_s"]
            .max()
        )

        print(
            f"{str(eta_range):12}"
            f"{len(group):10}"
            f"{mae:12.3f}"
            f"{max_error:14.3f}"
        )


def print_scenario_analysis(
    analysis: pd.DataFrame,
):
    """
    Analyze model error by the original SUMO scenario.

    traffic_scenario is NOT an ML feature.
    It is retained only for post-training analysis.
    """

    print()
    print("=" * 80)
    print("ERROR BY TRAFFIC SCENARIO")
    print("=" * 80)

    print(
        f"{'Scenario':15}"
        f"{'Samples':>10}"
        f"{'MAE':>12}"
        f"{'RMSE':>12}"
    )

    print("-" * 52)

    for scenario, group in (
        analysis.groupby(
            "traffic_scenario"
        )
    ):

        mae = mean_absolute_error(
            group["actual_eta_s"],
            group["predicted_eta_s"],
        )

        rmse = np.sqrt(
            mean_squared_error(
                group["actual_eta_s"],
                group["predicted_eta_s"],
            )
        )

        print(
            f"{scenario:15}"
            f"{len(group):10}"
            f"{mae:12.3f}"
            f"{rmse:12.3f}"
        )


def print_junction_analysis(
    analysis: pd.DataFrame,
):
    print()
    print("=" * 80)
    print("ERROR BY JUNCTION")
    print("=" * 80)

    print(
        f"{'Junction':15}"
        f"{'Samples':>10}"
        f"{'MAE':>12}"
        f"{'RMSE':>12}"
    )

    print("-" * 52)

    for junction, group in (
        analysis.groupby(
            "junction_id"
        )
    ):

        mae = mean_absolute_error(
            group["actual_eta_s"],
            group["predicted_eta_s"],
        )

        rmse = np.sqrt(
            mean_squared_error(
                group["actual_eta_s"],
                group["predicted_eta_s"],
            )
        )

        print(
            f"{junction:15}"
            f"{len(group):10}"
            f"{mae:12.3f}"
            f"{rmse:12.3f}"
        )


def print_worst_predictions(
    analysis: pd.DataFrame,
    count: int = 15,
):
    print()
    print("=" * 80)
    print(
        f"WORST {count} PREDICTIONS"
    )
    print("=" * 80)

    worst = (
        analysis
        .sort_values(
            "absolute_error_s",
            ascending=False,
        )
        .head(count)
    )

    print(
        f"{'Actual':>10}"
        f"{'Predicted':>12}"
        f"{'Error':>10}"
        f"{'Distance':>12}"
        f"{'Speed':>10}"
        f"{'Vehicles':>10}"
        f"{'Scenario':>14}"
        f"{'Junction':>10}"
    )

    print("-" * 92)

    for _, row in worst.iterrows():

        print(
            f"{row['actual_eta_s']:10.2f}"
            f"{row['predicted_eta_s']:12.2f}"
            f"{row['absolute_error_s']:10.2f}"
            f"{row['distance_to_junction_m']:12.2f}"
            f"{row['ambulance_speed_kmh']:10.2f}"
            f"{row['vehicle_count']:10.0f}"
            f"{str(row['traffic_scenario']):>14}"
            f"{str(row['junction_id']):>10}"
        )


def save_analysis(
    analysis: pd.DataFrame,
):
    output_file = (
        PROJECT_ROOT
        / "data"
        / "ml_error_analysis.csv"
    )

    analysis.to_csv(
        output_file,
        index=False,
    )

    print()
    print(
        f"Saved error analysis: "
        f"{output_file}"
    )


def main():
    print()
    print("=" * 80)
    print(
        "AI PREDICTIVE TRAFFIC - "
        "ML ERROR ANALYSIS"
    )
    print("=" * 80)

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"Model not found:\n{MODEL_FILE}"
        )

    df = load_data()

    print()
    print(
        f"Observed samples: {len(df)}"
    )

    (
        _,
        X_test,
        y_test,
        test_df,
    ) = create_grouped_split(df)

    model = joblib.load(
        MODEL_FILE
    )

    analysis = analyze_predictions(
        model,
        X_test,
        y_test,
        test_df,
    )

    print_overall_metrics(
        analysis
    )

    importance = (
        get_feature_importance(
            model,
        )
    )

    print()
    print("=" * 80)
    print("FEATURE IMPORTANCE")
    print("=" * 80)

    print(
        f"{'Feature':35}"
        f"{'Importance':>15}"
    )

    print("-" * 52)

    for _, row in importance.iterrows():

        print(
            f"{row['feature']:35}"
            f"{row['importance']:15.6f}"
        )

    print_eta_range_analysis(
        analysis
    )

    print_scenario_analysis(
        analysis
    )

    print_junction_analysis(
        analysis
    )

    print_worst_predictions(
        analysis
    )

    save_analysis(
        analysis
    )

    print()
    print("=" * 80)
    print("ML ERROR ANALYSIS COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()