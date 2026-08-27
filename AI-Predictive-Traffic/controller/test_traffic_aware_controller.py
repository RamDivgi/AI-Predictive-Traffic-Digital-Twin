from __future__ import annotations

import os
import sys
from pathlib import Path

import traci


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = PROJECT_ROOT / "controller"

if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))

from traffic_aware_controller import TrafficAwareController


SUMO_CONFIG = (
    PROJECT_ROOT
    / "simulation"
    / "config"
    / "test.sumocfg"
)


def main() -> None:
    print("=" * 80)
    print("AI PREDICTIVE TRAFFIC - END-TO-END CONTROLLER TEST")
    print("=" * 80)

    controller = TrafficAwareController()

    command = [
        "sumo",
        "-c",
        str(SUMO_CONFIG),
        "--start",
        "--quit-on-end",
    ]

    print()
    print(f"Configuration: {SUMO_CONFIG}")
    print("Starting SUMO...")

    try:
        traci.start(command)

        while (
            traci.simulation.getMinExpectedNumber()
            > 0
        ):
            traci.simulationStep()

            simulation_time = (
                traci.simulation.getTime()
            )

            print()
            print(
                f"Simulation time: "
                f"{simulation_time:.1f}s"
            )

            results = controller.process_step()

            if not results:
                print(
                    "No upcoming junction decisions."
                )

        print()
        print("=" * 80)
        print("END-TO-END TEST COMPLETED")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\nTest interrupted.")

    finally:
        try:
            controller.shutdown()
        except Exception as exc:
            print(
                f"Controller shutdown warning: {exc}"
            )

        try:
            traci.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()