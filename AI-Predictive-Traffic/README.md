# AI-Predictive Traffic Management System
**Mangaluru/Kankanady Emergency Traffic Digital Twin**

## 1. Problem Statement
Emergency vehicles in heavily congested urban environments, such as the Kankanady corridor in Mangaluru, frequently experience life-threatening delays due to static traffic signals and gridlock. Traditional preemption systems either disrupt traffic too heavily or are completely ineffective against saturated road queues.

## 2. Objective
To design, simulate, and visually demonstrate an AI-predictive emergency traffic management system that uses Machine Learning for ETA prediction, A* for traffic-aware routing, and progressive multi-junction preemption to clear queues before the ambulance arrives, thereby dramatically reducing emergency travel time while minimizing disruption to background traffic.

## 3. System Architecture
The system consists of a three-tier architecture:
*   **Ground Truth / Simulation Layer (SUMO):** Handles the microscopic physical movement of background traffic and the ambulance.
*   **AI / Control Layer (Python):** Contains the brains of the operation—handling A* routing, ML predictions, and intelligent signal overriding. Connects to SUMO via TraCI.
*   **Digital Twin / Visualization Layer (Unity):** Subscribes to Python/SUMO data over low-latency UDP to render a lightweight, real-time 3D dashboard for explainable AI behavior without affecting the underlying physics.

## 4. SUMO's Role
SUMO generates the background traffic, enforces collision avoidance, calculates edge travel times based on congestion, and executes traffic light states. It provides the "real world" physics foundation that prevents the AI from cheating.

## 5. Python AI's Role
The Python controller sits between SUMO and Unity. It actively pulls SUMO telemetry, feeds it into the ML models, runs A* graph search, triggers signal preemptions, and broadcasts optimized state data to Unity.

## 6. A* Routing
The `astar_router.py` dynamically calculates the fastest path to the selected hospital by treating SUMO edges as a graph where edge weights equal real-time congestion delays.

## 7. ML ETA Prediction
A Random Forest Regressor predicts the ambulance's exact time of arrival at upcoming junctions based on real-time speed, queue length, and distance, enabling the system to trigger preemptions precisely when needed.

## 8. Traffic-Aware Decision Making
The system does not blindly turn signals green. It evaluates the length of the queue at the upcoming junction. If the queue is massive, it preempts early to clear the cars. If the road is empty (Zero Congestion scenario), the AI abstains from preempting, saving cross-traffic from unnecessary red lights.

## 9. Multi-Junction Preemption
Instead of one intersection, the AI can trigger a "Rolling Green Wave," preparing sequential junctions simultaneously (e.g., Junction 1 and Kankanady) to maintain continuous momentum.

## 10. Hospital Destination Architecture
The `HospitalManager` maps logical destinations (e.g., "Highland Hospital", "KMC Hospital") to their nearest valid SUMO edges. The system supports overriding the destination dynamically via Unity UDP commands, forcing the AI to instantly calculate a new route and adapt preemption logic.

## 11. Unity Digital Twin
The Unity frontend provides an optimized, 3D visual explanation of the AI. It features an Emergency Dashboard that explicitly shows WHY the AI is acting (e.g., "PREEMPTING" vs "PREPARING" vs "NORMAL") and renders a thin blue trail indicating the dynamic A* route.

## 12. UDP Synchronization
To bridge Python and Unity, `unity_bridge.py` leverages non-blocking UDP sockets. Python acts as the telemetry server (Ports 5005, 5006, 5007, 5008, 5010) and Unity listens. Unity also sends commands back to Python (Port 5009). 

## 13. SUMO2Unity as Technical Reference
The visualization efficiency (spatial filtering, pooling, coordinate conversion) was inspired by the *SimuTraffX-Lab/SUMO2Unity* architecture, ensuring Unity maintains high FPS without modifying or reducing SUMO's underlying microscopic simulation complexity.

## 14. Performance Optimization
*   **Spatial Filtering:** Unity only visualizes vehicles within a 500m radius of the ambulance.
*   **Object Pooling:** Vehicles are pooled and recycled rather than instantiated/destroyed every frame.
*   **Delta Sync:** Traffic light states and routes are only transmitted when their internal hash/state actually changes, slashing network overhead.

## 15. Three Tested Scenarios
The system is regression-tested against three conditions:
1.  **Heavy Congestion:** Verifies massive queue clearing and early preemption.
2.  **Moderate Congestion:** Verifies standard adaptive routing.
3.  **Zero Congestion:** Verifies that the AI does *not* fire preemptions when roads are completely clear.

## 16. Failure / Edge-Case Handling
*   **Signal Recovery:** When the ambulance passes a junction, the AI explicitly releases the preemption, returning the signal to its normal SUMO program phase.
*   **Dropped Packets:** A 1.5s UDP heartbeat guarantees that Unity eventually catches up if a packet drops.
*   **Dynamic Rerouting:** If the ambulance routes away from a prepared junction, the stale preemption is automatically cancelled.

## 17. Known Limitations
*   This is a simulation. Real-world physical limitations (driver behavior, unpredictable lane changes, network latency in V2X communication) are idealized.
*   ETA predictions rely on macroscopic SUMO edge data, which may deviate from actual microscopic physics in extreme gridlock.

## 18. How to Run the System
1. Open a terminal in the project root.
2. Run the bridge: `python visualization/unity_bridge.py --gui`
3. Press "Play" in the Unity Editor (MangaluruDigitalTwin3D project).
4. Use the Dashboard in Unity to select a destination hospital and observe the AI routing and preemption in real-time.
