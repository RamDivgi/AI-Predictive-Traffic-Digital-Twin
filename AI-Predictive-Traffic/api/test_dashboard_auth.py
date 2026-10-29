"""
Automated Validation Test Suite: Dashboard Authentication, RBAC, Dispatch, and Telemetry
Mangaluru Emergency Response AI Digital Twin
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.auth import hash_password, verify_password, DEMO_USERS, create_session, get_session

@pytest.fixture
def client():
    return TestClient(app)

def test_password_hashing():
    raw = "dispatch123"
    hashed = hash_password(raw)
    assert verify_password(raw, hashed) is True
    assert verify_password("wrongpass", hashed) is False
    assert ":" in hashed

def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "simulation_running" in data

def test_demo_accounts_endpoint(client):
    res = client.get("/auth/demo-accounts")
    assert res.status_code == 200
    accounts = res.json()
    assert len(accounts) == 3
    roles = {acc["role"] for acc in accounts}
    assert roles == {"dispatcher", "admin", "viewer"}

def test_login_invalid_credentials(client):
    res = client.post("/auth/login", json={"username": "dispatcher", "password": "wrongpassword"})
    assert res.status_code == 401
    assert "Invalid credentials" in res.json()["detail"]

def test_login_valid_credentials(client):
    res = client.post("/auth/login", json={"username": "dispatcher", "password": "dispatch123"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["username"] == "dispatcher"
    assert data["user"]["role"] == "dispatcher"
    assert "dispatch" in data["user"]["permissions"]

def test_login_with_operator_and_assigned_ambulance(client):
    # Test logging in with operator name and assigned ambulance unit
    res = client.post("/auth/login", json={
        "username": "dispatcher",
        "password": "dispatch123",
        "operator_name": "Ram Divgi",
        "assigned_ambulance": "AMB-02"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["operator_name"] == "Ram Divgi"
    assert data["user"]["assigned_ambulance"] == "AMB-02"

    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify session profile via /auth/me
    me_res = client.get("/auth/me", headers=headers)
    assert me_res.status_code == 200
    me = me_res.json()
    assert me["operator_name"] == "Ram Divgi"
    assert me["assigned_ambulance"] == "AMB-02"

def test_dispatch_uses_session_assigned_ambulance(client):
    # Operator assigned to AMB-02
    res = client.post("/auth/login", json={
        "username": "dispatcher",
        "password": "dispatch123",
        "operator_name": "Ram Divgi",
        "assigned_ambulance": "AMB-02"
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Dispatch request without specifying ambulance_id -> backend auto-assigns session unit AMB-02
    disp_res = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "-26299202#3",
        "start_edge": "1096889856"
    }, headers=headers)
    assert disp_res.status_code == 200
    data = disp_res.json()
    assert data["trip"]["ambulance_id"] == "AMB-02"
    assert data["trip"]["operator_name"] == "Ram Divgi"

def test_dispatch_blocks_tampered_ambulance(client):
    # Operator assigned to AMB-01
    res = client.post("/auth/login", json={
        "username": "dispatcher",
        "password": "dispatch123",
        "operator_name": "Operator A",
        "assigned_ambulance": "AMB-01"
    })
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # If client attempts to maliciously dispatch AMB-03 when assigned to AMB-01 -> 403 Forbidden
    disp_res = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "-26299202#3",
        "ambulance_id": "AMB-03",
        "start_edge": "1096889856"
    }, headers=headers)
    assert disp_res.status_code == 403
    assert "Authorization failure: Account is assigned to AMB-01" in disp_res.json()["detail"]

def test_unauthenticated_dispatch_blocked(client):
    res = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "-26299202#3",
        "start_edge": "1096889856"
    })
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]

def test_viewer_role_dispatch_blocked(client):
    res = client.post("/auth/login", json={"username": "evaluator", "password": "viewer123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "-26299202#3",
        "start_edge": "1096889856"
    }, headers=headers)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]

def test_viewer_role_sim_control_blocked(client):
    res = client.post("/auth/login", json={"username": "evaluator", "password": "viewer123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/sim/control", json={"action": "reset"}, headers=headers)
    assert res.status_code == 403

def test_dispatcher_role_allowed_dispatch(client):
    res = client.post("/auth/login", json={"username": "dispatcher", "password": "dispatch123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "-26299202#3",
        "start_edge": "1096889856",
        "traffic_scenario": "medium"
    }, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "trip" in data

    res = client.post("/trip/stop", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

def test_dispatcher_role_sim_control_blocked(client):
    res = client.post("/auth/login", json={"username": "dispatcher", "password": "dispatch123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/sim/control", json={"action": "reset"}, headers=headers)
    assert res.status_code == 403

def test_admin_role_allowed_sim_control(client):
    res = client.post("/auth/login", json={"username": "traffic_admin", "password": "admin123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post("/sim/control", json={"action": "reset"}, headers=headers)
    assert res.status_code == 200
    assert "Simulation command reset issued" in res.json()["message"]

def test_ambulances_fleet_endpoint(client):
    res = client.get("/ambulances")
    assert res.status_code == 200
    fleet = res.json()
    assert len(fleet) >= 1
    assert fleet[0]["id"] == "AMB-01"

def test_trip_history_and_analytics(client):
    res = client.get("/trips/history")
    assert res.status_code == 200
    history = res.json()
    assert isinstance(history, list)
    assert len(history) > 0

    res = client.get("/trips/analytics")
    assert res.status_code == 200
    an = res.json()
    assert "total_trips" in an
    assert "observed_travel_time" in an
    assert "eta_prediction_metrics" in an
    assert "signal_preemption" in an

def test_logout(client):
    res = client.post("/auth/login", json={"username": "dispatcher", "password": "dispatch123"})
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert get_session(token) is not None

    res = client.post("/auth/logout", headers=headers)
    assert res.status_code == 200

    assert get_session(token) is None

def test_dashboard_html_structure_and_terminology(client):
    res = client.get("/dashboard/")
    assert res.status_code == 200
    html = res.text

    # Exact project title
    assert "<title>AI-Powered Predictive Routing and Signal Preemption in a Digital Twin Environment</title>" in html
    assert "AI-Powered Predictive Routing and Signal Preemption" in html

    # Tab ordering: Dispatch, Live Simulation, Trip History
    nav_start = html.find('id="app-nav"')
    assert nav_start != -1
    nav_end = html.find('</nav>', nav_start)
    nav_html = html[nav_start:nav_end]

    disp_pos = nav_html.find('data-tab="dispatch"')
    sim_pos = nav_html.find('data-tab="simulation"')
    hist_pos = nav_html.find('data-tab="history"')
    assert disp_pos != -1 and sim_pos != -1 and hist_pos != -1
    assert disp_pos < sim_pos < hist_pos, "Navigation tabs not in order: Dispatch -> Simulation -> History"

    # Default active tab is Dispatch
    assert '<button class="nav-tab-btn active" data-tab="dispatch">' in nav_html
    assert '<section class="view-panel active" id="view-dispatch">' in html

    # Emergency Dispatch button
    assert "Emergency Dispatch" in html
    assert 'id="btn-dispatch-ambulance"' in html

    # Signal visualization removed from map layers
    assert 'id="layer-signals"' not in html
    assert "Traffic Signals</label>" not in html

    # One-click demo accounts removed
    assert "One-Click Demo Accounts" not in html
    assert "fillDemo" not in html

def test_signals_backend_operational_after_canvas_removal(client):
    res = client.get("/signals")
    assert res.status_code == 200
    signals = res.json()
    assert isinstance(signals, list)
    assert len(signals) > 0, "Backend traffic signals should remain active for preemption"
    first_sig = signals[0]
    assert "state" in first_sig or "current_state" in first_sig

