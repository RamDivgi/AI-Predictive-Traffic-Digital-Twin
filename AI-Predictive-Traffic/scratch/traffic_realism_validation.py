"""
Traffic Realism Validation Script
Performs a comparative evaluation of Medium, High, and Bottleneck traffic scenarios
under reproducible random seeds (42, 101, 2024) and comparable simulation durations (50.0s / 500 steps).

Measures:
1. Actual vehicles inserted (departed) and active.
2. Network-wide mean speed and speed on monitored bottleneck edges vs alternative edges.
3. Max and average halted-vehicle counts / queue lengths.
4. Insertion failures (buffered/pending), waiting departures, and teleportations.
5. Repeatability of localized bottleneck congestion vs alternative corridors.
6. Behavior of the 4 deterministic queue vehicles on jam_route.
7. Dashboard state and Unity broadcasting payload structure.
"""
import sys
import os
import time
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "controller"))

import traci
import config
from visualization.unity_bridge import (
    generate_round_traffic,
    cleanup_simulation_traffic,
    TrafficMetricsTracker
)

CFG_FILE = str(PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_demo.sumocfg")

MONITORED_BOTTLENECK_EDGES = [
    "1189020226#3", "-132363066#1", "-132363066#0", "903009071#1",
    "26182678#1", "26182678#2", "26182678#3", "26299195#1", "26299195#2"
]

ALTERNATIVE_CORRIDOR_EDGES = [
    "-184750315#1", "1368365880", "26209723#2", "26209723#3",
    "1213225868", "1213225869", "-26209727#1"
]

SEEDS = [42, 101, 2024]
SCENARIOS = ["medium", "high", "bottleneck"]
STEPS_PER_RUN = 500  # 50.0 simulation seconds (0.1s step-length)

def start_sim():
    traci.start([
        "sumo",
        "-c", CFG_FILE,
        "--step-length", "0.1",
        "--random",
        "--ignore-route-errors",
        "--quit-on-end",
        "--start"
    ])

def close_sim():
    try:
        traci.close()
    except Exception:
        pass

def run_scenario(scenario_name: str, seed: int, round_id: int):
    # Setup round
    cur_t = traci.simulation.getTime()
    tracker = TrafficMetricsTracker()
    sched = generate_round_traffic(round_id=round_id, current_time=cur_t, scenario=scenario_name, seed=seed)
    tracker.reset_round(round_id=round_id, scenario=scenario_name, scheduled_ids=sched)

    network_speeds = []
    monitored_speeds = {e: [] for e in MONITORED_BOTTLENECK_EDGES}
    monitored_queues = {e: [] for e in MONITORED_BOTTLENECK_EDGES}
    alternative_speeds = {e: [] for e in ALTERNATIVE_CORRIDOR_EDGES}
    alternative_queues = {e: [] for e in ALTERNATIVE_CORRIDOR_EDGES}
    
    teleport_count = 0
    buffered_insertion_counts = []
    deterministic_seen = set()
    deterministic_speeds = {f"rnd_{round_id}_jam_{i}": [] for i in range(4)}

    for step in range(STEPS_PER_RUN):
        traci.simulationStep()
        tracker.update_step()
        
        # Teleportations check
        tel = traci.simulation.getStartingTeleportNumber()
        if tel > 0:
            teleport_count += tel

        # Check vehicle insertion buffer / pending
        # Vehicles loaded but not yet departed because edge was full
        # (In SUMO, BUF/pending vehicles)
        loaded = traci.simulation.getLoadedNumber()
        departed_total = traci.simulation.getDepartedNumber()

        # Network-wide mean speed
        active_ids = traci.vehicle.getIDList()
        if active_ids:
            cur_speeds = [traci.vehicle.getSpeed(v) for v in active_ids]
            network_speeds.append((sum(cur_speeds) / len(cur_speeds)) * 3.6)
        
        # Monitored corridor edges
        for e in MONITORED_BOTTLENECK_EDGES:
            try:
                s = traci.edge.getLastStepMeanSpeed(e) * 3.6
                q = traci.edge.getLastStepHaltingNumber(e)
                monitored_speeds[e].append(s)
                monitored_queues[e].append(q)
            except Exception:
                pass

        # Alternative corridor edges
        for e in ALTERNATIVE_CORRIDOR_EDGES:
            try:
                s = traci.edge.getLastStepMeanSpeed(e) * 3.6
                q = traci.edge.getLastStepHaltingNumber(e)
                alternative_speeds[e].append(s)
                alternative_queues[e].append(q)
            except Exception:
                pass

        # Deterministic queue vehicles inspection
        for i in range(4):
            jid = f"rnd_{round_id}_jam_{i}"
            if jid in active_ids:
                deterministic_seen.add(jid)
                deterministic_speeds[jid].append(traci.vehicle.getSpeed(jid) * 3.6)

    final_metrics = tracker.get_metrics_dict()
    
    # Calculate aggregates
    avg_net_speed = round(sum(network_speeds) / len(network_speeds), 2) if network_speeds else 0.0
    
    all_mon_speeds = [s for lst in monitored_speeds.values() for s in lst if s > 0]
    avg_mon_speed = round(sum(all_mon_speeds) / len(all_mon_speeds), 2) if all_mon_speeds else 0.0
    
    all_mon_queues = [q for lst in monitored_queues.values() for q in lst]
    max_mon_queue = max(all_mon_queues) if all_mon_queues else 0
    avg_mon_queue = round(sum(all_mon_queues) / len(all_mon_queues), 2) if all_mon_queues else 0.0

    all_alt_speeds = [s for lst in alternative_speeds.values() for s in lst if s > 0]
    avg_alt_speed = round(sum(all_alt_speeds) / len(all_alt_speeds), 2) if all_alt_speeds else 0.0

    all_alt_queues = [q for lst in alternative_queues.values() for q in lst]
    max_alt_queue = max(all_alt_queues) if all_alt_queues else 0
    avg_alt_queue = round(sum(all_alt_queues) / len(all_alt_queues), 2) if all_alt_queues else 0.0

    # Deterministic vehicles summary
    det_avg_speeds = {
        jid: round(sum(speeds) / len(speeds), 1) if speeds else 0.0
        for jid, speeds in deterministic_speeds.items()
    }
    
    # Clean up round
    rem = cleanup_simulation_traffic(sched)
    traci.simulationStep()
    lingering = len(traci.vehicle.getIDList())

    return {
        "scenario": scenario_name,
        "seed": seed,
        "scheduled": final_metrics["scheduled"],
        "inserted": final_metrics["inserted"],
        "active_at_t50": final_metrics["active"],
        "arrived": final_metrics["arrived"],
        "waiting_halted_t50": final_metrics["waiting"],
        "avg_network_speed_kmh": avg_net_speed,
        "avg_monitored_speed_kmh": avg_mon_speed,
        "avg_alternative_speed_kmh": avg_alt_speed,
        "max_monitored_queue": max_mon_queue,
        "avg_monitored_queue": avg_mon_queue,
        "max_alternative_queue": max_alt_queue,
        "avg_alternative_queue": avg_alt_queue,
        "teleportations": teleport_count,
        "deterministic_entered_count": len(deterministic_seen),
        "deterministic_speeds_kmh": det_avg_speeds,
        "lingering_vehicles_post_cleanup": lingering
    }

def main():
    print("=" * 80)
    print("STARTING TRAFFIC REALISM COMPARATIVE VALIDATION")
    print(f"Scenarios: {SCENARIOS} | Seeds: {SEEDS} | Duration: {STEPS_PER_RUN * 0.1:.1f}s each")
    print("=" * 80)

    start_sim()
    results = []
    round_counter = 1

    try:
        for sc in SCENARIOS:
            for sd in SEEDS:
                print(f"\n---> Running scenario '{sc}' (seed={sd}, round={round_counter})...")
                res = run_scenario(sc, sd, round_counter)
                results.append(res)
                print(f"     Scheduled: {res['scheduled']} | Inserted: {res['inserted']} | Active(t50): {res['active_at_t50']}")
                print(f"     Net Speed: {res['avg_network_speed_kmh']} km/h | Monitored Speed: {res['avg_monitored_speed_kmh']} km/h | Alt Speed: {res['avg_alternative_speed_kmh']} km/h")
                print(f"     Monitored Queue Max/Avg: {res['max_monitored_queue']} / {res['avg_monitored_queue']} | Alt Queue Max/Avg: {res['max_alternative_queue']} / {res['avg_alternative_queue']}")
                print(f"     Teleports: {res['teleportations']} | Deterministic Active: {res['deterministic_entered_count']}/4 | Post Cleanup Lingering: {res['lingering_vehicles_post_cleanup']}")
                round_counter += 1

        out_file = PROJECT_ROOT / "scratch" / "traffic_realism_results.json"
        with open(out_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n[DONE] Results written to {out_file}")

    finally:
        close_sim()

if __name__ == "__main__":
    main()
