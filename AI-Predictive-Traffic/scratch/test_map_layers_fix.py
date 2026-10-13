import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

def test_html_map_layers():
    html_path = Path("api/static/index.html")
    dash_path = Path("dashboard/index.html")

    assert html_path.exists(), "api/static/index.html does not exist"
    assert dash_path.exists(), "dashboard/index.html does not exist"

    content = html_path.read_text(encoding="utf-8")
    dash_content = dash_path.read_text(encoding="utf-8")
    assert content == dash_content, "api/static/index.html and dashboard/index.html must be identical"

    soup = BeautifulSoup(content, "html.parser")

    # 1. Incidents layer checkbox MUST BE ABSENT
    assert soup.find(id="layer-incidents") is None, "layer-incidents checkbox must be removed"
    
    # Check text inside Map Layers section
    map_layers_section = None
    for sec in soup.find_all("section", class_="section-box"):
        h2 = sec.find("h2")
        if h2 and "Map Layers" in h2.get_text():
            map_layers_section = sec
            break
            
    assert map_layers_section is not None, "Map Layers section must exist"
    section_text = map_layers_section.get_text()
    assert "Incidents" not in section_text, "'Incidents' must not appear in Map Layers section"

    # 2. Five operational layers MUST BE PRESENT
    assert soup.find(id="layer-traffic") is not None, "layer-traffic must be present"
    assert soup.find(id="layer-active-route") is not None, "layer-active-route must be present"
    assert soup.find(id="layer-alt-routes") is not None, "layer-alt-routes must be present"
    assert soup.find(id="layer-signals") is not None, "layer-signals must be present"
    assert soup.find(id="layer-hospitals") is not None, "layer-hospitals must be present"

    # 3. Map tooltip container MUST BE PRESENT
    assert soup.find(id="map-tooltip") is not None, "map-tooltip element must be present"

    # 4. Map legend indicators
    legend = soup.find("div", class_="map-legend-box")
    assert legend is not None, "map-legend-box must exist"
    legend_text = legend.get_text()
    assert "Signal" in legend_text, "Signal indicator must be in legend"
    assert "Hospital" in legend_text, "Hospital indicator must be in legend"

    print("HTML Map Layers and UI Verification PASSED!")

def test_backend_markers_data():
    from api.main import app
    client = TestClient(app)

    # 1. Test /hospitals provides valid coordinates
    res_hosps = client.get("/hospitals")
    assert res_hosps.status_code == 200, f"/hospitals failed: {res_hosps.status_code}"
    hosps = res_hosps.json()
    assert len(hosps) >= 3, f"Expected at least 3 hospitals, got {len(hosps)}"
    
    available_hosps = [h for h in hosps if h.get("available")]
    assert len(available_hosps) >= 3, f"Expected at least 3 available hospitals, got {len(available_hosps)}"

    for h in available_hosps:
        assert "coordinates" in h and h["coordinates"] is not None, f"Hospital {h['name']} missing coordinates dict"
        assert "x" in h["coordinates"] and "y" in h["coordinates"], f"Hospital {h['name']} coordinates missing x or y"
        x = h["coordinates"]["x"]
        y = h["coordinates"]["y"]
        assert isinstance(x, (int, float)) and isinstance(y, (int, float)), f"Coordinates for {h['name']} must be numeric"
        # Validate coordinates are within Mangaluru network bounds
        assert 500 <= x <= 3000, f"Hospital {h['name']} x={x} out of Mangaluru network bounds"
        assert 800 <= y <= 3000, f"Hospital {h['name']} y={y} out of Mangaluru network bounds"
        print(f"Verified Hospital: {h['name']} -> ({x}, {y})")

    # 2. Test /signals provides verified 55 TLS controllers with coordinates
    res_sigs = client.get("/signals")
    assert res_sigs.status_code == 200, f"/signals failed: {res_sigs.status_code}"
    signals = res_sigs.json()
    assert len(signals) == 55, f"Expected 55 TLS controllers, got {len(signals)}"

    for s in signals:
        sid = s.get("id") or s.get("junction_id")
        assert sid is not None, "Signal missing identifier"
        assert "coordinates" in s and s["coordinates"] is not None, f"Signal {sid} missing coordinates dict"
        x = s["coordinates"]["x"]
        y = s["coordinates"]["y"]
        assert isinstance(x, (int, float)) and isinstance(y, (int, float)), f"Coordinates for signal {sid} must be numeric"
        assert 500 <= x <= 3000, f"Signal {sid} x={x} out of Mangaluru network bounds"
        assert 800 <= y <= 3000, f"Signal {sid} y={y} out of Mangaluru network bounds"
        assert "state" in s and isinstance(s["state"], str), f"Signal {sid} missing state string"

    print(f"Verified all 55 SUMO TLS controllers with coordinates from /signals!")

    # 3. Test /network/signals endpoint
    res_net_sigs = client.get("/network/signals")
    assert res_net_sigs.status_code == 200, f"/network/signals failed: {res_net_sigs.status_code}"
    net_sigs = res_net_sigs.json()
    assert len(net_sigs) == 55, f"Expected 55 TLS in /network/signals, got {len(net_sigs)}"

    # 4. Check static file tls_coordinates.json
    import json
    tls_json_path = Path("controller/tls_coordinates.json")
    assert tls_json_path.exists(), "controller/tls_coordinates.json must exist"
    with open(tls_json_path) as f:
        tls_data = json.load(f)
    assert len(tls_data) == 55, f"Expected 55 entries in tls_coordinates.json, got {len(tls_data)}"

    # 5. Regression check for Trip APIs
    res_trip = client.post("/trip/start", json={
        "emergency": False,
        "hospital_id": "kmc_hospital",
        "start_edge": "1096889856",
        "traffic_scenario": "medium"
    })
    assert res_trip.status_code == 200 and res_trip.json().get("status") == "ok"

    res_mode = client.post("/trip/mode", json={"emergency": True})
    assert res_mode.status_code == 200 and res_mode.json().get("status") == "ok"

    res_stop = client.post("/trip/stop")
    assert res_stop.status_code == 200 and res_stop.json().get("status") == "ok"

    print("Backend Markers and Regression Verification PASSED!")

if __name__ == "__main__":
    test_html_map_layers()
    test_backend_markers_data()
    print("ALL MAP LAYER VERIFICATIONS PASSED SUCCESSFULLY!")
