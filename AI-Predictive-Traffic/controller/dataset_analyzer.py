from __future__ import annotations

import csv
import os
import statistics
from collections import Counter
from typing import Dict, List


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

DATASET_FILE = os.path.join(
    PROJECT_ROOT,
    "data",
    "traffic_dataset.csv",
)


NUMERIC_COLUMNS = [
    "simulation_time",
    "ambulance_speed_mps",
    "ambulance_speed_kmh",
    "distance_to_junction_m",
    "ambulance_eta_s",
    "vehicle_count",
    "halted_vehicle_count",
    "mean_speed_kmh",
    "occupancy_percent",
    "signal_phase",
    "signal_time_to_switch_s",
]


def load_dataset() -> List[Dict[str, str]]:
    """Load the generated CSV dataset."""

    if not os.path.exists(DATASET_FILE):
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_FILE}"
        )

    with open(
        DATASET_FILE,
        "r",
        newline="",
        encoding="utf-8",
    ) as csv_file:
        reader = csv.DictReader(csv_file)
        return list(reader)


def print_basic_statistics(
    rows: List[Dict[str, str]]
) -> None:
    """Print basic dataset information."""

    print()
    print("=" * 80)
    print("BASIC DATASET INFORMATION")
    print("=" * 80)

    print(f"Dataset file : {DATASET_FILE}")
    print(f"Observations : {len(rows)}")

    if rows:
        print(
            f"Columns      : {len(rows[0])}"
        )


def check_missing_values(
    rows: List[Dict[str, str]]
) -> None:
    """Check missing values in every column."""

    print()
    print("=" * 80)
    print("MISSING VALUE CHECK")
    print("=" * 80)

    if not rows:
        print("Dataset is empty.")
        return

    columns = rows[0].keys()

    total_missing = 0

    for column in columns:

        missing = sum(
            1
            for row in rows
            if row.get(column, "").strip() == ""
        )

        total_missing += missing

        status = "OK" if missing == 0 else "MISSING"

        print(
            f"{column:30} | "
            f"{missing:5} missing | "
            f"{status}"
        )

    print()
    print(
        f"Total missing values: {total_missing}"
    )


def check_numeric_values(
    rows: List[Dict[str, str]]
) -> None:
    """Check whether numeric columns contain valid values."""

    print()
    print("=" * 80)
    print("NUMERIC DATA VALIDATION")
    print("=" * 80)

    total_invalid = 0

    for column in NUMERIC_COLUMNS:

        invalid = 0

        for row in rows:

            value = row.get(column, "").strip()

            if not value:
                continue

            try:
                float(value)
            except ValueError:
                invalid += 1

        total_invalid += invalid

        status = "OK" if invalid == 0 else "INVALID"

        print(
            f"{column:30} | "
            f"{invalid:5} invalid | "
            f"{status}"
        )

    print()
    print(
        f"Total invalid numeric values: "
        f"{total_invalid}"
    )


def print_numeric_ranges(
    rows: List[Dict[str, str]]
) -> None:
    """Print min, max, mean and standard deviation."""

    print()
    print("=" * 80)
    print("FEATURE RANGES")
    print("=" * 80)

    for column in NUMERIC_COLUMNS:

        values = []

        for row in rows:

            value = row.get(column, "").strip()

            if not value:
                continue

            try:
                values.append(float(value))
            except ValueError:
                continue

        if not values:
            print(
                f"{column:30} | No numeric data"
            )
            continue

        mean_value = statistics.mean(values)

        if len(values) > 1:
            std_value = statistics.stdev(values)
        else:
            std_value = 0.0

        print(
            f"{column:30} | "
            f"Min: {min(values):10.2f} | "
            f"Max: {max(values):10.2f} | "
            f"Mean: {mean_value:10.2f} | "
            f"Std: {std_value:10.2f}"
        )


def print_junction_distribution(
    rows: List[Dict[str, str]]
) -> None:
    """Show how observations are distributed across junctions."""

    print()
    print("=" * 80)
    print("JUNCTION DISTRIBUTION")
    print("=" * 80)

    junction_counts = Counter(
        row.get("junction_id", "")
        for row in rows
    )

    if not junction_counts:
        print("No junction data found.")
        return

    for junction, count in sorted(
        junction_counts.items()
    ):
        print(
            f"Junction {junction:10} | "
            f"Observations: {count}"
        )


def print_movement_distribution(
    rows: List[Dict[str, str]]
) -> None:
    """Show ambulance movements represented in the dataset."""

    print()
    print("=" * 80)
    print("ROUTE MOVEMENT DISTRIBUTION")
    print("=" * 80)

    movements = Counter(
        (
            row.get("incoming_edge", ""),
            row.get("outgoing_edge", ""),
        )
        for row in rows
    )

    for (
        incoming,
        outgoing,
    ), count in sorted(movements.items()):

        print(
            f"{incoming} -> {outgoing:5} | "
            f"Observations: {count}"
        )


def check_feature_variation(
    rows: List[Dict[str, str]]
) -> None:
    """
    Check whether important features actually vary.

    A feature with only one unique value provides little
    information for a predictive ML model.
    """

    print()
    print("=" * 80)
    print("FEATURE VARIATION CHECK")
    print("=" * 80)

    important_columns = [
        "ambulance_speed_kmh",
        "distance_to_junction_m",
        "ambulance_eta_s",
        "vehicle_count",
        "halted_vehicle_count",
        "mean_speed_kmh",
        "occupancy_percent",
        "signal_phase",
        "signal_time_to_switch_s",
    ]

    for column in important_columns:

        values = set()

        for row in rows:

            value = row.get(column, "").strip()

            if value:
                values.add(value)

        unique_count = len(values)

        if unique_count <= 1:
            status = "LOW VARIATION"
        elif unique_count < 5:
            status = "LIMITED"
        else:
            status = "GOOD"

        print(
            f"{column:30} | "
            f"Unique values: {unique_count:5} | "
            f"{status}"
        )


def analyze_dataset() -> None:
    """Run the complete dataset analysis."""

    print("Starting dataset analysis...")

    try:
        rows = load_dataset()
    except FileNotFoundError as exc:
        print()
        print(f"ERROR: {exc}")
        return

    if not rows:
        print()
        print("ERROR: Dataset contains zero rows.")
        return

    print_basic_statistics(rows)

    check_missing_values(rows)

    check_numeric_values(rows)

    print_numeric_ranges(rows)

    print_junction_distribution(rows)

    print_movement_distribution(rows)

    check_feature_variation(rows)

    print()
    print("=" * 80)
    print("DATASET ANALYSIS COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    analyze_dataset()