"""
PHASE 3: MANGALURU-WIDE REPRODUCIBLE DATA COLLECTOR
===================================================
Generates an authoritative ETA training dataset using the full Mangaluru SUMO road network
(mangaluru_ai.net.xml.gz) across multiple authoritative hospitals, diverse
origin corridors, and configurable traffic scenarios.

Features captured: Only variables observable at real-time inference.
Identifiers captured: run_id, seed, trip_id, ambulance_id, destination_hospital,
                     origin_edge, traffic_scenario, simulation_time.
Explicit Targets:
- target_junction_eta_s: time to upcoming junction approach (<= 5m or node crossing)
- target_junction_observed: 1 if arrival observed, 0 if unreached/censored
- target_hospital_eta_s: total time to destination hospital edge
- target_hospital_observed: 1 if hospital reached, 0 if unreached/censored
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
import sumolib
import traci

PROJECT_ROOT = Path("D:/AIML/Projects/Major")
PY_ROOT = PROJECT_ROOT / "AI-Predictive-Traffic"
sys.path.append(str(PY_ROOT / "controller"))

import config
import astar_router
import route_evaluator
import junction_detector
import signal_mapping
from hospital_manager import HospitalManager

MANGALURU_NET = PY_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"
HOSPITALS_FILE = PY_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
SUMOCFG = PY_ROOT / "simulation" / "mangaluru" / "ambulance_test.sumocfg"

DATA_DIR = PY_ROOT / "scratch" / "phase3_eta" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DATASET_CSV = DATA_DIR / "mangaluru_eta_dataset_v1.csv"

# Global network bindings
config.NET_FILE = MANGALURU_NET
_net = sumolib.net.readNet(str(MANGALURU_NET))
astar_router._SUMO_NETWORK = _net
route_evaluator._SUMO_NETWORK = _net
junction_detector.SUMO_NETWORK = _net

hm = HospitalManager(str(MANGALURU_NET), str(HOSPITALS_FILE))
router = astar_router.AStarRouter(str(MANGALURU_NET))

CSV_HEADER = [
    "run_id",
    "seed",
    "trip_id",
    "ambulance_id",
    "destination_hospital",
    "route_id",
    "origin_edge",
    "traffic_scenario",
    "simulation_time",
    "ambulance_speed_mps",
    "ambulance_speed_kmh",
    "distance_to_junction_m",
    "distance_to_hospital_m",
    "vehicle_count",
    "halted_vehicle_count",
    "mean_speed_kmh",
    "occupancy_percent",
    "signal_phase",
    "signal_time_to_switch_s",
    "junction_id",
    "incoming_edge",
    "outgoing_edge",
    "target_junction_eta_s",
    "target_junction_observed",
    "target_hospital_eta_s",
    "target_hospital_observed",
]


def run_single_trip(
    run_idx: int,
    seed: int,
    origin_edge: str,
    hospital_id: str,
    scenario_name: str,
    max_steps: int = 350,
) -> list[dict]:
    hospital = hm.get_hospital(hospital_id)
    if not hospital or not hospital.nearest_edge:
        print(f"ERROR: Unknown hospital {hospital_id}")
        return []

    dest_edge = hospital.nearest_edge
    route_obj = router.find_route(origin_edge, dest_edge)
    if not route_obj or not route_obj.edge_ids:
        print(f"ERROR: No valid route from {origin_edge} to {dest_edge}")
        return []

    amb_id = f"amb_p3_{run_idx:03d}"
    trip_id = f"trip_{run_idx:03d}_{hospital_id}_{scenario_name}_{seed}"
    route_id = f"route_{trip_id}"

    try:
        traci.close()
    except Exception:
        pass

    traci.start([
        "sumo",
        "-c", str(SUMOCFG),
        "--step-length", "1.0",
        "--seed", str(seed),
        "--no-warnings",
    ])

    # Rebuild TLS cache in current active SUMO session
    signal_mapping._MOVEMENT_TO_TLS_CACHE = None
    signal_mapping._build_tls_cache()

    # Inject trip route and ambulance
    traci.route.add(route_id, route_obj.edge_ids)
    traci.vehicle.add(
        vehID=amb_id,
        routeID=route_id,
        typeID="ambulance",
        depart="1.0",
        departLane="best",
    )

    # Apply scenario conditions
    if scenario_name == "moderate":
        mid_idx = len(route_obj.edge_ids) // 2
        slow_edge = route_obj.edge_ids[mid_idx]
        try:
            traci.edge.setMaxSpeed(slow_edge, 4.0)
        except Exception:
            pass

    elif scenario_name == "heavy":
        mid_idx = len(route_obj.edge_ids) // 2
        for offset in [-1, 0, 1]:
            e_idx = max(0, min(len(route_obj.edge_ids) - 1, mid_idx + offset))
            try:
                traci.edge.setMaxSpeed(route_obj.edge_ids[e_idx], 2.5)
            except Exception:
                pass
        try:
            block_edge = route_obj.edge_ids[mid_idx]
            block_r = f"block_{trip_id}"
            traci.route.add(block_r, [block_edge])
            for i in range(2):
                vid = f"blocker_{trip_id}_{i}"
                traci.vehicle.add(vid, block_r, typeID="passenger")
                traci.vehicle.moveTo(vid, f"{block_edge}_0", 10.0 + i * 8.0)
                traci.vehicle.setSpeed(vid, 0.0)
        except Exception:
            pass

    elif scenario_name == "incident":
        mid_idx = len(route_obj.edge_ids) // 2
        block_edge = route_obj.edge_ids[mid_idx]
        try:
            traci.edge.setMaxSpeed(block_edge, 0.8)
            block_r = f"incident_{trip_id}"
            traci.route.add(block_r, [block_edge])
            for i in range(3):
                vid = f"inc_blocker_{trip_id}_{i}"
                traci.vehicle.add(vid, block_r, typeID="passenger")
                traci.vehicle.moveTo(vid, f"{block_edge}_0", 5.0 + i * 8.0)
                traci.vehicle.setSpeed(vid, 0.0)
        except Exception:
            pass

    # Simulation observations and tracking
    raw_observations: list[dict] = []
    junction_arrivals: dict[str, float] = {}
    active_approaches: dict[str, dict] = {}
    hospital_arrival_time: float | None = None

    step = 0
    ambulance_spawned = False
    ambulance_arrived = False

    while step < max_steps:
        traci.simulationStep()
        sim_time = traci.simulation.getTime()

        # Remove background collision dummy ambulance if present
        if "ambulance" in traci.vehicle.getIDList():
            try:
                traci.vehicle.remove("ambulance")
            except Exception:
                pass

        vehs = traci.vehicle.getIDList()
        if amb_id in vehs:
            ambulance_spawned = True
            current_edge = traci.vehicle.getRoadID(amb_id)
            current_spd_mps = max(0.0, traci.vehicle.getSpeed(amb_id))

            # Check hospital arrival
            if current_edge == dest_edge:
                if hospital_arrival_time is None:
                    hospital_arrival_time = sim_time
                ambulance_arrived = True
                break

            # Calculate remaining route distance to hospital
            route_edges = traci.vehicle.getRoute(amb_id)
            r_idx = traci.vehicle.getRouteIndex(amb_id)
            if 0 <= r_idx < len(route_edges):
                remaining_edges = route_edges[r_idx:]
                dist_to_hospital = sum(_net.getEdge(e).getLength() for e in remaining_edges if _net.hasEdge(e))
            else:
                dist_to_hospital = 0.0

            # Get upcoming signalized junctions
            upcoming = junction_detector.get_upcoming_junctions(max_junctions=3, ambulance_id=amb_id)
            upcoming_ids = set()

            for j in upcoming:
                upcoming_ids.add(j.junction_id)
                active_approaches[j.junction_id] = {
                    "incoming": j.incoming_edge,
                    "outgoing": j.outgoing_edge,
                    "dist": j.distance_from_ambulance_m,
                    "time": sim_time,
                }

                # Mark arrival if approach reached
                if j.distance_from_ambulance_m <= 5.0 and j.junction_id not in junction_arrivals:
                    junction_arrivals[j.junction_id] = sim_time

                # Traffic statistics on incoming edge
                inc_edge = j.incoming_edge
                v_ids = traci.edge.getLastStepVehicleIDs(inc_edge)
                v_count = len(v_ids)
                halted_count = sum(1 for v in v_ids if traci.vehicle.getSpeed(v) < 0.1)
                mean_spd = max(0.0, traci.edge.getLastStepMeanSpeed(inc_edge))
                occ = max(0.0, traci.edge.getLastStepOccupancy(inc_edge))

                # Signal state
                j_id = j.junction_id
                sig_phase = -1
                sig_switch = 0.0
                try:
                    sig_phase = traci.trafficlight.getPhase(j_id)
                    next_sw = traci.trafficlight.getNextSwitch(j_id)
                    sig_switch = max(0.0, next_sw - sim_time)
                except Exception:
                    pass

                obs = {
                    "run_id": f"run_{run_idx:03d}",
                    "seed": seed,
                    "trip_id": trip_id,
                    "ambulance_id": amb_id,
                    "destination_hospital": hospital_id,
                    "route_id": route_id,
                    "origin_edge": origin_edge,
                    "traffic_scenario": scenario_name,
                    "simulation_time": sim_time,
                    "ambulance_speed_mps": round(current_spd_mps, 3),
                    "ambulance_speed_kmh": round(current_spd_mps * 3.6, 2),
                    "distance_to_junction_m": round(j.distance_from_ambulance_m, 2),
                    "distance_to_hospital_m": round(dist_to_hospital, 2),
                    "vehicle_count": v_count,
                    "halted_vehicle_count": halted_count,
                    "mean_speed_kmh": round(mean_spd * 3.6, 2),
                    "occupancy_percent": round(occ, 2),
                    "signal_phase": sig_phase,
                    "signal_time_to_switch_s": round(sig_switch, 2),
                    "junction_id": j_id,
                    "incoming_edge": inc_edge,
                    "outgoing_edge": j.outgoing_edge,
                }
                raw_observations.append(obs)

            # Check for passed / crossed junctions
            for j_id, info in list(active_approaches.items()):
                if j_id not in junction_arrivals:
                    if current_edge == info["outgoing"] or current_edge.startswith(f":{j_id}"):
                        junction_arrivals[j_id] = sim_time
                    elif j_id not in upcoming_ids and info["dist"] < 35.0:
                        junction_arrivals[j_id] = sim_time

        elif ambulance_spawned:
            # Ambulance completed destination and despawned
            if hospital_arrival_time is None:
                hospital_arrival_time = sim_time
            ambulance_arrived = True
            break

        step += 1

    traci.close()

    # Calculate ground-truth targets strictly without lookahead leakage
    final_rows: list[dict] = []
    for obs in raw_observations:
        j_id = obs["junction_id"]
        obs_time = obs["simulation_time"]

        # Junction Target (time to junction arrival)
        if j_id in junction_arrivals and junction_arrivals[j_id] >= obs_time:
            obs["target_junction_eta_s"] = round(junction_arrivals[j_id] - obs_time, 2)
            obs["target_junction_observed"] = 1
        else:
            obs["target_junction_eta_s"] = None
            obs["target_junction_observed"] = 0

        # Hospital Target (total journey ETA)
        if hospital_arrival_time is not None and hospital_arrival_time >= obs_time:
            obs["target_hospital_eta_s"] = round(hospital_arrival_time - obs_time, 2)
            obs["target_hospital_observed"] = 1
        else:
            obs["target_hospital_eta_s"] = None
            obs["target_hospital_observed"] = 0

        # Retain valid observations
        if obs["distance_to_junction_m"] > 0:
            final_rows.append(obs)

    return final_rows


def run_phase3_collection():
    print("=" * 85)
    print("PHASE 3: MANGALURU-WIDE REPRODUCIBLE DATASET COLLECTION")
    print("=" * 85)

    # 8 Authoritative Hospitals across distinct Mangaluru quadrants
    destinations = [
        "kmc_hospital",
        "athena_hospital",
        "indira_hospital",
        "unity_hospital",
        "highland_hospital",
        "father_muller_hospital",
        "vijaya_clinic_general_hospital",
        "calaco_hospital",
    ]

    # Diverse Arterial Origins
    origins = [
        "321397980",     # North / Kadri
        "1358315405",    # Central / Kodialbail
        "1089450246#0",  # South / Kankanady
        "-132363062",    # East Arterial
        "1096889856",    # North-East
    ]

    # Traffic Scenarios
    scenarios = ["light", "moderate", "heavy", "incident"]

    total_trips = 0
    all_samples: list[dict] = []
    run_counter = 1
    base_seed = 2026

    # Select balanced 40 trip matrix: each scenario and origin-hospital pair well represented
    trip_plans = []
    for sc_idx, sc in enumerate(scenarios):
        for orig in origins:
            for dest in destinations[:2]:  # 2 major hospitals per origin-scenario pair
                trip_plans.append((orig, dest, sc))

    print(f"Scheduled {len(trip_plans)} simulation trips across full Mangaluru network...")

    for orig, dest, sc in trip_plans:
        seed = base_seed + run_counter * 17
        print(f"  [Run {run_counter:03d}/{len(trip_plans):03d}] Orig: {orig:<15} -> Dest: {dest:<22} | Scenario: {sc:<8} | Seed: {seed}...", end="", flush=True)

        rows = run_single_trip(
            run_idx=run_counter,
            seed=seed,
            origin_edge=orig,
            hospital_id=dest,
            scenario_name=sc,
            max_steps=350,
        )

        obs_junc = sum(1 for r in rows if r["target_junction_observed"] == 1)
        obs_hosp = sum(1 for r in rows if r["target_hospital_observed"] == 1)
        print(f" Samples: {len(rows):4d} (Valid Junc: {obs_junc:4d}, Hosp: {obs_hosp:4d})")

        all_samples.extend(rows)
        total_trips += 1
        run_counter += 1

        # Incremental save every 5 trips
        if run_counter % 5 == 0 or run_counter > len(trip_plans):
            with open(OUTPUT_DATASET_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
                writer.writeheader()
                writer.writerows(all_samples)

    # Final save
    with open(OUTPUT_DATASET_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(all_samples)

    print("\n" + "=" * 85)
    print(f"DATASET COLLECTION COMPLETED SUCCESSFULLY!")
    print(f"Total Trips Executed : {total_trips}")
    print(f"Total Raw Samples    : {len(all_samples)}")
    print(f"Dataset File Path    : {OUTPUT_DATASET_CSV}")
    print("=" * 85)


if __name__ == "__main__":
    run_phase3_collection()
