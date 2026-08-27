from pathlib import Path

import traci

from route_manager import get_route_state, format_route_state


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

    print("Starting route management test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            state = get_route_state()

            if state is not None:
                print(
                    f"Simulation time: "
                    f"{traci.simulation.getTime():.1f}s"
                )
                print(format_route_state(state))
                print("-" * 60)

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print("Route management test completed.")


if __name__ == "__main__":
    main()