from __future__ import annotations

import csv
import os
import sys


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

DATASET_FILE = os.path.join(
    PROJECT_ROOT,
    "data",
    "traffic_dataset.csv",
)


REQUIRED_COLUMNS = [
    "simulation_time",
    "ambulance_id",
    "ambulance_edge",
    "ambulance_speed_mps",
    "ambulance_speed_kmh",
    "junction_id",
    "incoming_edge",
    "outgoing_edge",
    "distance_to_junction_m",
    "ambulance_eta_s",
    "vehicle_count",
    "halted_vehicle_count",
    "mean_speed_kmh",
    "occupancy_percent",
    "signal_phase",
    "signal_state",
    "signal_time_to_switch_s",
]


def validate_file() -> bool:
    """Validate that the dataset exists and is structurally usable."""

    print("=" * 80)
    print("DATASET STRUCTURE TEST")
    print("=" * 80)

    if not os.path.exists(DATASET_FILE):
        print(
            f"ERROR: Dataset not found:\n"
            f"{DATASET_FILE}"
        )
        return False

    with open(
        DATASET_FILE,
        "r",
        newline="",
        encoding="utf-8",
    ) as csv_file:

        reader = csv.DictReader(csv_file)

        columns = reader.fieldnames or []

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in columns
        ]

        if missing_columns:

            print("ERROR: Missing required columns:")

            for column in missing_columns:
                print(f"  - {column}")

            return False

        rows = list(reader)

    if not rows:
        print(
            "ERROR: Dataset contains no observations."
        )
        return False

    print(
        f"PASS: Dataset exists."
    )

    print(
        f"PASS: {len(rows)} observations found."
    )

    print(
        f"PASS: {len(columns)} columns found."
    )

    print(
        "PASS: All required columns are present."
    )

    return True


def main() -> None:
    """Run dataset validation and analysis."""

    print("Starting dataset analysis test...")
    print()

    if not validate_file():
        sys.exit(1)

    print()

    from dataset_analyzer import analyze_dataset

    analyze_dataset()

    print()
    print("=" * 80)
    print("DATASET ANALYSIS TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()