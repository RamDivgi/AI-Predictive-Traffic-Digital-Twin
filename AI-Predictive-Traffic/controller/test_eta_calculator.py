from pathlib import Path

import traci

from eta_calculator import calculate_eta_to_edge, format_eta_result


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "config" / "test.sumocfg"

TARGET_EDGE = "EH"


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

    print("Starting ETA calculation test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print(f"Target edge: {TARGET_EDGE}")
    print()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            result = calculate_eta_to_edge(TARGET_EDGE)

            if result is not None:
                print(
                    f"Time: {traci.simulation.getTime():5.1f}s | "
                    f"{format_eta_result(result)}"
                )

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print("ETA calculation test completed.")


if __name__ == "__main__":
    main()