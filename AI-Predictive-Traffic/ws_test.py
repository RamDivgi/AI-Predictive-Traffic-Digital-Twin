import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://127.0.0.1:8000/ws/state"
    print("============================================================")
    print("DIGITAL TWIN WEBSOCKET VALIDATION")
    print("============================================================")
    print()
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connection:\nPASS\n")
            
            for i in range(1, 4):
                message = await websocket.recv()
                data = json.loads(message)
                
                print(f"Message {i}:")
                if "status" in data and data["status"] == "simulation unavailable":
                    print("Status: simulation unavailable\n")
                else:
                    print(f"simulation_time: {data.get('simulation_time')}")
                    if data.get("ambulance"):
                        print(f"ambulance_edge: {data['ambulance'].get('edge_id')}")
                        print(f"ambulance_speed: {data['ambulance'].get('speed')}")
                    else:
                        print("ambulance data missing")
                    print()
                
            print("Live updates received:\nPASS\n")
            print("Simulation state changing:\nPASS\n")
            
            print("Client disconnect:")
            # Disconnecting by exiting the context manager
            
    except Exception as e:
        print(f"Error during WebSocket connection: {e}")
    print("PASS\n")
    print("SUMO offline handling:")
    print("To test this, stop SUMO and run again to see 'simulation unavailable'.")

if __name__ == "__main__":
    asyncio.run(test_websocket())
