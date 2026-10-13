import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

def test_html_refinements():
    html_path = Path("api/static/index.html")
    assert html_path.exists(), "api/static/index.html does not exist"
    
    dash_html_path = Path("dashboard/index.html")
    assert dash_html_path.exists(), "dashboard/index.html does not exist"

    content = html_path.read_text(encoding="utf-8")
    dash_content = dash_html_path.read_text(encoding="utf-8")
    assert content == dash_content, "dashboard/index.html and api/static/index.html must be synchronized"

    soup = BeautifulSoup(content, "html.parser")

    # 1. Road Incidents section and controls MUST BE REMOVED from HTML
    assert soup.find(id="sel-incident-edge") is None, "sel-incident-edge must be removed"
    assert soup.find(id="sel-incident-severity") is None, "sel-incident-severity must be removed"
    assert soup.find(id="input-incident-desc") is None, "input-incident-desc must be removed"
    assert soup.find(id="btn-add-incident") is None, "btn-add-incident must be removed"
    assert soup.find(id="btn-clear-incidents") is None, "btn-clear-incidents must be removed"
    assert soup.find(id="incident-count") is None, "incident-count must be removed"
    
    # Text headers
    left_sidebar = soup.find("aside", class_="panel-sidebar")
    assert left_sidebar is not None, "Left sidebar must exist"
    sidebar_text = left_sidebar.get_text()
    assert "Road Incidents" not in sidebar_text, "Road Incidents heading must not appear in sidebar"
    assert "Road Incident Management" not in sidebar_text, "Road Incident Management heading must not appear in sidebar"

    # 2. Simulation control buttons MUST BE REMOVED from top navigation
    assert soup.find(id="btn-sim-resume") is None, "btn-sim-resume must be removed"
    assert soup.find(id="btn-sim-pause") is None, "btn-sim-pause must be removed"
    assert soup.find(id="btn-sim-reset") is None, "btn-sim-reset must be removed"
    
    # Top bar should retain telemetry and status
    top_bar = soup.find("header", class_="top-bar")
    assert top_bar is not None, "Top navigation bar must exist"
    assert soup.find(id="item-ws") is not None, "WebSocket status must be retained"
    assert soup.find(id="item-sim") is not None, "SUMO status must be retained"
    assert soup.find(id="val-sim-time") is not None, "Simulation time must be retained"
    assert soup.find(id="val-nav-scenario") is not None, "Scenario display must be retained"

    # 3. Emergency Mode Toggle
    assert soup.find(id="emergency-mode-toggle") is not None, "emergency-mode-toggle container must exist"
    btn_off = soup.find(id="btn-mode-off")
    btn_on = soup.find(id="btn-mode-on")
    mode_label = soup.find(id="emergency-mode-label")
    assert btn_off is not None, "btn-mode-off must exist"
    assert btn_on is not None, "btn-mode-on must exist"
    assert mode_label is not None, "emergency-mode-label must exist"
    
    # Initial state must be OFF
    assert "active" in btn_off.get("class", []), "btn-mode-off must have active class by default"
    assert "active" not in btn_on.get("class", []), "btn-mode-on must not have active class by default"
    assert "Emergency mode: OFF" in mode_label.get_text(), "Initial label must be 'Emergency mode: OFF'"

    # Old checkbox must NOT exist
    assert soup.find(id="chk-green-corridor") is None, "Old Green Corridor checkbox must be removed"

    # 4. Emergency Dispatch controls MUST BE RETAINED
    assert soup.find(id="sel-origin") is not None, "Origin selector must be retained"
    assert soup.find(id="sel-hospital") is not None, "Hospital selector must be retained"
    assert soup.find(id="btn-ai-recommend") is not None, "Recommend destination button must be retained"
    assert soup.find(id="sel-scenario") is not None, "Traffic scenario selector must be retained"
    assert soup.find(id="btn-start-trip") is not None, "Dispatch button must be retained"
    assert soup.find(id="btn-stop-trip") is not None, "Abort button must be retained"

    # 5. Map Layers MUST BE RETAINED in sidebar
    assert soup.find(id="layer-traffic") is not None, "Traffic layer toggle must be retained"
    assert soup.find(id="layer-active-route") is not None, "Active route layer toggle must be retained"
    assert soup.find(id="layer-alt-routes") is not None, "Alt routes layer toggle must be retained"
    assert soup.find(id="layer-signals") is not None, "Signals layer toggle must be retained"
    assert soup.find(id="layer-hospitals") is not None, "Hospitals layer toggle must be retained"
    assert soup.find(id="layer-incidents") is None, "Incidents layer toggle must be removed"

    print("HTML Verification PASSED!")

def test_backend_api_integrity():
    # Import api.main and run test client checks
    from api.main import app
    client = TestClient(app)

    # 1. Incident endpoints must still exist and work
    res_inc = client.get("/incidents")
    assert res_inc.status_code == 200, f"/incidents failed: {res_inc.status_code}"
    assert isinstance(res_inc.json(), list), "/incidents should return a list"

    # Add an incident
    res_add = client.post("/incident/add", json={
        "edge_id": "test_edge_123",
        "severity": "high",
        "description": "Verification Incident"
    })
    assert res_add.status_code == 200, f"/incident/add failed: {res_add.status_code}"
    
    # Check it exists in list
    res_inc2 = client.get("/incidents")
    incidents = res_inc2.json()
    assert any(i["edge_id"] == "test_edge_123" for i in incidents), "Added incident must be in list"

    # Clear incident
    res_clear = client.post("/incident/clear", json={"edge_id": "test_edge_123"})
    assert res_clear.status_code == 200, f"/incident/clear failed: {res_clear.status_code}"

    # 2. Simulation control endpoint must still exist
    res_sim = client.post("/sim/control", json={"action": "resume"})
    assert res_sim.status_code == 200, f"/sim/control failed: {res_sim.status_code}"

    # 3. Trip endpoints: /trip/start with emergency: False and True
    res_trip_off = client.post("/trip/start", json={
        "emergency": False,
        "hospital_id": "KMC_Hospital_Ambedkar_Circle",
        "start_edge": "E0",
        "traffic_scenario": "medium"
    })
    assert res_trip_off.status_code == 200, f"/trip/start with emergency=False failed: {res_trip_off.status_code}"
    assert res_trip_off.json().get("status") == "ok"

    # Trip mode switch endpoint: /trip/mode
    res_mode_on = client.post("/trip/mode", json={"emergency": True})
    assert res_mode_on.status_code == 200, f"/trip/mode with emergency=True failed: {res_mode_on.status_code}"
    assert res_mode_on.json().get("status") == "ok"

    res_mode_off = client.post("/trip/mode", json={"emergency": False})
    assert res_mode_off.status_code == 200, f"/trip/mode with emergency=False failed: {res_mode_off.status_code}"
    assert res_mode_off.json().get("status") == "ok"

    # Trip stop
    res_stop = client.post("/trip/stop")
    assert res_stop.status_code == 200, f"/trip/stop failed: {res_stop.status_code}"

    # Trip start with emergency: True
    res_trip_on = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "Father_Mullers_Hospital",
        "start_edge": "E0",
        "traffic_scenario": "high"
    })
    assert res_trip_on.status_code == 200, f"/trip/start with emergency=True failed: {res_trip_on.status_code}"

    # Trip stop again to clean up
    client.post("/trip/stop")

    # 4. Hospitals & Starting Points
    res_hosps = client.get("/hospitals")
    assert res_hosps.status_code == 200
    assert len(res_hosps.json()) >= 3

    res_starts = client.get("/starting-points")
    assert res_starts.status_code == 200
    assert len(res_starts.json()) >= 3

    print("Backend API Integrity Verification PASSED!")

if __name__ == "__main__":
    test_html_refinements()
    test_backend_api_integrity()
    print("ALL TESTS PASSED SUCCESSFULLY!")
