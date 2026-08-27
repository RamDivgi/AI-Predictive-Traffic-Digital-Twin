from pathlib import Path

import traci

from junction_detector import get_upcoming_junctions
from predictive_eta import calculate_junction_etas
from preemption_decision import (
    decide_traffic_aware_preemption,
    format_decision,
)
from traffic_features import (
    build_traffic_features,
    format_traffic_features,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = (
    PROJECT_ROOT
    / "simulation"
    / "config"
    / "test.sumocfg"
)


def main() -> None:
    if not SUMO_CONFIG.exists():
        raise FileNotFoundError(
            f"SUMO configuration not found: {SUMO_CONFIG}"
        )

    sumo_command = [
        "sumo-gui",
        "-c",
        str(SUMO_CONFIG),
        "--delay",
        "200",
    ]

    print("Starting traffic-aware preemption test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()
    print(
        "NOTE: This test does NOT modify traffic signals."
    )
    print()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            if "ambulance" not in traci.vehicle.getIDList():
                continue

            current_time = traci.simulation.getTime()

            current_edge = traci.vehicle.getRoadID(
                "ambulance"
            )

            print(
                f"Simulation time: "
                f"{current_time:.1f}s | "
                f"Ambulance edge: "
                f"{current_edge}"
            )

            junctions = get_upcoming_junctions(
                max_junctions=3
            )

            etas = calculate_junction_etas(
                max_junctions=3
            )

            if not junctions or not etas:
                print(
                    "No upcoming junction data available."
                )
                print("-" * 100)
                continue

            for junction, eta in zip(
                junctions,
                etas,
            ):
                features = build_traffic_features(
                    junction,
                    eta,
                )

                decision = (
                    decide_traffic_aware_preemption(
                        features
                    )
                )

                print(
                    "  "
                    + format_traffic_features(
                        features
                    )
                )

                print(
                    "  "
                    + format_decision(
                        decision
                    )
                )

            print("-" * 100)

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print(
        "Traffic-aware preemption test completed."
    )


if __name__ == "__main__":
    main()