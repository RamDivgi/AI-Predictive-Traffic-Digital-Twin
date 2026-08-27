from __future__ import annotations

import csv
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

import traci

from dataset_schema import TrafficObservation
from scenario_generator import (
    TrafficScenario,
    get_scenarios,
)


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

BASE_ROUTE_FILE = os.path.join(
    PROJECT_ROOT,
    "simulation",
    "routes",
    "test.rou.xml",
)

OUTPUT_FILE = os.path.join(
    PROJECT_ROOT,
    "data",
    "traffic_dataset_multiscenario.csv",
)

AMBULANCE_ID = "ambulance"

SUMO_CONFIG = os.path.join(
    PROJECT_ROOT,
    "simulation",
    "config",
    "test.sumocfg",
)


def load_route_file() -> ET.ElementTree:
    """
    Load the existing SUMO route file.
    """

    if not os.path.exists(BASE_ROUTE_FILE):
        raise FileNotFoundError(
            f"Route file not found: {BASE_ROUTE_FILE}"
        )

    return ET.parse(BASE_ROUTE_FILE)


def prepare_scenario_route_file(
    scenario: TrafficScenario,
    output_path: str,
) -> None:
    """
    Create a temporary SUMO route file for a traffic scenario.

    All generated vehicles and the ambulance are sorted by
    departure time so SUMO does not ignore vehicles.
    """

    tree = load_route_file()
    root = tree.getroot()

    original_vehicles = list(
        root.findall("vehicle")
    )

    ambulance_vehicle = None
    traffic_templates = []

    for vehicle in original_vehicles:

        vehicle_id = vehicle.get("id", "")

        if vehicle_id == AMBULANCE_ID:
            ambulance_vehicle = vehicle
        else:
            traffic_templates.append(vehicle)

    if ambulance_vehicle is None:
        raise RuntimeError(
            "Ambulance vehicle was not found in "
            f"{BASE_ROUTE_FILE}"
        )

    if not traffic_templates:
        raise RuntimeError(
            "No non-ambulance vehicles were found "
            "to use as traffic templates."
        )

    # Remove all original vehicles.
    for vehicle in original_vehicles:
        root.remove(vehicle)

    generated_vehicles = []

    # Create scenario traffic vehicles.
    for index in range(
        scenario.vehicle_count
    ):

        template = traffic_templates[
            index % len(traffic_templates)
        ]

        vehicle = ET.fromstring(
            ET.tostring(
                template,
                encoding="unicode",
            )
        )

        vehicle.set(
            "id",
            f"{scenario.name}_vehicle_{index + 1}",
        )

        departure_time = (
            index
            * scenario.departure_spacing
        )

        vehicle.set(
            "depart",
            f"{departure_time:.2f}",
        )

        vehicle.set(
            "departSpeed",
            "max",
        )

        vehicle.set(
            "departPos",
            "base",
        )

        vtype_id = vehicle.get("type")

        if vtype_id:

            for vtype in root.findall("vType"):

                if vtype.get("id") != vtype_id:
                    continue

                original_speed = float(
                    vtype.get(
                        "maxSpeed",
                        "13.89",
                    )
                )

                scenario_speed = max(
                    2.0,
                    original_speed
                    * scenario.speed_factor,
                )

                scenario_vtype_id = (
                    f"{scenario.name}_type"
                )

                existing_scenario_type = None

                for existing_type in root.findall(
                    "vType"
                ):

                    if (
                        existing_type.get("id")
                        == scenario_vtype_id
                    ):
                        existing_scenario_type = (
                            existing_type
                        )
                        break

                if existing_scenario_type is None:

                    scenario_vtype = ET.fromstring(
                        ET.tostring(
                            vtype,
                            encoding="unicode",
                        )
                    )

                    scenario_vtype.set(
                        "id",
                        scenario_vtype_id,
                    )

                    scenario_vtype.set(
                        "maxSpeed",
                        f"{scenario_speed:.3f}",
                    )

                    root.append(
                        scenario_vtype
                    )

                vehicle.set(
                    "type",
                    scenario_vtype_id,
                )

                break

        generated_vehicles.append(vehicle)

    # Add ambulance to the list.
    ambulance_copy = ET.fromstring(
        ET.tostring(
            ambulance_vehicle,
            encoding="unicode",
        )
    )

    generated_vehicles.append(
        ambulance_copy
    )

    # IMPORTANT:
    # SUMO route files must be ordered by departure time.
    def departure_time(vehicle: ET.Element) -> float:
        try:
            return float(
                vehicle.get(
                    "depart",
                    "0",
                )
            )
        except ValueError:
            return 0.0

    generated_vehicles.sort(
        key=departure_time
    )

    # Write vehicles in correct departure order.
    for vehicle in generated_vehicles:
        root.append(vehicle)

    tree.write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )

def get_traffic_data(
    edge_id: str,
) -> Dict[str, float]:
    """
    Collect traffic information from SUMO.
    """

    try:

        vehicle_ids = (
            traci.edge.getLastStepVehicleIDs(
                edge_id
            )
        )

        vehicle_count = len(
            vehicle_ids
        )

        halted_vehicle_count = sum(
            1
            for vehicle_id in vehicle_ids
            if traci.vehicle.getSpeed(
                vehicle_id
            ) < 0.1
        )

        mean_speed = (
            traci.edge.getLastStepMeanSpeed(
                edge_id
            )
        )

        occupancy = (
            traci.edge.getLastStepOccupancy(
                edge_id
            )
        )

        if mean_speed < 0:
            mean_speed = 0.0

        if occupancy < 0:
            occupancy = 0.0

        return {
            "vehicle_count": float(
                vehicle_count
            ),
            "halted_vehicle_count": float(
                halted_vehicle_count
            ),
            "mean_speed_kmh": (
                mean_speed * 3.6
            ),
            "occupancy_percent": occupancy,
        }

    except traci.TraCIException:

        return {
            "vehicle_count": 0.0,
            "halted_vehicle_count": 0.0,
            "mean_speed_kmh": 0.0,
            "occupancy_percent": 0.0,
        }


def get_signal_data(
    junction_id: str,
) -> Dict[str, object]:
    """
    Collect signal information.
    """

    try:

        signal_phase = (
            traci.trafficlight.getPhase(
                junction_id
            )
        )

        signal_state = (
            traci.trafficlight
            .getRedYellowGreenState(
                junction_id
            )
        )

        next_switch = (
            traci.trafficlight.getNextSwitch(
                junction_id
            )
        )

        current_time = (
            traci.simulation.getTime()
        )

        return {
            "signal_phase": signal_phase,
            "signal_state": signal_state,
            "signal_time_to_switch_s": max(
                0.0,
                next_switch - current_time,
            ),
        }

    except traci.TraCIException:

        return {
            "signal_phase": -1,
            "signal_state": "",
            "signal_time_to_switch_s": 0.0,
        }


def get_upcoming_junctions() -> List[dict]:
    """
    Use SUMO's vehicle.getNextTLS() to find upcoming
    signalized junctions.
    """

    if (
        AMBULANCE_ID
        not in traci.vehicle.getIDList()
    ):
        return []

    try:

        upcoming_tls = (
            traci.vehicle.getNextTLS(
                AMBULANCE_ID
            )
        )

    except traci.TraCIException:

        return []

    route = list(
        traci.vehicle.getRoute(
            AMBULANCE_ID
        )
    )

    current_index = (
        traci.vehicle.getRouteIndex(
            AMBULANCE_ID
        )
    )

    if current_index < 0:
        return []

    results = []

    for (
        tls_id,
        tls_index,
        distance,
        _state,
    ) in upcoming_tls:

        try:

            controlled_links = (
                traci.trafficlight
                .getControlledLinks(
                    tls_id
                )
            )

            if (
                tls_index
                >= len(controlled_links)
            ):
                continue

            links = controlled_links[
                tls_index
            ]

            if not links:
                continue

            movement = None

            for link in links:

                if not link:
                    continue

                incoming_lane = link[0]
                outgoing_lane = link[1]

                incoming_edge = (
                    traci.lane.getEdgeID(
                        incoming_lane
                    )
                )

                outgoing_edge = (
                    traci.lane.getEdgeID(
                        outgoing_lane
                    )
                )

                for route_index in range(
                    current_index,
                    len(route) - 1,
                ):

                    if (
                        route[route_index]
                        == incoming_edge
                        and
                        route[
                            route_index + 1
                        ]
                        == outgoing_edge
                    ):

                        movement = (
                            incoming_edge,
                            outgoing_edge,
                        )

                        break

                if movement:
                    break

            if movement is None:
                continue

            results.append(
                {
                    "junction_id": tls_id,
                    "incoming_edge": movement[0],
                    "outgoing_edge": movement[1],
                    "distance_m": max(
                        0.0,
                        float(distance),
                    ),
                }
            )

            if len(results) >= 3:
                break

        except traci.TraCIException:
            continue

    return results


def collect_current_step(
    scenario_name: str,
) -> List[TrafficObservation]:
    """
    Collect all observations for the current SUMO step.
    """

    if (
        AMBULANCE_ID
        not in traci.vehicle.getIDList()
    ):
        return []

    simulation_time = (
        traci.simulation.getTime()
    )

    ambulance_edge = (
        traci.vehicle.getRoadID(
            AMBULANCE_ID
        )
    )

    ambulance_speed_mps = (
        traci.vehicle.getSpeed(
            AMBULANCE_ID
        )
    )

    ambulance_speed_kmh = (
        ambulance_speed_mps * 3.6
    )

    upcoming = (
        get_upcoming_junctions()
    )

    observations = []

    for junction in upcoming:

        distance = junction[
            "distance_m"
        ]

        effective_speed = max(
            ambulance_speed_mps,
            0.1,
        )

        eta = (
            distance
            / effective_speed
        )

        traffic = get_traffic_data(
            junction["incoming_edge"]
        )

        signal = get_signal_data(
            junction["junction_id"]
        )

        observation = (
            TrafficObservation(
                simulation_time=simulation_time,
                ambulance_id=AMBULANCE_ID,
                ambulance_edge=ambulance_edge,
                ambulance_speed_mps=(
                    ambulance_speed_mps
                ),
                ambulance_speed_kmh=(
                    ambulance_speed_kmh
                ),
                junction_id=(
                    junction["junction_id"]
                ),
                incoming_edge=(
                    junction["incoming_edge"]
                ),
                outgoing_edge=(
                    junction["outgoing_edge"]
                ),
                distance_to_junction_m=(
                    distance
                ),
                ambulance_eta_s=eta,
                vehicle_count=int(
                    traffic[
                        "vehicle_count"
                    ]
                ),
                halted_vehicle_count=int(
                    traffic[
                        "halted_vehicle_count"
                    ]
                ),
                mean_speed_kmh=(
                    traffic[
                        "mean_speed_kmh"
                    ]
                ),
                occupancy_percent=(
                    traffic[
                        "occupancy_percent"
                    ]
                ),
                signal_phase=int(
                    signal["signal_phase"]
                ),
                signal_state=str(
                    signal["signal_state"]
                ),
                signal_time_to_switch_s=(
                    float(
                        signal[
                            "signal_time_to_switch_s"
                        ]
                    )
                ),
            )
        )

        observations.append(
            observation
        )

    return observations


def append_observations(
    writer: csv.DictWriter,
    observations: List[TrafficObservation],
    scenario_name: str,
) -> int:
    """
    Write observations to the combined CSV.

    The scenario name is stored as an additional column
    so the training data can be analyzed by traffic condition.
    """

    count = 0

    for observation in observations:

        row = observation.to_dict()

        row["traffic_scenario"] = (
            scenario_name
        )

        writer.writerow(row)

        count += 1

    return count


def run_scenario(
    scenario: TrafficScenario,
    writer: csv.DictWriter,
) -> int:
    """
    Run one SUMO scenario and collect its observations.
    """

    temporary_directory = (
        tempfile.mkdtemp(
            prefix="ai_traffic_"
        )
    )

    route_file = os.path.join(
        temporary_directory,
        f"{scenario.name}.rou.xml",
    )

    print()
    print("=" * 80)
    print(
        f"SCENARIO: {scenario.name.upper()}"
    )
    print("=" * 80)

    print(
        f"Description       : "
        f"{scenario.description}"
    )

    print(
        f"Traffic vehicles  : "
        f"{scenario.vehicle_count}"
    )

    print(
        f"Departure spacing : "
        f"{scenario.departure_spacing}s"
    )

    print(
        f"Speed factor      : "
        f"{scenario.speed_factor}"
    )

    prepare_scenario_route_file(
        scenario,
        route_file,
    )

    observation_count = 0

    try:

        sumo_command = [
            "sumo",
            "-c",
            SUMO_CONFIG,
            "--route-files",
            route_file,
            "--start",
            "--quit-on-end",
        ]

        traci.start(
            sumo_command
        )

        while (
            traci.simulation
            .getMinExpectedNumber()
            > 0
        ):

            traci.simulationStep()

            observations = (
                collect_current_step(
                    scenario.name
                )
            )

            if observations:

                observation_count += (
                    append_observations(
                        writer,
                        observations,
                        scenario.name,
                    )
                )

        traci.close()

    finally:

        try:
            traci.close()
        except Exception:
            pass

        shutil.rmtree(
            temporary_directory,
            ignore_errors=True,
        )

    print(
        f"Scenario observations: "
        f"{observation_count}"
    )

    return observation_count


def collect_all_scenarios(
    seed: Optional[int] = None,
) -> None:
    """
    Run every configured traffic scenario and create
    one combined dataset.

    A seed can be supplied so that each dataset-generation
    run produces a different but reproducible set of
    traffic scenarios.
    """

    os.makedirs(
        os.path.dirname(
            OUTPUT_FILE
        ),
        exist_ok=True,
    )

    if os.path.exists(
        OUTPUT_FILE
    ):
        os.remove(
            OUTPUT_FILE
        )

    fieldnames = (
        TrafficObservation.csv_headers()
        + ["traffic_scenario"]
    )

    total_observations = 0

    scenarios = get_scenarios(
        seed=seed
    )

    print(
        "Starting multi-scenario "
        "dataset generation..."
    )

    print(
        f"Seed: {seed}"
    )

    print(
        f"Scenarios: {len(scenarios)}"
    )

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for scenario in scenarios:

            count = run_scenario(
                scenario,
                writer,
            )

            total_observations += count

    print()
    print("=" * 80)
    print("MULTI-SCENARIO DATASET COMPLETE")
    print("=" * 80)

    print(
        f"Total observations: "
        f"{total_observations}"
    )

    print(
        f"Dataset: {OUTPUT_FILE}"
    )


if __name__ == "__main__":

    try:

        seed_value = os.getenv(
            "SUMO_RANDOM_SEED"
        )

        seed = (
            int(seed_value)
            if seed_value
            else None
        )

        collect_all_scenarios(
            seed=seed
        )

    except KeyboardInterrupt:

        print(
            "\nDataset generation interrupted."
        )

        try:
            traci.close()
        except Exception:
            pass

    except Exception as exc:

        print()
        print(
            "Multi-scenario dataset generation failed."
        )

        print(
            f"Error: {exc}"
        )

        try:
            traci.close()
        except Exception:
            pass

        raise