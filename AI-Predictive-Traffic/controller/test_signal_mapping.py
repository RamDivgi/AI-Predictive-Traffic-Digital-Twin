from pathlib import Path

import traci

from signal_mapping import (
    format_signal_links,
    get_signal_links,
)
from signal_preemption import (
    create_preemption_plan,
    format_preemption_plan,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "config" / "test.sumocfg"


SIGNAL_IDS = ["B", "C", "E"]

AMBULANCE_MOVEMENTS = [
    ("B", "AB", "BC"),
    ("C", "BC", "CE"),
    ("E", "CE", "EH"),
]


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

    print("Starting signal mapping test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()

    traci.start(sumo_command)

    try:
        print("=" * 80)
        print("TRAFFIC SIGNAL CONTROLLED LINKS")
        print("=" * 80)

        for signal_id in SIGNAL_IDS:
            print()
            print(f"Junction {signal_id}")

            links = get_signal_links(signal_id)

            print(format_signal_links(links))

        print()
        print("=" * 80)
        print("AMBULANCE MOVEMENT MAPPING")
        print("=" * 80)

        for junction_id, incoming_edge, outgoing_edge in AMBULANCE_MOVEMENTS:
            print()

            plan = create_preemption_plan(
                junction_id=junction_id,
                incoming_edge=incoming_edge,
                outgoing_edge=outgoing_edge,
            )

            print(format_preemption_plan(plan))

        print()
        print("=" * 80)
        print("No traffic signals were modified during this test.")
        print("=" * 80)

    finally:
        traci.close()

    print()
    print("TraCI connection closed.")
    print("Signal mapping test completed.")


if __name__ == "__main__":
    main()