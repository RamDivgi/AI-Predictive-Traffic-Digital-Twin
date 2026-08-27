from __future__ import annotations

import csv
import os
import sys
from typing import Any, Dict, List, Optional

import traci

from dataset_schema import TrafficObservation


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

SUMO_CONFIG = os.path.join(
    PROJECT_ROOT,
    "simulation",
    "config",
    "test.sumocfg",
)

OUTPUT_FILE = os.path.join(
    PROJECT_ROOT,
    "data",
    "traffic_dataset.csv",
)

AMBULANCE_ID = "ambulance"
MAX_JUNCTIONS = 3


def get_traffic_data(edge_id: str) -> Dict[str, Any]:
    """
    Collect traffic information for a road edge.
    """

    try:
        vehicle_ids = traci.edge.getLastStepVehicleIDs(
            edge_id
        )

        vehicle_count = len(vehicle_ids)

        halted_vehicle_count = sum(
            1
            for vehicle_id in vehicle_ids
            if traci.vehicle.getSpeed(vehicle_id) < 0.1
        )

        mean_speed = traci.edge.getLastStepMeanSpeed(
            edge_id
        )

        occupancy = traci.edge.getLastStepOccupancy(
            edge_id
        )

        if mean_speed < 0:
            mean_speed = 0.0

        if occupancy < 0:
            occupancy = 0.0

        return {
            "vehicle_count": vehicle_count,
            "halted_vehicle_count": halted_vehicle_count,
            "mean_speed_kmh": mean_speed * 3.6,
            "occupancy_percent": occupancy,
        }

    except traci.TraCIException:
        return {
            "vehicle_count": 0,
            "halted_vehicle_count": 0,
            "mean_speed_kmh": 0.0,
            "occupancy_percent": 0.0,
        }


def get_signal_data(
    junction_id: str,
    signal_index: int,
) -> Dict[str, Any]:
    """
    Collect traffic signal information for a junction.
    """

    try:
        signal_ids = traci.trafficlight.getIDList()

        if junction_id not in signal_ids:
            return {
                "signal_phase": -1,
                "signal_state": "",
                "signal_time_to_switch_s": 0.0,
            }

        signal_phase = traci.trafficlight.getPhase(
            junction_id
        )

        signal_state = (
            traci.trafficlight.getRedYellowGreenState(
                junction_id
            )
        )

        next_switch = traci.trafficlight.getNextSwitch(
            junction_id
        )

        current_time = traci.simulation.getTime()

        time_to_switch = max(
            0.0,
            next_switch - current_time,
        )

        return {
            "signal_phase": signal_phase,
            "signal_state": signal_state,
            "signal_time_to_switch_s": time_to_switch,
        }

    except traci.TraCIException:
        return {
            "signal_phase": -1,
            "signal_state": "",
            "signal_time_to_switch_s": 0.0,
        }


def get_route_edges() -> List[str]:
    """
    Return the ambulance's complete route.
    """

    try:
        return list(
            traci.vehicle.getRoute(AMBULANCE_ID)
        )
    except traci.TraCIException:
        return []


def get_current_route_index() -> int:
    """
    Return the ambulance's current route index.
    """

    try:
        return traci.vehicle.getRouteIndex(
            AMBULANCE_ID
        )
    except traci.TraCIException:
        return -1


def get_movement_for_tls(
    tls_id: str,
    tls_index: int,
    route_edges: List[str],
    current_route_index: int,
) -> Optional[Dict[str, str]]:
    """
    Determine the incoming and outgoing route edges controlled
    by a specific traffic-light signal index.

    SUMO returns controlled links as lane-to-lane connections.
    We convert the lane IDs into edge IDs and match them against
    the ambulance's route.
    """

    try:
        controlled_links = (
            traci.trafficlight.getControlledLinks(
                tls_id
            )
        )

        if tls_index < 0:
            return None

        if tls_index >= len(controlled_links):
            return None

        links = controlled_links[tls_index]

        if not links:
            return None

        for link in links:

            if not link:
                continue

            incoming_lane = link[0]
            outgoing_lane = link[1]

            incoming_edge = traci.lane.getEdgeID(
                incoming_lane
            )

            outgoing_edge = traci.lane.getEdgeID(
                outgoing_lane
            )

            if incoming_edge not in route_edges:
                continue

            if outgoing_edge not in route_edges:
                continue

            incoming_index = route_edges.index(
                incoming_edge
            )

            if incoming_index < current_route_index:
                continue

            if (
                incoming_index + 1 < len(route_edges)
                and route_edges[incoming_index + 1]
                == outgoing_edge
            ):
                return {
                    "incoming_edge": incoming_edge,
                    "outgoing_edge": outgoing_edge,
                }

        return None

    except traci.TraCIException:
        return None


def get_upcoming_junctions() -> List[Dict[str, Any]]:
    """
    Find upcoming signalized junctions using SUMO's
    vehicle.getNextTLS() API.

    This avoids relying on unavailable EdgeDomain methods
    such as getToNode().
    """

    if AMBULANCE_ID not in traci.vehicle.getIDList():
        return []

    route_edges = get_route_edges()

    current_route_index = get_current_route_index()

    if not route_edges or current_route_index < 0:
        return []

    try:
        upcoming_tls = traci.vehicle.getNextTLS(
            AMBULANCE_ID
        )
    except traci.TraCIException:
        return []

    junctions: List[Dict[str, Any]] = []

    for tls_id, tls_index, distance, _state in upcoming_tls:

        movement = get_movement_for_tls(
            tls_id=tls_id,
            tls_index=tls_index,
            route_edges=route_edges,
            current_route_index=current_route_index,
        )

        if movement is None:
            continue

        junctions.append(
            {
                "junction_id": tls_id,
                "incoming_edge": movement[
                    "incoming_edge"
                ],
                "outgoing_edge": movement[
                    "outgoing_edge"
                ],
                "distance_to_junction_m": max(
                    0.0,
                    float(distance),
                ),
                "signal_index": tls_index,
            }
        )

        if len(junctions) >= MAX_JUNCTIONS:
            break

    return junctions


def calculate_eta(
    distance_m: float,
    speed_mps: float,
) -> float:
    """
    Calculate instantaneous ETA.
    """

    minimum_speed = 0.1

    effective_speed = max(
        speed_mps,
        minimum_speed,
    )

    return distance_m / effective_speed


def collect_observation() -> List[TrafficObservation]:
    """
    Collect observations for all upcoming signalized
    junctions on the ambulance route.
    """

    if AMBULANCE_ID not in traci.vehicle.getIDList():
        return []

    simulation_time = traci.simulation.getTime()

    ambulance_edge = traci.vehicle.getRoadID(
        AMBULANCE_ID
    )

    ambulance_speed_mps = traci.vehicle.getSpeed(
        AMBULANCE_ID
    )

    ambulance_speed_kmh = (
        ambulance_speed_mps * 3.6
    )

    upcoming_junctions = get_upcoming_junctions()

    observations: List[TrafficObservation] = []

    for junction in upcoming_junctions:

        junction_id = junction["junction_id"]

        incoming_edge = junction["incoming_edge"]

        outgoing_edge = junction["outgoing_edge"]

        distance = junction[
            "distance_to_junction_m"
        ]

        eta = calculate_eta(
            distance,
            ambulance_speed_mps,
        )

        traffic = get_traffic_data(
            incoming_edge
        )

        signal = get_signal_data(
            junction_id,
            junction["signal_index"],
        )

        observation = TrafficObservation(
            simulation_time=simulation_time,
            ambulance_id=AMBULANCE_ID,
            ambulance_edge=ambulance_edge,
            ambulance_speed_mps=ambulance_speed_mps,
            ambulance_speed_kmh=ambulance_speed_kmh,
            junction_id=junction_id,
            incoming_edge=incoming_edge,
            outgoing_edge=outgoing_edge,
            distance_to_junction_m=distance,
            ambulance_eta_s=eta,
            vehicle_count=traffic[
                "vehicle_count"
            ],
            halted_vehicle_count=traffic[
                "halted_vehicle_count"
            ],
            mean_speed_kmh=traffic[
                "mean_speed_kmh"
            ],
            occupancy_percent=traffic[
                "occupancy_percent"
            ],
            signal_phase=signal[
                "signal_phase"
            ],
            signal_state=signal[
                "signal_state"
            ],
            signal_time_to_switch_s=signal[
                "signal_time_to_switch_s"
            ],
        )

        observations.append(
            observation
        )

    return observations


def write_dataset(
    observations: List[TrafficObservation],
) -> None:
    """
    Append observations to the CSV file.
    """

    os.makedirs(
        os.path.dirname(OUTPUT_FILE),
        exist_ok=True,
    )

    file_exists = os.path.exists(
        OUTPUT_FILE
    )

    with open(
        OUTPUT_FILE,
        "a",
        newline="",
        encoding="utf-8",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=TrafficObservation.csv_headers(),
        )

        if not file_exists:
            writer.writeheader()

        for observation in observations:
            writer.writerow(
                observation.to_dict()
            )


def start_simulation() -> None:
    """
    Start SUMO through TraCI.
    """

    sumo_command = [
        "sumo",
        "-c",
        SUMO_CONFIG,
        "--start",
        "--quit-on-end",
    ]

    traci.start(
        sumo_command
    )


def collect_dataset() -> None:
    """
    Run SUMO and collect traffic observations.
    """

    print(
        "Starting traffic dataset collection..."
    )

    print(
        f"Configuration: {SUMO_CONFIG}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print()

    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    start_simulation()

    observation_count = 0

    try:

        while (
            traci.simulation.getMinExpectedNumber()
            > 0
        ):

            traci.simulationStep()

            observations = (
                collect_observation()
            )

            if observations:

                write_dataset(
                    observations
                )

                observation_count += len(
                    observations
                )

                print(
                    f"Time: "
                    f"{traci.simulation.getTime():6.1f}s | "
                    f"Observations: "
                    f"{len(observations)} | "
                    f"Total: "
                    f"{observation_count}"
                )

    finally:

        traci.close()

    print()

    print(
        "Dataset collection completed. "
        f"Total observations: "
        f"{observation_count}"
    )

    print(
        f"Dataset saved to: {OUTPUT_FILE}"
    )


if __name__ == "__main__":

    try:

        collect_dataset()

    except KeyboardInterrupt:

        print(
            "\nDataset collection interrupted."
        )

        try:
            traci.close()
        except Exception:
            pass

    except Exception as exc:

        print(
            "\nDataset collection failed."
        )

        print(
            f"Error: {exc}"
        )

        sys.exit(1)