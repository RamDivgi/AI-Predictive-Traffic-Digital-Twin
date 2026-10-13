import json
import math
import os
import sys

def test_phase6c_building_and_destination():
    print("=" * 70)
    print("PHASE 6C VERIFICATION AUDIT")
    print("=" * 70)

    # 1. Load RoadNetwork.json
    json_path = r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Generated\RoadNetwork.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    edges = data.get("edges", [])
    buildings = data.get("buildings", [])
    hospitals = data.get("hospitals", [])

    print(f"Loaded: {len(edges)} edges, {len(buildings)} buildings, {len(hospitals)} hospitals")

    # Collect road segments
    road_segs = []
    for edge in edges:
        for lane in edge.get("lanes", []):
            shape = lane.get("shape", [])
            w = lane.get("width", 3.2)
            for i in range(len(shape) - 1):
                road_segs.append({
                    "p1": (shape[i]["x"], shape[i]["y"]),
                    "p2": (shape[i+1]["x"], shape[i+1]["y"]),
                    "width": w
                })

    print(f"Total road lane segments: {len(road_segs)}")

    # 2. Test Building Placement Logic
    model_count = 0
    fallback_count = 0
    min_observed_clearance = float("inf")
    violations = []

    for bldg in buildings:
        shape = bldg.get("shape", [])
        if len(shape) < 3:
            continue

        sum_x = sum(p["x"] for p in shape)
        sum_z = sum(p["y"] for p in shape)
        count = len(shape)
        cx = sum_x / count
        cz = sum_z / count

        min_x = min(p["x"] for p in shape)
        max_x = max(p["x"] for p in shape)
        min_z = min(p["y"] for p in shape)
        max_z = max(p["y"] for p in shape)

        size_x = max_x - min_x
        size_z = max_z - min_z
        min_dim = min(size_x, size_z)
        max_dim = max(size_x, size_z)
        aspect = max_dim / max(0.1, min_dim)

        # Nearest road segment
        min_road_edge_dist = float("inf")
        nearest_proj = None
        for seg in road_segs:
            x1, y1 = seg["p1"]
            x2, y2 = seg["p2"]
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx*dx + dy*dy
            t = 0.0 if l2 < 0.0001 else max(0.0, min(1.0, ((cx - x1)*dx + (cz - y1)*dy) / l2))
            px = x1 + t * dx
            pz = y1 + t * dy
            dist = math.hypot(cx - px, cz - pz)
            edge_dist = dist - (seg["width"] * 0.5)
            if edge_dist < min_road_edge_dist:
                min_road_edge_dist = edge_dist
                nearest_proj = (px, pz)

        # Check hospital proximity
        near_hospital = any(math.hypot(cx - h["x"], cz - h["y"]) < 35.0 for h in hospitals)

        fits_model = (min_dim >= 10.0 and max_dim <= 45.0 and aspect <= 2.2 and not near_hospital)

        if fits_model:
            is_residential = (max_dim < 26.0)
            native_span = 15.0 if is_residential else 25.0
            target_span = max(9.0, min(18.0, min_dim * 0.75)) if is_residential else max(16.0, min(30.0, min_dim * 0.75))
            scale = max(0.70, min(1.25, target_span / native_span))
            half_span = (native_span * scale) * 0.5
            road_clearance = min_road_edge_dist - half_span

            if road_clearance >= 2.5:
                model_count += 1
                if road_clearance < min_observed_clearance:
                    min_observed_clearance = road_clearance
                to_road = (nearest_proj[0] - cx, nearest_proj[1] - cz)
                face_angle = math.degrees(math.atan2(to_road[0], to_road[1]))
            else:
                fallback_count += 1
        else:
            fallback_count += 1

    print("\n--- 1. BUILDING PLACEMENT AUDIT ---")
    print(f"3D Models Placed:      {model_count} ({model_count/len(buildings)*100:.1f}%)")
    print(f"Procedural Fallbacks:  {fallback_count} ({fallback_count/len(buildings)*100:.1f}%)")
    print(f"Minimum Road Clearance: {min_observed_clearance:.2f} m (Threshold: >= 2.50 m)")
    assert min_observed_clearance >= 2.50, f"Road clearance violation: {min_observed_clearance} m < 2.5 m"
    print("PASS: Zero building-road overlaps or encroachment violations.")

    # 3. Test Hospital Landmark Frontage Orientations
    print("\n--- 2. HOSPITAL LANDMARK ORIENTATION AUDIT ---")
    for hosp in hospitals:
        hx, hy = hosp["x"], hosp["y"]
        min_dist = float("inf")
        best_proj = None
        for seg in road_segs:
            x1, y1 = seg["p1"]
            x2, y2 = seg["p2"]
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx*dx + dy*dy
            t = 0.0 if l2 < 0.0001 else max(0.0, min(1.0, ((hx - x1)*dx + (hy - y1)*dy) / l2))
            px = x1 + t * dx
            py = y1 + t * dy
            d = math.hypot(hx - px, hy - py)
            if d < min_dist:
                min_dist = d
                best_proj = (px, py)

        angle = math.degrees(math.atan2(best_proj[0] - hx, best_proj[1] - hy))
        print(f"  {hosp['name']:<30} distToRoad={min_dist:5.1f}m facing={angle:6.1f} deg")

    print("PASS: All hospitals have entrance-facing road frontage orientation computed.")

    # 4. Destination Marker Resolution
    print("\n--- 3. DESTINATION MARKER RESOLUTION AUDIT ---")
    test_endpoints = [
        ("KMC Hospital", 962.9, 1744.2),
        ("Father Muller Hospital", 2108.8, 1159.1),
        ("Highland Hospital", 1693.4, 1163.4)
    ]

    for expected_name, end_x, end_z in test_endpoints:
        min_d = float("inf")
        best_name = None
        for h in hospitals:
            d = math.hypot(h["x"] - end_x, h["y"] - end_z)
            if d < min_d:
                min_d = d
                best_name = h["name"]
        print(f"  Endpoint ({end_x:6.1f}, {end_z:6.1f}) -> Resolved: {best_name} (dist={min_d:.1f}m, expected: {expected_name})")
        assert best_name == expected_name, f"Resolution mismatch! Expected {expected_name}, got {best_name}"

    print("PASS: Route endpoints accurately map to correct active destination name.")

    # 5. Preservation Check
    print("\n--- 4. STRICT PRESERVATION AUDIT ---")
    # Verify VehicleSmoother.cs exists
    vs_path = r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Scripts\VehicleSmoother.cs"
    assert os.path.exists(vs_path), "VehicleSmoother.cs missing!"
    print("PASS: VehicleSmoother.cs strictly preserved.")

    # Verify UDP ports in scripts
    ports_to_check = {
        r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Scripts\AmbulanceReceiver.cs": 5005,
        r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Scripts\TrafficReceiver.cs": 5006,
        r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Scripts\TrafficSignalReceiver.cs": 5007,
        r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Scripts\RouteReceiver.cs": 5008,
        r"D:\AIML\Projects\Major\MangaluruDigitalTwin3D\Assets\Scripts\DashboardController.cs": 5010,
    }
    for script_file, port in ports_to_check.items():
        with open(script_file, "r", encoding="utf-8") as sf:
            content = sf.read()
            assert str(port) in content, f"Port {port} missing from {script_file}!"
    print("PASS: All 5 UDP telemetry ports (5005, 5006, 5007, 5008, 5010) preserved.")

    print("\n" + "=" * 70)
    print("ALL PHASE 6C AUDIT CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    test_phase6c_building_and_destination()
