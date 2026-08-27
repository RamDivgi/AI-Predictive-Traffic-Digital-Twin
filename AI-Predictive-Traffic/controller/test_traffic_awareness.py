from pathlib import Path

import traci

from signal_monitor import (
    format_signal_states,
    get_signal_states,
)
from traffic_monitor import (
    format_traffic,
    get_upcoming_traffic,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "config" / "test.sumocfg"


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

    print("Starting traffic-awareness test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            if "ambulance" not in traci.vehicle.getIDList():
                continue

            traffic = get_upcoming_traffic(max_edges=3)

            junction_ids = ["B", "C", "E"]
            signals = get_signal_states(junction_ids)

            print(
                f"Simulation time: "
                f"{traci.simulation.getTime():.1f}s"
            )

            print("\nTraffic:")
            print(format_traffic(traffic))

            print("\nSignals:")
            print(format_signal_states(signals))

            print("-" * 80)

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print("Traffic-awareness test completed.")


if __name__ == "__main__":
    main()