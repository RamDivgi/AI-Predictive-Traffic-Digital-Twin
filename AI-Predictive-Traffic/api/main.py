import os
import sys

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from fastapi.responses import JSONResponse
from typing import List
from api.models import (
    AmbulanceState,
    TrafficState,
    SignalState,
    DecisionState,
    DigitalTwinState
)
from api.state_provider import StateProvider

app = FastAPI(title="Digital Twin API")

def get_live_state():
    return StateProvider.read_state()

def unavailable_response():
    return JSONResponse(status_code=503, content={"status": "simulation unavailable"})

@app.get("/health")
def get_health():
    state = get_live_state()
    return {"status": "ok", "simulation_running": state is not None}

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
