from pathlib import Path

import traci

from junction_detector import get_upcoming_junctions
from predictive_eta import calculate_junction_etas
from preemption_policy import decide_preemption
from signal_controller import SignalController


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_CONFIG = PROJECT_ROOT / "simulation" / "config" / "test.sumocfg"


def get_signal_indices_for_movement(
    junction_id: str,
    incoming_edge: str,
    outgoing_edge: str,
) -> list[int]:
    """
    Find the SUMO traffic-light signal indices controlling
    the specified incoming-edge to outgoing-edge movement.
    """

    if junction_id not in traci.trafficlight.getIDList():
        return []

    controlled_links = traci.trafficlight.getControlledLinks(
        junction_id
    )

    matching_indices: list[int] = []

    for signal_index, connections in enumerate(
        controlled_links
    ):
        if not connections:
            continue

        for connection in connections:
            if len(connection) < 2:
                continue

            incoming_lane = connection[0]
            outgoing_lane = connection[1]

            incoming_edge_id = incoming_lane.rsplit(
                "_",
                1,
            )[0]

            outgoing_edge_id = outgoing_lane.rsplit(
                "_",
                1,
            )[0]

            if (
                incoming_edge_id == incoming_edge
                and outgoing_edge_id == outgoing_edge
            ):
                if signal_index not in matching_indices:
                    matching_indices.append(
                        signal_index
                    )

    return matching_indices


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

    print("Starting signal preemption lifecycle test...")
    print(f"Configuration: {SUMO_CONFIG}")
    print()

    signal_controller = SignalController()

    traci.start(sumo_command)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            vehicle_ids = traci.vehicle.getIDList()

            if "ambulance" not in vehicle_ids:
                continue

            current_time = traci.simulation.getTime()
            current_edge = traci.vehicle.getRoadID(
                "ambulance"
            )

            junctions = get_upcoming_junctions(
                max_junctions=3
            )

            etas = calculate_junction_etas(
                max_junctions=3
            )

            print(
                f"Time: {current_time:5.1f}s | "
                f"Ambulance edge: {current_edge}"
            )

            # --------------------------------------------------
            # 1. Restore junctions that the ambulance has cleared
            # --------------------------------------------------

            active_junctions = (
                signal_controller.get_active_preemptions()
            )

            for junction_id in active_junctions:
                record_junction = next(
                    (
                        junction
                        for junction in junctions
                        if junction.junction_id == junction_id
                    ),
                    None,
                )

                if record_junction is None:
                    # The junction is no longer among the
                    # upcoming junctions. Check whether the
                    # ambulance has physically cleared it.
                    #
                    # We use the stored snapshot's junction
                    # state indirectly through the active
                    # junction's incoming edge from the
                    # currently known route.
                    restored = False

                    if current_edge.startswith(":"):
                        continue

                    # Determine whether this junction belongs
                    # to the route edge immediately behind the
                    # ambulance.
                    route = list(
                        traci.vehicle.getRoute(
                            "ambulance"
                        )
                    )

                    route_index = (
                        traci.vehicle.getRouteIndex(
                            "ambulance"
                        )
                    )

                    if route_index > 0:
                        previous_edge = route[
                            route_index - 1
                        ]

                        restored = (
                            signal_controller.release_if_cleared(
                                junction_id,
                                previous_edge,
                            )
                        )

                    if restored:
                        print(
                            f"  <<< SIGNAL RESTORED at "
                            f"Junction {junction_id}"
                        )

            # --------------------------------------------------
            # 2. Evaluate upcoming junctions
            # --------------------------------------------------

            for junction, eta in zip(
                junctions,
                etas,
            ):
                signal_indices = (
                    get_signal_indices_for_movement(
                        junction.junction_id,
                        junction.incoming_edge,
                        junction.outgoing_edge,
                    )
                )

                current_signal_state = (
                    traci.trafficlight.getRedYellowGreenState(
                        junction.junction_id
                    )
                    if junction.junction_id
                    in traci.trafficlight.getIDList()
                    else ""
                )

                decision = decide_preemption(
                    distance_m=eta.distance_m,
                    eta_seconds=eta.estimated_travel_seconds,
                    current_signal_state=current_signal_state,
                    required_signal_indices=signal_indices,
                )

                print(
                    f"  Junction {junction.junction_id} | "
                    f"Distance: {eta.distance_m:.1f} m | "
                    f"ETA: {eta.estimated_travel_seconds:.1f} s | "
                    f"Signal indices: {signal_indices} | "
                    f"Preempt: {decision.should_preempt}"
                )

                if (
                    decision.should_preempt
                    and not signal_controller.is_preempted(
                        junction.junction_id
                    )
                ):
                    success = (
                        signal_controller.preempt(
                            junction_id=(
                                junction.junction_id
                            ),
                            signal_indices=(
                                signal_indices
                            ),
                            hold_seconds=8.0,
                        )
                    )

                    if success:
                        print(
                            f"  >>> PREEMPTION ACTIVATED at "
                            f"Junction "
                            f"{junction.junction_id}"
                        )

            # --------------------------------------------------
            # 3. Print active preemptions
            # --------------------------------------------------

            active = (
                signal_controller.get_active_preemptions()
            )

            if active:
                print(
                    f"  Active preemptions: "
                    f"{', '.join(active)}"
                )

            print("-" * 90)

    finally:
        signal_controller.restore_all()
        traci.close()

    print()
    print("TraCI connection closed.")
    print("Signal preemption lifecycle test completed.")


if __name__ == "__main__":
    main()