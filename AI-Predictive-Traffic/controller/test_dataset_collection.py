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


EXPECTED_COLUMNS = [
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


def validate_dataset() -> bool:
    """
    Validate the generated traffic dataset.
    """

    print()
    print("=" * 80)
    print("DATASET VALIDATION")
    print("=" * 80)

    if not os.path.exists(DATASET_FILE):
        print("ERROR: Dataset file was not created.")
        print(f"Expected: {DATASET_FILE}")
        return False

    print(f"Dataset file: {DATASET_FILE}")

    with open(
        DATASET_FILE,
        "r",
        newline="",
        encoding="utf-8",
    ) as csv_file:

        reader = csv.DictReader(csv_file)

        actual_columns = reader.fieldnames or []

        print()
        print("Checking columns...")

        missing_columns = [
            column
            for column in EXPECTED_COLUMNS
            if column not in actual_columns
        ]

        if missing_columns:
            print("ERROR: Missing columns:")

            for column in missing_columns:
                print(f"  - {column}")

            return False

        print(
            f"PASS: All {len(EXPECTED_COLUMNS)} "
            "expected columns are present."
        )

        rows = list(reader)

    print()
    print(f"Total observations: {len(rows)}")

    if not rows:
        print("ERROR: Dataset contains no observations.")
        return False

    print("PASS: Dataset contains observations.")

    print()
    print("Sample observations:")
    print("-" * 80)

    for index, row in enumerate(rows[:5], start=1):

        print(
            f"{index}. "
            f"Time={row['simulation_time']}s | "
            f"Junction={row['junction_id']} | "
            f"Movement="
            f"{row['incoming_edge']} -> "
            f"{row['outgoing_edge']} | "
            f"Distance="
            f"{row['distance_to_junction_m']}m | "
            f"ETA="
            f"{row['ambulance_eta_s']}s | "
            f"Vehicles="
            f"{row['vehicle_count']} | "
            f"Halted="
            f"{row['halted_vehicle_count']}"
        )

    print("-" * 80)

    print()
    print("Dataset validation successful.")

    return True


def main() -> None:
    """
    Run dataset validation.
    """

    print("Starting dataset collection test...")
    print()

    # Import here so validation can still be used independently.
    from dataset_collector import collect_dataset

    try:
        collect_dataset()

    except Exception as exc:
        print()
        print("Dataset collection failed.")
        print(f"Error: {exc}")
        sys.exit(1)

    if not validate_dataset():
        sys.exit(1)

    print()
    print("=" * 80)
    print("DATASET COLLECTION TEST PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()