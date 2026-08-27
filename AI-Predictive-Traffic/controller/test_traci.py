from pathlib import Path

import traci


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

    print("Starting SUMO through TraCI...")
    print(f"Configuration: {SUMO_CONFIG}")

    traci.start(sumo_command)

    try:
        step = 0

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            vehicle_ids = traci.vehicle.getIDList()

            print(
                f"Step {step:03d} | "
                f"Vehicles in simulation: {list(vehicle_ids)}"
            )

            step += 1

    finally:
        traci.close()

    print("TraCI connection closed.")
    print("Python ↔ TraCI ↔ SUMO test completed successfully.")


if __name__ == "__main__":
    main()