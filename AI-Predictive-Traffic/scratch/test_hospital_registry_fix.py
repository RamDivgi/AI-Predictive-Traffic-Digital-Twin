import sys
from pathlib import Path
import math

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from controller.hospital_manager import HospitalManager, AUTHORITATIVE_REGISTRY, EXCLUDED_POIS
from controller.astar_router import AStarRouter
from api.main import app
from fastapi.testclient import TestClient

def main():
    print("=" * 60)
    print("HOSPITAL REGISTRY & SELECTION VERIFICATION TEST")
    print("=" * 60)

    net_file = str(PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml")
    hosp_file1 = str(PROJECT_ROOT / "simulation" / "mangaluru" / "hospitals.add.xml")
    hosp_file2 = str(PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml")

    hm = HospitalManager(net_file, [hosp_file1, hosp_file2])
    all_hospitals = hm.get_all_hospitals()

    print(f"\n1. Loaded {len(all_hospitals)} authoritative destinations:")
    for h in all_hospitals:
        print(f"   [{h.id}] '{h.name}' -> edge: {h.nearest_edge}, type: {h.destination_type}, coord: ({h.x:.1f}, {h.y:.1f})")

    # Check 1: ID 160262590 displays as 'City Hospital'
    h_city = hm.get_hospital("160262590")
    assert h_city is not None, "Hospital 160262590 must exist!"
    assert h_city.name == "City Hospital", f"Expected 'City Hospital', got '{h_city.name}'"
    assert h_city.nearest_edge == "-239271492#3", f"Expected nearest edge -239271492#3, got '{h_city.nearest_edge}'"
    print("\n[PASS] Check 1: ID 160262590 is 'City Hospital' with destination edge -239271492#3.")

    # Check 2: Unwanted generic hospital and clinic labels are excluded
    for excluded in EXCLUDED_POIS:
        # direct lookup should either be None or (in case of alias 'city_hospital') point to 160262590
        if excluded == "city_hospital":
            resolved = hm.get_hospital(excluded)
            assert resolved.id == "160262590", "Alias 'city_hospital' must resolve to '160262590'"
        else:
            assert excluded not in hm.hospitals, f"Excluded POI {excluded} should not be in hospitals dict!"
    for h in all_hospitals:
        assert not h.name.startswith("Hospital ("), f"Generic hospital label found: {h.name}"
        assert not h.name.startswith("Clinic ("), f"Generic clinic label found: {h.name}"
        assert not h.name.startswith("Unknown ("), f"Generic unknown label found: {h.name}"
    print("[PASS] Check 2: Generic and unwanted labels (1203949837, 6938916238, 5867851072, 6938916239) excluded.")

    # Check 3: Duplicate hospital records removed (no duplicate city_hospital in registry)
    hospital_ids = [h.id for h in all_hospitals]
    assert len(hospital_ids) == len(set(hospital_ids)), "Duplicate hospital IDs found in registry!"
    assert "city_hospital" not in hospital_ids, "Legacy ID 'city_hospital' should not be an active list element."
    assert "160262590" in hospital_ids, "160262590 must be the authoritative ID."
    print(f"[PASS] Check 3: No duplicate entries. Exactly {len(all_hospitals)} unique authoritative hospitals present.")

    # Check 4: Valid hospital coordinates within network bounds
    net = hm.net
    bbox = net.getBBoxXY() # ((min_x, min_y), (max_x, max_y))
    print(f"\n   SUMO Network Bounding Box: {bbox}")
    for h in all_hospitals:
        # Allow reasonable vicinity of network
        assert bbox[0][0] - 200 <= h.x <= bbox[1][0] + 200, f"Hospital {h.name} X={h.x} outside network!"
        assert bbox[0][1] - 200 <= h.y <= bbox[1][1] + 200, f"Hospital {h.name} Y={h.y} outside network!"
    print("[PASS] Check 4: All hospital coordinates are within network bounds.")

    # Check 5: Reachability via A* Router from all 4 origins to all destinations
    router = AStarRouter()
    start_edges = ["1096889856", "-26209727#1", "1213225868", "-1154699531"]
    routable_count = 0
    total_checks = len(start_edges) * len(all_hospitals)
    for se in start_edges:
        for h in all_hospitals:
            route = router.find_route(se, h.nearest_edge)
            assert route is not None and len(route.edge_ids) > 0, f"Unroutable pair: {se} -> {h.name} ({h.nearest_edge})"
            routable_count += 1
    assert routable_count == total_checks, f"Expected {total_checks} routable pairs, got {routable_count}"
    print(f"[PASS] Check 5: 100% reachability verified ({routable_count}/{total_checks} pairs successfully routed).")

    # Check 6: FastAPI endpoints (/hospitals, /hospitals/recommend, /trip/start)
    client = TestClient(app)
    
    # 6a. GET /hospitals
    res = client.get("/hospitals")
    assert res.status_code == 200
    hosps_json = res.json()
    assert len(hosps_json) == 11, f"Expected 11 hospitals in API response, got {len(hosps_json)}"
    city_entry = next((h for h in hosps_json if h["id"] == "160262590"), None)
    assert city_entry is not None, "160262590 missing in /hospitals API"
    assert city_entry["name"] == "City Hospital"
    assert city_entry["available"] is True
    assert city_entry["destination_type"] == "hospital"
    print("[PASS] Check 6a: API /hospitals returns exactly 11 valid destinations with City Hospital.")

    # 6b. GET /hospitals/recommend
    res_rec = client.get("/hospitals/recommend?start_edge=1096889856")
    assert res_rec.status_code == 200
    rec_data = res_rec.json()
    assert "recommendations" in rec_data
    assert len(rec_data["recommendations"]) == 11
    # Ensure none of the recommendations have generic names
    for r in rec_data["recommendations"]:
        assert not r["name"].startswith("Hospital (")
        assert not r["name"].startswith("Clinic (")
    print(f"[PASS] Check 6b: API /hospitals/recommend returns {len(rec_data['recommendations'])} valid recommendations; top recommendation: '{rec_data['recommended_hospital_name']}'")

    # 6c. Trip dispatch to City Hospital (160262590)
    res_dispatch = client.post("/trip/start", json={
        "emergency": True,
        "hospital_id": "160262590",
        "start_edge": "1096889856",
        "traffic_scenario": "medium"
    })
    assert res_dispatch.status_code == 200
    assert res_dispatch.json()["status"] == "ok"
    print("[PASS] Check 6c: Dispatch command to '160262590' succeeded.")

    # 6d. Legacy alias lookup works
    h_alias = hm.get_hospital("city_hospital")
    assert h_alias is not None
    assert h_alias.id == "160262590"
    assert h_alias.name == "City Hospital"
    print("[PASS] Check 6d: Legacy alias 'city_hospital' transparently resolves to City Hospital (160262590).")

    # Check 7: Frontend synchronization
    f1 = (PROJECT_ROOT / "api" / "static" / "index.html").read_text(encoding="utf-8")
    f2 = (PROJECT_ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert f1 == f2, "api/static/index.html and dashboard/index.html must be identical!"
    assert "layer-hospitals" in f1, "layer-hospitals toggle must exist in frontend!"
    assert "Hospital (" not in f1, "No hardcoded 'Hospital (' generic labels in frontend!"
    print("[PASS] Check 7: Frontend files api/static/index.html and dashboard/index.html are perfectly synchronized.")

    print("\n" + "=" * 60)
    print("ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    main()
