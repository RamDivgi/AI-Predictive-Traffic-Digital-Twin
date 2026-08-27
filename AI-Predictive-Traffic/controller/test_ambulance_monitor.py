from pathlib import Path

import traci

from ambulance_monitor import get_ambulance_state, format_ambulance_state


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

    print("Starting ambulance monitoring test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            state = get_ambulance_state()

            if state is not None:
                print(format_ambulance_state(state))
            else:
                print(
                    f"Time: {traci.simulation.getTime():6.1f}s | "
                    "Ambulance not currently in simulation"
                )

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print("Ambulance monitoring test completed.")


if __name__ == "__main__":
    main()