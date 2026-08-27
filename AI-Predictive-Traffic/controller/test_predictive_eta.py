from pathlib import Path

import traci

from predictive_eta import calculate_junction_etas, format_junction_etas


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

    print("Starting junction-based predictive ETA test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            etas = calculate_junction_etas(max_junctions=3)

            if etas:
                print(
                    f"Simulation time: "
                    f"{traci.simulation.getTime():.1f}s"
                )
                print(format_junction_etas(etas))
                print("-" * 70)

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print("Junction-based predictive ETA test completed.")


if __name__ == "__main__":
    main()