# Academic Presentation Outline: Final-Year Major Project

**Project Title:** AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment  
**Department:** Artificial Intelligence & Machine Learning (AIML)  
**Degree:** Bachelor of Engineering (B.E.)  
**Academic Year:** 2026  

---

## Slide 1: Title & Project Overview
- **Title:** AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment
- **Domain:** Intelligent Transportation Systems (ITS) • Cyber-Physical Systems • Deep/Machine Learning
- **Focus:** Real-time emergency vehicle transit optimization across Mangaluru urban corridors using micro-simulation (SUMO) and 3D digital twins (Unity).

---

## Slide 2: Problem Statement & Motivation
- **The Challenge:**
  - Emergency vehicles (ambulances) lose critical minutes at congested urban intersections.
  - Traditional siren-based transit is reactive and impeded by accumulated vehicle queues that cannot move at red lights.
  - Blind preemption causes severe civilian gridlock, pedestrian safety hazards, and phase starvation on cross-streets.
- **Project Objective:**
  - Build an end-to-end digital twin combining traffic-aware pathfinding, machine-learning ETA prediction, proactive traffic light preemption, and real-time 3D spatial visualization.

---

## Slide 3: End-to-End System Architecture
- **Layer 1: Micro-Simulation Layer (SUMO)**
  - Real-world Mangaluru road network extracted from OpenStreetMap (OSM).
  - High-fidelity vehicle physics, multi-modal traffic, lane dynamics, and actuated traffic lights.
- **Layer 2: AI Control & Decision Layer (Python)**
  - Traffic-aware A* Router dynamically recalculating routes based on live link costs and queue penalties.
  - Real-time ML ETA Regressor inferring travel times to downstream junctions.
  - Preemption Controller orchestrating green waves, yellow clearance, and restoration.
- **Layer 3: Visualization & Telemetry Layer (Unity 3D & FastAPI)**
  - Asynchronous UDP socket bridge streaming transforms, route lines, signal states, and telemetry.
  - Interactive Web Dashboard for monitoring, hospital selection, and manual congestion injection.

---

## Slide 4: Mangaluru Digital Twin & Road Network
- **Geographic Scope:** Arterial corridors connecting Kankanady, Balmatta, Falnir, Hampankatta, and Jyothi Circle.
- **Network Dimensions:**
  - **1,764 Road Edges** and **825 Graph Nodes**.
  - **55 Traffic Light Systems (TLS)** mapped with exact movement-to-phase tables.
  - **11 Real-World Hospitals** mapped with coordinate landmarks and ingress edges (Athena, Highland, KMC, Father Muller, SCS, Unity, City Hospital).
- **Presentation Selection:** High-density 4-square-kilometer zone calibrated for interactive visual fidelity.

---

## Slide 5: Traffic-Aware Dynamic A* Routing
- **Mathematical Cost Formulation:**
  $$C(e) = w_t \cdot t_{\text{free}}(e) + w_q \cdot t_{\text{queue}}(e) + w_s \cdot t_{\text{signal}}(e)$$
  - $t_{\text{free}}(e) = \text{Length}(e) / \max(v_{\text{amb}}, v_{\text{limit}})$ (Base travel time)
  - $t_{\text{queue}}(e) = N_{\text{halted}} \times 2.5\text{s}$ (Queue dissipation penalty based on HCM headway)
  - $t_{\text{signal}}(e)$ = Signal phase delay penalty at intersection
- **Admissible Heuristic:**
  $$h(n) = \frac{\text{EuclideanDistance}(n, \text{Dest})}{v_{\max}} \le h^*(n)$$
  - Mathematically guarantees optimal path selection without overestimating true travel costs.
- **Live Rerouting:** Automatically detects newly formed bottleneck jams or incidents and diverts the ambulance along alternate arterial corridors.

---

## Slide 6: Machine Learning ETA Prediction
- **Target Variable:** Time-to-arrival at the next downstream junction ($t_{\text{arrival}} - t_{\text{sim}}$ in seconds).
- **8 Feature Predictors (Strict Non-Leakage Schema):**
  1. `ambulance_speed_mps`: Instantaneous ambulance velocity.
  2. `distance_to_junction_m`: Euclidean & path distance along road link.
  3. `vehicle_count`: Preceding traffic density on incoming lane.
  4. `halted_vehicle_count`: Stopped vehicles ($v < 0.1$ m/s) blocking approach.
  5. `mean_speed_kmh`: Background traffic average cruising speed.
  6. `occupancy_percent`: Sensor loop lane occupancy.
  7. `signal_phase`: Active signal phase index.
  8. `signal_time_to_switch_s`: Elapsed / remaining phase duration.
- **Model Comparison (Phase 4 Shadow Benchmark - 6,306 ground-truth samples):**
  - **Candidate Random Forest:** $\text{MAE} = 18.37\text{s}$ ($R^2 = 0.760$, $\text{P90} = 43.9\text{s}$)
  - **Production Random Forest:** $\text{MAE} = 74.32\text{s}$ ($R^2 = -1.156$, $\text{P90} = 178.3\text{s}$)
  - **Physics Baseline ($\text{Dist}/\text{Speed}$):** $\text{MAE} = 54.54\text{s}$ ($R^2 = -0.259$, $\text{P90} = 135.8\text{s}$)

---

## Slide 7: Predictive Signal Preemption Logic
- **Preemption Trigger Conditions:**
  $$\text{Trigger} = (\text{Conflict} \lor \text{InWindow}) \land (N_{\text{halted}} \le 5) \land (10\text{m} < \text{Dist} \le 500\text{m})$$
  - $\text{Conflict}$: Signal is currently red and $\text{ETA} \le \text{TimeToSwitch} + (N_{\text{halted}} \times 2.5\text{s})$.
  - $\text{InWindow}$: Predicted $\text{ETA} \le 20.0\text{s}$ (proactive green corridor preparation).
- **Safety Safeguards:**
  - **Mandatory Yellow Transition:** Enforces a 3.0s yellow warning phase before switching signals.
  - **Hold Time Enforcement:** Holds green phase for 8.0s or until ambulance clearance is detected.
  - **Automatic Restoration:** Immediately reverts traffic light to standard cyclical plan once the ambulance passes the detector edge.
  - **Heavy Queue Suppression:** Suppresses preemption if cross-queues exceed critical safety thresholds.

---

## Slide 8: Unity 3D Visualization & Digital Twin Architecture
- **Network Pipeline:** Multi-threaded asynchronous UDP streaming:
  - Port 5005: Ambulance coordinates, speed, heading.
  - Port 5006: Civilian traffic fleet.
  - Port 5007: Dynamic signal heads (Red/Yellow/Green materials).
  - Port 5008: Active route polyline renderer.
  - Port 5009: Inbound control commands from Unity UI to SUMO.
- **Visual Features:**
  - Procedural road mesh generation from `RoadNetwork.json`.
  - Vehicle position smoothing (dead reckoning & Hermite interpolation).
  - Dual-mode camera: Dynamic chase camera and bird's-eye orbital overview.
  - Hospital 3D markers and billboard distance callouts.

---

## Slide 9: Controlled A/B Experiment & Critical Academic Findings
- **16 Matched Pairs (32 Simulation Runs) in Closed-Loop SUMO Simulation:**
  - Comparing Production Preemption (Control) vs Candidate Preemption (Treatment).
  - 100% Valid Completion Rate (16/16 pairs reached hospital destination).
- **The Core Academic Finding:**
  - Control travel time averaged **237.31s** vs Candidate **245.12s** ($\Delta = +7.81\text{s}$ slower, $p = 0.0266$).
  - Control faster in 12 pairs; Treatment faster in 3 pairs (including a dramatic **-26.0s speedup** in heavy congestion); Tied in 1 pair.
- **Why Did Higher Model Accuracy Lead to Slower Travel Times?**
  - **The Queue Dissipation Paradox:** Control model had high MAE (+74s bias), triggering preemption ~28s early. While premature, this gave queued vehicles ample time to accelerate and disperse!
  - Candidate model predicted arrival with pinpoint accuracy (~9.7s lead time). However, queued passenger cars take $2.5\text{s}$ each to react and clear. By the time the ambulance arrived, vehicles were still dissipating, causing brief deceleration.
- **Operational Trade-Off Advantage:**
  - Candidate slashed signal preemption disruptions by **44.0%** (30.6 down to 17.1 activations/trip) and reduced hold times by **64.8%** (27.6s down to 9.7s), preserving civilian cross-traffic flow.
- **Scientific Conclusion:**  
  *Lower offline ETA error does not automatically improve closed-loop transit.* Preemption algorithms must include an explicit standing-queue clearance buffer. Therefore, the candidate model is held in staging and not blindly integrated.

---

## Slide 10: Limitations, Future Work & Conclusion
- **Verified Deliverables:**
  - Real-world Mangaluru road network (1,764 edges, 55 TLS) & multi-scenario SUMO simulation.
  - Functional A* traffic-aware dynamic rerouting (-36.7s improvement under congestion).
  - ML ETA inference with fail-safe boundary protections (9,667 inferences, 0 crashes/clamps).
  - Real-time Unity 3D digital twin & Web Dashboard (19/19 auth tests passed).
  - Rigorous, truthful empirical evaluation across all 16 matched pairs with zero fabricated data.
- **Limitations:**
  - Fixed preemption hold times (8.0s) rather than vehicle-actuated dynamic extension.
  - Pure simulation physics (idealized driver lane compliance, no two-wheeler creeping).
  - Zero-latency wireless assumptions (no cellular packet loss or transmission lag modeled).
- **Future Scope:**
  - Queue dissipation preemption buffer: $\text{Trigger} = \text{ETA} + (N_{\text{halted}} \times 2.5\text{s})$.
  - DSRC / C-V2X vehicle-to-infrastructure communication simulation.
  - Hardware-in-the-loop (HIL) traffic controller interfacing with Mangaluru Smart City ICCC.
