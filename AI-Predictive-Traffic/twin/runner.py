import os
import sys
import time
import math

# Ensure SUMO_HOME is set
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")

import traci
from traci.exceptions import TraCIException, FatalTraCIError

# Import StateProvider
api_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'api'))
if api_dir not in sys.path:
    sys.path.append(api_dir)
from state_provider import StateProvider

def run_digital_twin():
    sumocfg = os.path.abspath(os.path.join(
        os.path.dirname(__file__), 
        "..", 
        "simulation", 
        "mangaluru", 
        "ambulance_test.sumocfg"
    ))
    
    if not os.path.exists(sumocfg):
        print(f"Error: Configuration file not found at {sumocfg}")
        sys.exit(1)
        
    print(f"Starting Digital Twin with config: {sumocfg}")
    
    try:
        traci.start(["sumo", "-c", sumocfg, "--no-warnings", "true"])
        print("TraCI connected successfully.")
    except Exception as e:
        print(f"Failed to start TraCI: {e}")
        sys.exit(1)
        
    try:
        step = 0
        step_length = traci.simulation.getDeltaT()
        print(f"Simulation step length: {step_length}s")
        print("Entering real-time simulation loop. Press Ctrl+C to stop.")
        
        start_wall_time = time.time()
        start_sim_time = traci.simulation.getTime()
        
        # Get all traffic lights for monitoring
        traffic_lights = traci.trafficlight.getIDList()
        
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            sim_time = traci.simulation.getTime()
            
            # --------------------------------------------------------
            # Extract state for API
            # --------------------------------------------------------
            vehicle_count = traci.vehicle.getIDCount()
            
            ambulance_state = None
            if "ambulance" in traci.vehicle.getIDList():
                speed = traci.vehicle.getSpeed("ambulance")
                edge = traci.vehicle.getRoadID("ambulance")
                x, y = traci.vehicle.getPosition("ambulance")
                lon, lat = traci.simulation.convertGeo(x, y, False)
                route_id = traci.vehicle.getRouteID("ambulance")
                # Default destination is the last edge in the route
                edges = traci.vehicle.getRoute("ambulance")
                destination = edges[-1] if edges else "Unknown"
                
                ambulance_state = {
                    "vehicle_id": "ambulance",
                    "latitude": lat,
                    "longitude": lon,
                    "speed": speed,
                    "current_edge": edge,
                    "current_route": route_id,
                    "destination": destination,
                    "eta": 0.0 # Placeholder unless calculated
                }
                
            traffic_state = [
                {
                    "edge_id": "total_network",
                    "vehicle_count": vehicle_count,
                    "average_speed": 0.0,
                    "occupancy": 0.0,
                    "timestamp": sim_time
                }
            ]
            
            signals_state = []
            # Just take the first few to avoid massive JSON for the prototype
            for tl in traffic_lights[:5]:
                signals_state.append({
                    "junction_id": tl,
                    "state": traci.trafficlight.getRedYellowGreenState(tl),
                    "phase": traci.trafficlight.getPhase(tl),
                    "timestamp": sim_time
                })
                
            state_dict = {
                "simulation_time": sim_time,
                "ambulance": ambulance_state,
                "traffic": traffic_state,
                "signals": signals_state,
                "decisions": []
            }
            
            StateProvider.write_state(state_dict)
            
            # Print periodically
            if step % 5 == 0:
                amb_status = "Not spawned"
                if ambulance_state:
                    amb_status = f"Edge: {ambulance_state['current_edge']}, Speed: {ambulance_state['speed']:.1f}m/s"
                elif sim_time > 10.0:
                    amb_status = "Arrived/Departed"
                else:
                    amb_status = "Waiting to depart"
                    
                print(f"[Sim Time: {sim_time:.1f}s] Active Vehicles: {vehicle_count} | Ambulance: {amb_status}")
            
            # Real-time synchronization
            elapsed_sim_time = sim_time - start_sim_time
            elapsed_wall_time = time.time() - start_wall_time
            
            sleep_time = elapsed_sim_time - elapsed_wall_time
            if sleep_time > 0:
                time.sleep(sleep_time)
                
            step += 1
            
        print("Simulation ended natively.")
        
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down Digital Twin...")
    except TraCIException as e:
        print(f"\nTraCI Exception: {e}")
    except FatalTraCIError as e:
        print(f"\nFatal TraCI Error: {e}")
    except Exception as e:
        print(f"\nUnexpected error during simulation: {e}")
    finally:
        print("Closing TraCI connection...")
        try:
            if traci.isLoaded():
                traci.close()
        except Exception:
            pass
        StateProvider.clear_state()
        print("Shutdown complete.")

if __name__ == "__main__":
    run_digital_twin()
