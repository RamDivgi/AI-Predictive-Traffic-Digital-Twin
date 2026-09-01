import os
import sys

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from api.models import (
    AmbulanceState,
    TrafficState,
    SignalState,
    DecisionState,
    DigitalTwinState,
    TripStartRequest,
    HospitalResponse,
    StartPointResponse
)
from api.state_provider import StateProvider
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Digital Twin API")

# Serve the static frontend dashboard
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="dashboard")

def get_live_state():
    return StateProvider.read_state()

def unavailable_response():
    return JSONResponse(status_code=503, content={"status": "simulation unavailable"})

@app.get("/health")
def get_health():
    state = get_live_state()
    return {"status": "ok", "simulation_running": state is not None}

STARTING_POINTS = [
    {"id": "1952656064", "label": "Base (Default)", "outgoing_edge": "1096889856"},
    {"id": "290604685", "label": "Start Point 1", "outgoing_edge": "26515013#2"},
    {"id": "12741213715", "label": "Start Point 2", "outgoing_edge": "26299206#2"},
    {"id": "12680853221", "label": "Start Point 3", "outgoing_edge": "1369161858"},
    {"id": "8577986935", "label": "Start Point 4", "outgoing_edge": "924066824#2"},
]

@app.get("/starting-points", response_model=List[StartPointResponse])
def get_starting_points():
    return STARTING_POINTS

@app.get("/hospitals", response_model=List[HospitalResponse])
def get_hospitals(start_junction: Optional[str] = None):
    hospitals = []
    import os
    from controller.hospital_manager import HospitalManager
    from pathlib import Path
    import math
    
    # We must instantiate HospitalManager to properly check routable edges
    # We load from both hospital definition files
    project_root = Path(__file__).resolve().parent.parent
    net_file = str(project_root / "simulation" / "mangaluru" / "presentation_selection2.net.xml")
    hosp_file1 = str(project_root / "simulation" / "mangaluru" / "hospitals.add.xml")
    hosp_file2 = str(project_root / "simulation" / "mangaluru" / "presentation_labels.add.xml")
    
    try:
        hm = HospitalManager(net_file, [hosp_file1, hosp_file2])
        all_hosps = hm.get_all_hospitals()
        
        start_x, start_y = None, None
        if start_junction:
            try:
                node = hm.net.getNode(start_junction)
                start_x, start_y = node.getCoord()
            except Exception as e:
                print(f"Could not find start junction {start_junction}: {e}")

        for h in all_hosps:
            # presentation_labels.add.xml includes clinic and hospital types, some might be duplicated but HospitalManager uses a dict so it deduplicates by ID
            if h.nearest_edge is None:
                hospitals.append({"id": h.id, "name": h.name, "available": False, "reason": "Not accessible from road network (No valid passenger edge nearby)"})
            else:
                dist_km = None
                if start_x is not None and start_y is not None:
                    dist_km = round(math.hypot(h.x - start_x, h.y - start_y) / 1000.0, 1)
                hospitals.append({"id": h.id, "name": h.name, "available": True, "reason": None, "distance_km": dist_km})
                
        if start_x is not None and start_y is not None:
            # Sort by distance
            hospitals.sort(key=lambda x: x.get("distance_km", float('inf')) if x.get("distance_km") is not None else float('inf'))

    except Exception as e:
        print(f"Error loading hospitals in API: {e}")
        
    return hospitals

@app.post("/trip/start")
def start_trip(req: TripStartRequest):
    StateProvider.write_trip_command({
        "action": "start",
        "emergency": req.emergency,
        "hospital_id": req.hospital_id,
        "start_edge": req.start_edge
    })
    return {"status": "ok", "message": "Trip start command issued"}

@app.post("/trip/stop")
def stop_trip():
    StateProvider.write_trip_command({
        "action": "stop"
    })
    return {"status": "ok", "message": "Trip stop command issued"}


@app.get("/state", response_model=DigitalTwinState)
def get_state():
    state = get_live_state()
    if state is None:
        return unavailable_response()
    return state

@app.get("/ambulance", response_model=AmbulanceState)
def get_ambulance():
    state = get_live_state()
    if state is None:
        return unavailable_response()
    
    if state.get("ambulance") is None:
        return JSONResponse(status_code=404, content={"status": "ambulance not in simulation"})
        
    return state["ambulance"]

@app.get("/traffic", response_model=List[TrafficState])
def get_traffic():
    state = get_live_state()
    if state is None:
        return unavailable_response()
    return state.get("traffic", [])

@app.get("/signals", response_model=List[SignalState])
def get_signals():
    state = get_live_state()
    if state is None:
        return unavailable_response()
    return state.get("signals", [])

@app.get("/decisions", response_model=List[DecisionState])
def get_decisions():
    state = get_live_state()
    if state is None:
        return unavailable_response()
    return state.get("decisions", [])

@app.websocket("/ws/state")
async def websocket_state(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            state = get_live_state()
            if state is None:
                await websocket.send_json({"status": "simulation unavailable"})
            else:
                await websocket.send_json(state)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
