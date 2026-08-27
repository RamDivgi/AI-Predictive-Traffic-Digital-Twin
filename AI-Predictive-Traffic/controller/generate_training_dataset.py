from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = PROJECT_ROOT / "controller"
DATA_DIR = PROJECT_ROOT / "data"

COLLECTOR = CONTROLLER_DIR / "multi_scenario_collector.py"

SOURCE_FILE = DATA_DIR / "traffic_dataset_multiscenario.csv"
OUTPUT_FILE = DATA_DIR / "training_dataset.csv"

RUNS = 25
BASE_SEED = 1001


def run_collection(run_number: int) -> bool:
    print()
    print("=" * 80)
    print(f"DATASET GENERATION RUN {run_number}/{RUNS}")
    print("=" * 80)

    seed = BASE_SEED + run_number - 1

    print(f"SUMO seed: {seed}")
    print(f"Collector: {COLLECTOR}")

    env = os.environ.copy()
    env["SUMO_RANDOM_SEED"] = str(seed)

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(COLLECTOR),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            text=True,
        )

        if result.returncode != 0:
            print(
                f"ERROR: Multi-scenario collection "
                f"failed on run {run_number}."
            )
            return False

        return True

    except Exception as exc:
        print(
            f"ERROR: Run {run_number} failed: {exc}"
        )
        return False


def append_dataset(
    source_file: Path,
    destination_file: Path,
) -> int:
    """
    Append one multi-scenario dataset to the
    combined training dataset.
    """

    if not source_file.exists():
        print(
            f"WARNING: Source dataset not found: "
            f"{source_file}"
        )
        return 0

    with source_file.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as source:
        reader = csv.reader(source)
        rows = list(reader)

    if len(rows) <= 1:
        print(
            "WARNING: Source dataset contains "
            "no observations."
        )
        return 0

    header = rows[0]
    observations = rows[1:]

    if not observations:
        return 0

    destination_exists = (
        destination_file.exists()
        and destination_file.stat().st_size > 0
    )

    with destination_file.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as destination:

        writer = csv.writer(destination)

        if not destination_exists:
            writer.writerow(header)

        writer.writerows(observations)

    return len(observations)


def validate_dataset(
    dataset_file: Path,
) -> tuple[int, int, set[str]]:
    """
    Validate the generated training dataset.

    Returns:
        total_rows,
        column_count,
        scenario_names
    """

    if not dataset_file.exists():
        return 0, 0, set()

    with dataset_file.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as file:

        reader = csv.DictReader(file)
        rows = list(reader)

        scenario_names = {
            row.get("traffic_scenario", "")
            for row in rows
            if row.get("traffic_scenario")
        }

        return (
            len(rows),
            len(reader.fieldnames or []),
            scenario_names,
        )


def main() -> None:
    print("=" * 80)
    print("AI PREDICTIVE TRAFFIC - TRAINING DATA GENERATOR")
    print("=" * 80)

    print()
    print(f"Runs              : {RUNS}")
    print(f"Base seed         : {BASE_SEED}")
    print(f"Collector         : {COLLECTOR}")
    print(f"Source dataset    : {SOURCE_FILE}")
    print(f"Training dataset  : {OUTPUT_FILE}")

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove the old combined dataset.
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

        print()
        print(
            f"Removed previous dataset: "
            f"{OUTPUT_FILE}"
        )

    successful_runs = 0
    failed_runs = 0
    total_observations = 0

    for run_number in range(
        1,
        RUNS + 1,
    ):

        success = run_collection(
            run_number
        )

        if not success:
            failed_runs += 1
            continue

        observations = append_dataset(
            SOURCE_FILE,
            OUTPUT_FILE,
        )

        if observations <= 0:
            print(
                f"WARNING: Run {run_number} "
                f"produced no observations."
            )
            failed_runs += 1
            continue

        successful_runs += 1
        total_observations += observations

        print()
        print(
            f"Run {run_number} completed:"
        )
        print(
            f"  Observations added : "
            f"{observations}"
        )
        print(
            f"  Total observations : "
            f"{total_observations}"
        )

    print()
    print("=" * 80)
    print("TRAINING DATA GENERATION COMPLETED")
    print("=" * 80)

    print(
        f"Successful runs : "
        f"{successful_runs}/{RUNS}"
    )

    print(
        f"Failed runs     : "
        f"{failed_runs}/{RUNS}"
    )

    print(
        f"Total rows      : "
        f"{total_observations}"
    )

    print(
        f"Output file     : "
        f"{OUTPUT_FILE}"
    )

    if total_observations == 0:
        print()
        print(
            "ERROR: No training observations "
            "were generated."
        )
        sys.exit(1)

    # Final validation.
    rows, columns, scenarios = validate_dataset(
        OUTPUT_FILE
    )

    print()
    print("=" * 80)
    print("FINAL DATASET VALIDATION")
    print("=" * 80)

    print(
        f"Rows             : {rows}"
    )

    print(
        f"Columns          : {columns}"
    )

    print(
        f"Scenarios found  : {len(scenarios)}"
    )

    print(
        f"Scenario names   : "
        f"{', '.join(sorted(scenarios))}"
    )

    expected_scenarios = {
        "low",
        "normal",
        "moderate",
        "heavy",
        "congested",
    }

    missing_scenarios = (
        expected_scenarios - scenarios
    )

    if missing_scenarios:
        print()
        print(
            "WARNING: Missing traffic scenarios:"
        )

        for scenario in sorted(
            missing_scenarios
        ):
            print(
                f"  - {scenario}"
            )
    else:
        print()
        print(
            "PASS: All five traffic scenarios "
            "are present."
        )

    print()
    print(
        "Training dataset generation finished."
    )


if __name__ == "__main__":
    main()