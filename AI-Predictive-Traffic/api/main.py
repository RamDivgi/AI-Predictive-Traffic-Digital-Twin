import os
import sys
import json

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, HTTPException, status, Depends
import asyncio
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from pathlib import Path
import math
from api.models import (
    AmbulanceState,
    TrafficState,
    SignalState,
    DecisionState,
    DigitalTwinState,
    TripStartRequest,
    TripModeRequest,
    IncidentCreateRequest,
    IncidentClearRequest,
    SimControlRequest,
    HospitalResponse,
    StartPointResponse,
    LoginRequest,
    LoginResponse,
    UserProfile
)
from api.state_provider import StateProvider
from api.auth import (
    require_auth,
    authenticate_user,
    create_session,
    get_session,
    revoke_session,
    DEMO_USERS,
    get_current_user_from_request
)

from api.trip_history import TripHistoryManager
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI(title="Digital Twin API")

# Serve the static frontend dashboard
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="dashboard")

def get_live_state():
    state = StateProvider.read_state()
    if state:
        # Check if trip completed and update TripHistory
        ds = state.get("decision_support", {})
        lts = ds.get("last_trip_summary")
        if lts and lts.get("completed"):
            act_s = lts.get("actual_travel_time_s") or lts.get("actual_travel_time_seconds", 0.0)
            ini_s = lts.get("initial_predicted_eta_s") or lts.get("initial_predicted_eta_seconds", 0.0)
            gc = state.get("green_corridor", {})
            preempt_count = gc.get("preemption_count", 0)
            reroute_count = ds.get("reroute_count", 0)
            TripHistoryManager.complete_active_trip(
                actual_duration_s=act_s,
                predicted_eta_s=ini_s,
                preemptions_count=preempt_count,
                reroutes_count=reroute_count
            )
    return state

def unavailable_response():
    return JSONResponse(status_code=503, content={"status": "simulation unavailable"})

@app.get("/health")
def get_health():
    state = get_live_state()
    return {"status": "ok", "simulation_running": state is not None}

# AMBULANCE FLEET REGISTRY
AMBULANCES = [
    {
        "id": "AMB-01",
        "name": "Ambulance 01 (ALS Unit)",
        "callsign": "ALS-MGL-01",
        "type": "Advanced Life Support",
        "station": "Father Muller Medical Base",
        "equipment": "Defibrillator, Ventilator, Real-Time Telemetry Bridge",
        "status": "Available"
    },
    {
        "id": "AMB-02",
        "name": "Ambulance 02 (BLS Unit)",
        "callsign": "BLS-MGL-02",
        "type": "Basic Life Support",
        "station": "Pumpwell Standby Post",
        "equipment": "First Response, Trauma Kit",
        "status": "Standby"
    },
    {
        "id": "AMB-03",
        "name": "Ambulance 03 (Critical Care)",
        "callsign": "MICU-MGL-03",
        "type": "Mobile Intensive Care Unit",
        "station": "Kankanady Depot",
        "equipment": "Full Intensive Care Suite",
        "status": "Standby"
    }
]

@app.get("/ambulances")
def get_ambulances():
    state = get_live_state()
    active_amb = state.get("ambulance") if state else None
    fleet = [dict(a) for a in AMBULANCES]
    if active_amb and active_amb.get("vehicle_id"):
        fleet[0]["status"] = "En Route"
        fleet[0]["current_speed_kmh"] = round(active_amb.get("speed", 0.0) * 3.6, 1)
        fleet[0]["current_edge"] = active_amb.get("current_edge", "Unknown")
        fleet[0]["destination"] = active_amb.get("destination", "Assigned")
    return fleet

# AUTHENTICATION ENDPOINTS
@app.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, response: Response):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Use demo account: dispatcher (pass: dispatch123), traffic_admin (pass: admin123), or evaluator (pass: viewer123)."
        )
    token = create_session(
        username=user["username"],
        operator_name=req.operator_name,
        assigned_ambulance=req.assigned_ambulance
    )
    session = get_session(token)
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=86400,
        httponly=False,
        samesite="lax"
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "username": session["username"],
            "name": session["name"],
            "operator_name": session["operator_name"],
            "assigned_ambulance": session["assigned_ambulance"],
            "role": session["role"],
            "permissions": session["permissions"]
        }
    }


@app.get("/auth/me")
def get_me(current_user: dict = Depends(require_auth())):
    return current_user

@app.post("/auth/logout")
def logout(request: Request, response: Response, current_user: dict = Depends(require_auth())):
    token = request.cookies.get("session_token")
    if not token and request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token:
        revoke_session(token)
    response.delete_cookie("session_token")
    return {"status": "ok", "message": "Logged out successfully"}

@app.get("/auth/demo-accounts")
def get_demo_accounts():
    return [
        {
            "username": u["username"],
            "name": u["name"],
            "role": u["role"],
            "permissions": u["permissions"],
            "description": u["description"]
        }
        for u in DEMO_USERS.values()
    ]


STARTING_POINTS = [
    {"id": "1096889856", "label": "Base (Father Muller Road)", "name": "Base (Father Muller Road)", "outgoing_edge": "1096889856", "edge_id": "1096889856"},
    {"id": "-26209727#1", "label": "Start Point 1 (Kankanady Bypass)", "name": "Start Point 1 (Kankanady Bypass)", "outgoing_edge": "-26209727#1", "edge_id": "-26209727#1"},
    {"id": "1213225868", "label": "Start Point 2 (Pumpwell / Highway Inflow)", "name": "Start Point 2 (Pumpwell / Highway Inflow)", "outgoing_edge": "1213225868", "edge_id": "1213225868"},
    {"id": "-1154699531", "label": "Start Point 3 (Falnir Inflow)", "name": "Start Point 3 (Falnir Inflow)", "outgoing_edge": "-1154699531", "edge_id": "-1154699531"},
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
            coords = {"x": round(h.x, 2), "y": round(h.y, 2)}
            dest_type = getattr(h, "destination_type", "hospital")
            if h.nearest_edge is None:
                hospitals.append({
                    "id": h.id,
                    "name": h.name,
                    "available": False,
                    "reason": "Not accessible from road network (No valid passenger edge nearby)",
                    "coordinates": coords,
                    "x": coords["x"],
                    "y": coords["y"],
                    "destination_type": dest_type
                })
            else:
                dist_km = None
                if start_x is not None and start_y is not None:
                    dist_km = round(math.hypot(h.x - start_x, h.y - start_y) / 1000.0, 1)
                hospitals.append({
                    "id": h.id,
                    "name": h.name,
                    "available": True,
                    "reason": None,
                    "distance_km": dist_km,
                    "nearest_edge": h.nearest_edge,
                    "coordinates": coords,
                    "x": coords["x"],
                    "y": coords["y"],
                    "destination_type": dest_type
                })
                
        if start_x is not None and start_y is not None:
            # Sort by distance
            hospitals.sort(key=lambda x: x.get("distance_km", float('inf')) if x.get("distance_km") is not None else float('inf'))

    except Exception as e:
        print(f"Error loading hospitals in API: {e}")
        
    return hospitals

@app.post("/trip/start")
def start_trip(req: TripStartRequest, current_user: dict = Depends(require_auth(["dispatcher", "admin"]))):
    # Enforce assigned ambulance authorization
    session_amb = current_user.get("assigned_ambulance", "AMB-01")
    if req.ambulance_id and req.ambulance_id != session_amb and current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Authorization failure: Account is assigned to {session_amb}. Cannot dispatch {req.ambulance_id}."
        )
    
    ambulance_to_dispatch = session_amb or req.ambulance_id or "AMB-01"

    # Lookup destination name
    destination_name = req.hospital_id
    try:
        all_hosps = get_hospitals()
        for h in all_hosps:
            if h.get("id") == req.hospital_id:
                destination_name = h.get("name", req.hospital_id)
                break
    except Exception:
        pass

    origin_name = req.start_edge or "Base (Father Muller Road)"
    for sp in STARTING_POINTS:
        if sp["id"] == req.start_edge:
            origin_name = sp["label"]
            break

    # Calculate initial predicted ETA if recommend endpoint is available
    predicted_eta = None
    try:
        rec_data = recommend_hospital(start_edge=req.start_edge)
        if isinstance(rec_data, dict):
            for rec in rec_data.get("recommendations", []):
                if rec.get("hospital_id") == req.hospital_id:
                    predicted_eta = rec.get("total_cost_s")
                    break
    except Exception:
        pass

    StateProvider.write_trip_command({
        "action": "start",
        "emergency": req.emergency,
        "hospital_id": req.hospital_id,
        "ambulance_id": ambulance_to_dispatch,
        "start_edge": req.start_edge,
        "traffic_scenario": req.traffic_scenario or "medium"
    })

    op_name = current_user.get("operator_name", current_user["name"])
    trip_record = TripHistoryManager.start_trip(
        ambulance_id=ambulance_to_dispatch,
        origin_name=origin_name,
        start_edge=req.start_edge or "1096889856",
        hospital_id=req.hospital_id,
        destination_name=destination_name,
        traffic_scenario=req.traffic_scenario or "medium",
        emergency_mode=req.emergency,
        predicted_eta=predicted_eta,
        dispatched_by=current_user["username"],
        operator_name=op_name
    )

    return {
        "status": "ok",
        "message": f"Trip start command issued for {destination_name} (Ambulance: {ambulance_to_dispatch}, Operator: {op_name})",
        "trip": trip_record
    }


@app.post("/trip/stop")
def stop_trip(current_user: dict = Depends(require_auth(["dispatcher", "admin"]))):
    StateProvider.write_trip_command({
        "action": "stop"
    })
    aborted_trip = TripHistoryManager.abort_active_trip(
        reason=f"Aborted by operator ({current_user['name']})"
    )
    return {
        "status": "ok",
        "message": "Trip stop command issued",
        "trip": aborted_trip
    }

@app.post("/trip/mode")
def set_trip_mode(req: TripModeRequest, current_user: dict = Depends(require_auth(["dispatcher", "admin"]))):
    StateProvider.write_trip_command({
        "action": "set_mode",
        "emergency": req.emergency
    })
    return {"status": "ok", "message": f"Trip emergency mode set to {req.emergency}"}

@app.post("/incident/add")
def add_incident(req: IncidentCreateRequest, current_user: dict = Depends(require_auth(["admin"]))):
    StateProvider.write_incident_command({
        "action": "add",
        "edge_id": req.edge_id,
        "severity": req.severity or "blockage",
        "description": req.description or ""
    })
    return {"status": "ok", "message": f"Incident added on edge {req.edge_id} by {current_user['name']}"}

@app.post("/incident/clear")
def clear_incident(req: IncidentClearRequest, current_user: dict = Depends(require_auth(["admin"]))):
    StateProvider.write_incident_command({
        "action": "clear",
        "edge_id": req.edge_id
    })
    return {"status": "ok", "message": f"Incident clearance issued for edge {req.edge_id} by {current_user['name']}"}

@app.get("/incidents")
def get_incidents():
    state = get_live_state()
    if state and "incidents" in state and state["incidents"]:
        return state["incidents"]
    return StateProvider.get_active_incidents()

@app.post("/sim/control")
def control_sim(req: SimControlRequest, current_user: dict = Depends(require_auth(["admin"]))):
    StateProvider.write_sim_command({
        "action": req.action
    })
    return {"status": "ok", "message": f"Simulation command {req.action} issued by {current_user['name']}"}

@app.get("/trips/history")
def get_trips_history():
    return TripHistoryManager.get_all_trips()

@app.get("/trips/analytics")
def get_trips_analytics():
    return TripHistoryManager.get_analytics_summary()


@app.get("/network/edges")
def get_network_edges():
    road_net_file = os.path.join(static_dir, "RoadNetwork.json")
    if os.path.exists(road_net_file):
        try:
            import json
            with open(road_net_file, "r") as f:
                data = json.load(f)
            edges_summary = []
            for e in data.get("edges", []):
                eid = e.get("id")
                if not eid or eid.startswith(":"):
                    continue
                lanes = e.get("lanes", [])
                length_m = 0
                if lanes and "shape" in lanes[0] and len(lanes[0]["shape"]) >= 2:
                    pts = lanes[0]["shape"]
                    for p_i in range(len(pts)-1):
                        dx = pts[p_i+1]["x"] - pts[p_i]["x"]
                        dy = pts[p_i+1]["y"] - pts[p_i]["y"]
                        length_m += math.hypot(dx, dy)
                edges_summary.append({
                    "id": eid,
                    "edge_id": eid,
                    "length_m": round(length_m, 1),
                    "lane_count": len(lanes),
                    "lanes": len(lanes)
                })
            edges_summary.sort(key=lambda x: str(x["id"]))
            return edges_summary
        except Exception as e:
            print(f"Error loading edges: {e}")
    return []

@app.get("/hospitals/recommend")
def recommend_hospital(start_edge: Optional[str] = "1096889856"):
    project_root = Path(__file__).resolve().parent.parent
    net_file = str(project_root / "simulation" / "mangaluru" / "presentation_selection2.net.xml")
    hosp_file1 = str(project_root / "simulation" / "mangaluru" / "hospitals.add.xml")
    hosp_file2 = str(project_root / "simulation" / "mangaluru" / "presentation_labels.add.xml")
    
    from controller.hospital_manager import HospitalManager
    from controller.astar_router import AStarRouter

    valid_start_edges = ["-26209727#1", "1213225868", "-1154699531", "1096889856"]
    if start_edge not in valid_start_edges:
        start_edge = "1096889856"

    router = AStarRouter()
    state = get_live_state()
    if state and state.get("incidents"):
        for inc in state["incidents"]:
            router.add_incident(inc.get("edge_id"), inc.get("severity", "blockage"))

    hm = HospitalManager(net_file, [hosp_file1, hosp_file2])
    all_hosps = hm.get_all_hospitals()
    
    evaluations = []
    for h in all_hosps:
        if not h.nearest_edge:
            continue
        try:
            route = router.find_route(start_edge, h.nearest_edge)
            if route:
                evaluations.append({
                    "hospital_id": h.id,
                    "hospital_name": h.name,
                    "name": h.name,
                    "nearest_edge": h.nearest_edge,
                    "cost_seconds": round(route.total_cost, 1),
                    "total_cost_s": round(route.total_cost, 1),
                    "estimated_travel_time_s": round(route.estimated_travel_time_s, 1),
                    "distance_meters": round(route.total_distance_m, 1),
                    "total_distance_m": round(route.total_distance_m, 1),
                    "congestion_delay_s": round(route.total_congestion_cost, 1),
                    "signal_delay_s": round(route.total_signal_delay_s, 1),
                    "edge_count": len(route.edge_ids),
                    "summary_explanation": f"ETA: {round(route.total_cost, 1)}s across {len(route.edge_ids)} edges ({round(route.total_distance_m, 1)}m)"
                })
        except Exception:
            pass
            
    if not evaluations:
        return JSONResponse(status_code=404, content={"error": "No routable hospitals found from this origin"})

    evaluations.sort(key=lambda x: x["total_cost_s"])
    best_fastest = evaluations[0]
    shortest_dist = min(evaluations, key=lambda x: x["total_distance_m"])
    
    is_also_shortest = (best_fastest["hospital_id"] == shortest_dist["hospital_id"])
    if is_also_shortest:
        reason = (
            f"Recommended '{best_fastest['hospital_name']}' as both the fastest ETA ({best_fastest['total_cost_s']}s) "
            f"and shortest physical path ({best_fastest['total_distance_m']}m) from selected origin."
        )
    else:
        diff_time = shortest_dist["total_cost_s"] - best_fastest["total_cost_s"]
        reason = (
            f"Recommended '{best_fastest['hospital_name']}' as fastest ETA ({best_fastest['total_cost_s']}s). "
            f"Note: '{shortest_dist['hospital_name']}' is physically shorter ({shortest_dist['total_distance_m']}m vs {best_fastest['total_distance_m']}m) "
            f"but has higher predicted traffic/signal delay (+{diff_time:.1f}s)."
        )

    best_fastest["summary_explanation"] = reason

    return {
        "start_edge": start_edge,
        "fastest_hospital_id": best_fastest["hospital_id"],
        "recommended_hospital_id": best_fastest["hospital_id"],
        "recommended_hospital_name": best_fastest["hospital_name"],
        "shortest_dist_hospital_id": shortest_dist["hospital_id"],
        "shortest_distance_hospital_name": shortest_dist["hospital_name"],
        "estimated_travel_time_s": best_fastest["total_cost_s"],
        "total_distance_m": best_fastest["total_distance_m"],
        "shortest_distance_m": shortest_dist["total_distance_m"],
        "reason": reason,
        "recommendations": evaluations,
        "evaluations": evaluations
    }

@app.get("/experiments/comparison")
def get_experiment_comparison():
    summary_file = os.path.join(os.path.dirname(__file__), "..", "results", "baseline_vs_proposed_kmc_summary.json")
    if not os.path.exists(summary_file):
        return JSONResponse(status_code=404, content={"error": "Comparison data unavailable"})
    try:
        import json
        with open(summary_file, "r") as f:
            data = json.load(f)
        
        # Calculate cross-scenario aggregate metrics
        base_tt = []
        prop_tt = []
        base_wait = []
        prop_wait = []
        total_pairs = 0

        for scen, sc_data in data.items():
            b = sc_data.get("baseline", {})
            p = sc_data.get("proposed", {})
            c = sc_data.get("comparison", {})
            runs = c.get("paired_valid_count", b.get("total_runs", 5))
            total_pairs += runs
            if "mean_travel_time" in b: base_tt.append(b["mean_travel_time"])
            if "mean_travel_time" in p: prop_tt.append(p["mean_travel_time"])
            if "mean_waiting_time" in b: base_wait.append(b["mean_waiting_time"])
            if "mean_waiting_time" in p: prop_wait.append(p["mean_waiting_time"])

        mean_base_tt = sum(base_tt) / len(base_tt) if base_tt else 0.0
        mean_prop_tt = sum(prop_tt) / len(prop_tt) if prop_tt else 0.0
        tt_reduc_pct = ((mean_base_tt - mean_prop_tt) / mean_base_tt * 100.0) if mean_base_tt > 0 else 0.0

        mean_base_wait = sum(base_wait) / len(base_wait) if base_wait else 0.0
        mean_prop_wait = sum(prop_wait) / len(prop_wait) if prop_wait else 0.0
        wait_reduc_pct = ((mean_base_wait - mean_prop_wait) / mean_base_wait * 100.0) if mean_base_wait > 0 else 0.0

        return {
            "source": "Empirical evaluation on Mangaluru Kankanady Corridor (5 paired seeds per scenario)",
            "sample_size": total_pairs,
            "baseline": {
                "mean_travel_time": round(mean_base_tt, 1),
                "mean_waiting_time": round(mean_base_wait, 1)
            },
            "proposed": {
                "mean_travel_time": round(mean_prop_tt, 1),
                "mean_waiting_time": round(mean_prop_wait, 1)
            },
            "improvements": {
                "travel_time_reduction_pct": round(tt_reduc_pct, 1),
                "wait_time_reduction_pct": round(wait_reduc_pct, 1)
            },
            "scenarios": data
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


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

TLS_COORDS_FILE = os.path.join(os.path.dirname(__file__), "..", "controller", "tls_coordinates.json")
_CACHED_TLS_COORDS = None

def get_tls_coordinates():
    global _CACHED_TLS_COORDS
    if _CACHED_TLS_COORDS is None:
        try:
            if os.path.exists(TLS_COORDS_FILE):
                with open(TLS_COORDS_FILE, "r") as f:
                    _CACHED_TLS_COORDS = json.load(f)
            else:
                _CACHED_TLS_COORDS = {}
        except Exception:
            _CACHED_TLS_COORDS = {}
    return _CACHED_TLS_COORDS

@app.get("/signals", response_model=List[SignalState])
def get_signals():
    tls_coords = get_tls_coordinates()
    state = get_live_state()
    live_signals = state.get("signals", []) if state else []
    
    live_state_by_id = {}
    for s in live_signals:
        sid = s.get("id") or s.get("junction_id")
        if sid:
            live_state_by_id[sid] = s.get("state") or s.get("current_state") or "G"
            
    result = []
    for tid, coords in tls_coords.items():
        st = live_state_by_id.get(tid, "G")
        result.append({
            "id": tid,
            "junction_id": tid,
            "state": st,
            "current_state": st,
            "coordinates": coords,
            "x": coords.get("x"),
            "y": coords.get("y"),
            "phase": 0,
            "timestamp": state.get("simulation_time", 0.0) if state else 0.0
        })
    return result

@app.get("/network/signals")
def get_network_signals():
    tls_coords = get_tls_coordinates()
    state = get_live_state()
    live_signals = state.get("signals", []) if state else []
    live_state_by_id = {}
    for s in live_signals:
        sid = s.get("id") or s.get("junction_id")
        if sid:
            live_state_by_id[sid] = s.get("state") or s.get("current_state") or "G"
            
    return [
        {
            "id": tid,
            "junction_id": tid,
            "state": live_state_by_id.get(tid, "G"),
            "current_state": live_state_by_id.get(tid, "G"),
            "coordinates": coords,
            "x": coords.get("x"),
            "y": coords.get("y")
        }
        for tid, coords in tls_coords.items()
    ]

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
