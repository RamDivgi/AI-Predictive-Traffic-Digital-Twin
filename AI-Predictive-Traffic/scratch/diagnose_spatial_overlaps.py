import json
import math
from pathlib import Path
from shapely.geometry import Polygon, LineString, MultiPolygon, box
from shapely.ops import unary_union
import shapely

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROAD_NETWORK_JSON = PROJECT_ROOT.parent / "MangaluruDigitalTwin3D" / "Assets" / "Generated" / "RoadNetwork.json"
PREFAB_BOUNDS_JSON = PROJECT_ROOT / "scratch" / "prefab_bounds.json"

def run_diagnostic():
    print("=" * 80)
    print("PHASE 2C SPATIAL GEOMETRY DIAGNOSTIC AUDIT")
    print("=" * 80)

    with open(ROAD_NETWORK_JSON, "r", encoding="utf-8") as f:
        net_data = json.load(f)

    with open(PREFAB_BOUNDS_JSON, "r", encoding="utf-8") as f:
        prefab_data = json.load(f)

    prefab_bounds = {p["name"]: p for p in prefab_data["prefabs"]}

    edges = net_data.get("edges", [])
    junctions = net_data.get("junctions", [])
    buildings = net_data.get("buildings", [])
    hospitals = net_data.get("hospitals", [])

    print(f"Loaded: {len(edges)} edges, {len(junctions)} junctions, {len(buildings)} buildings.")

    # 1. Build Road Polygons & Sidewalk Polygons
    road_polys = []
    sidewalk_polys = []

    for edge in edges:
        lanes = edge.get("lanes", [])
        if not lanes:
            continue
        for l_idx, lane in enumerate(lanes):
            shape = lane.get("shape", [])
            w = lane.get("width", 3.2)
            if len(shape) < 2:
                continue
            line_pts = [(p["x"], p["y"]) for p in shape]
            ls = LineString(line_pts)
            # Lane polygon
            lane_poly = ls.buffer(w * 0.5, cap_style="flat", join_style="mitre")
            if lane_poly.is_valid and not lane_poly.is_empty:
                road_polys.append(lane_poly)

            # Outer sidewalk ribbon (on lane 0 / outer edges)
            if l_idx == 0:
                # Buffer to outer edge + 1.5m sidewalk
                sw_poly = ls.buffer((w * 0.5) + 1.5, cap_style="flat", join_style="mitre")
                if sw_poly.is_valid and not sw_poly.is_empty:
                    sidewalk_polys.append(sw_poly)

    # 2. Build Junction Polygons
    junction_polys = []
    for junc in junctions:
        shape = junc.get("shape", [])
        if len(shape) >= 3:
            pts = [(p["x"], p["y"]) for p in shape]
            j_poly = Polygon(pts)
            if not j_poly.is_valid:
                j_poly = j_poly.buffer(0)
            if j_poly.is_valid and not j_poly.is_empty:
                junction_polys.append(j_poly)

    print(f"Constructed {len(road_polys)} lane polygons, {len(sidewalk_polys)} sidewalk envelopes, {len(junction_polys)} junction polygons.")

    # Unify for fast query
    road_union = unary_union(road_polys)
    junction_union = unary_union(junction_polys)
    road_and_junction_union = unary_union([road_union, junction_union])
    full_corridor_union = unary_union([road_and_junction_union, unary_union(sidewalk_polys)])
    total_exclusion_zone = full_corridor_union.buffer(1.5)

    # 3. Simulate exact Unity placement logic for each building
    res_prefabs = ["Bldg_House01", "Bldg_House02", "Bldg_House05", "Bldg_House07", "Bldg_House11"]
    com_prefabs = ["Bldg_Commercial01", "Bldg_Commercial02", "Bldg_Commercial03", "Bldg_Office01", "Bldg_Office02"]

    # Pre-collect road segments for minRoadEdgeDist logic in Unity
    road_segs = []
    for edge in edges:
        for lane in edge.get("lanes", []):
            s = lane.get("shape", [])
            w = lane.get("width", 3.2)
            for i in range(len(s) - 1):
                road_segs.append(((s[i]["x"], s[i]["y"]), (s[i+1]["x"], s[i+1]["y"]), w))

    overlapping_road_count = 0
    overlapping_junction_count = 0
    overlapping_sidewalk_count = 0
    clearance_violations_count = 0
    total_offending_buildings = []

    for idx, bldg in enumerate(buildings):
        bid = bldg.get("id", f"bldg_{idx}")
        bshape = bldg.get("shape", [])
        if len(bshape) < 3:
            continue

        b_pts = [(p["x"], p["y"]) for p in bshape]
        src_poly = Polygon(b_pts)
        if not src_poly.is_valid:
            src_poly = src_poly.buffer(0)

        cx = sum(p[0] for p in b_pts) / len(b_pts)
        cy = sum(p[1] for p in b_pts) / len(b_pts)
        min_x = min(p[0] for p in b_pts)
        max_x = max(p[0] for p in b_pts)
        min_y = min(p[1] for p in b_pts)
        max_y = max(p[1] for p in b_pts)

        size_x = max_x - min_x
        size_y = max_y - min_y
        min_dim = min(size_x, size_y)
        max_dim = max(size_x, size_y)
        aspect = max_dim / max(0.1, min_dim)

        # minRoadEdgeDist in Unity
        min_edge_dist = float("inf")
        nearest_proj = (0, 0)
        for (x1, y1), (x2, y2), w in road_segs:
            dx = x2 - x1
            dy = y2 - y1
            l2 = dx*dx + dy*dy
            t = 0.0 if l2 < 0.0001 else max(0.0, min(1.0, ((cx - x1)*dx + (cy - y1)*dy) / l2))
            px = x1 + t * dx
            py = y1 + t * dy
            d = math.hypot(cx - px, cy - py)
            ed = d - (w * 0.5)
            if ed < min_edge_dist:
                min_edge_dist = ed
                nearest_proj = (px, py)

        near_hosp = any(math.hypot(cx - h["x"], cy - h["y"]) < 35.0 for h in hospitals)
        fits_model = (min_dim >= 10.0 and max_dim <= 45.0 and aspect <= 2.2 and not near_hosp)

        # Determine if Unity placed a 3D model or procedural
        model_placed = False
        final_poly = None
        model_name = None

        if fits_model:
            btype = bldg.get("building_type", "residential")
            prefer_com = btype in ["commercial", "office", "retail"]
            prefer_res = btype in ["house", "residential"]

            if prefer_com:
                chosen = com_prefabs[(hash(bid) & 0x7FFFFFFF) % len(com_prefabs)]
            elif prefer_res or max_dim < 26.0:
                chosen = res_prefabs[(hash(bid) & 0x7FFFFFFF) % len(res_prefabs)]
            else:
                chosen = com_prefabs[(hash(bid) & 0x7FFFFFFF) % len(com_prefabs)]

            pb = prefab_bounds[chosen]
            # Scale prefab to fit inside parcel bounds
            scale_w = size_x / max(1.0, pb["sizeX"])
            scale_d = size_y / max(1.0, pb["sizeZ"])
            scale = max(0.55, min(1.10, min(scale_w, scale_d) * 0.90))

            if bldg.get("is_infill") and abs(bldg.get("facing", 0)) > 0.01:
                facing_deg = bldg["facing"]
            else:
                facing_deg = math.degrees(math.atan2(nearest_proj[0] - cx, nearest_proj[1] - cy))

            p_min_x, p_max_x = pb["minX"] * scale, pb["maxX"] * scale
            p_min_z, p_max_z = pb["minZ"] * scale, pb["maxZ"] * scale
            rad = math.radians(facing_deg)
            cos_a, sin_a = math.cos(rad), math.sin(rad)

            local_corners = [
                (p_min_x, p_min_z),
                (p_max_x, p_min_z),
                (p_max_x, p_max_z),
                (p_min_x, p_max_z)
            ]
            world_corners = []
            for lx, lz in local_corners:
                wx = cx + (lx * cos_a + lz * sin_a)
                wz = cy + (-lx * sin_a + lz * cos_a)
                world_corners.append((wx, wz))

            test_model_poly = Polygon(world_corners)

            # Check if rotated 3D model maintains >= 2.0m clearance to roads & junctions
            if not test_model_poly.intersects(total_exclusion_zone):
                model_placed = True
                model_name = chosen
                final_poly = test_model_poly

        if not model_placed:
            # Procedural building uses src_poly (strictly bounded)
            final_poly = src_poly

        if not final_poly.is_valid:
            final_poly = final_poly.buffer(0)

        # Check intersection with road lane surfaces
        hits_road = final_poly.intersects(road_union)
        hits_junction = final_poly.intersects(junction_union)
        hits_sidewalk = final_poly.intersects(full_corridor_union)

        # Minimum distance to road surface
        dist_to_road_surface = final_poly.distance(road_union)
        dist_to_junction = final_poly.distance(junction_union)
        actual_min_clearance = min(dist_to_road_surface, dist_to_junction)

        is_violating = hits_road or hits_junction or (actual_min_clearance < 2.0)

        if hits_road:
            overlapping_road_count += 1
        if hits_junction:
            overlapping_junction_count += 1
        if hits_sidewalk:
            overlapping_sidewalk_count += 1
        if actual_min_clearance < 2.0:
            clearance_violations_count += 1

        if is_violating:
            overlap_area_road = final_poly.intersection(road_union).area if hits_road else 0.0
            overlap_area_junc = final_poly.intersection(junction_union).area if hits_junction else 0.0
            total_offending_buildings.append({
                "id": bid,
                "type": bldg.get("building_type", "unknown"),
                "is_infill": bldg.get("is_infill", False),
                "source": bldg.get("source", "unknown"),
                "model_placed": model_placed,
                "model_name": model_name,
                "hits_road": hits_road,
                "hits_junction": hits_junction,
                "overlap_area_m2": round(overlap_area_road + overlap_area_junc, 2),
                "actual_clearance_m": round(actual_min_clearance, 2),
                "centroid": (round(cx, 1), round(cy, 1))
            })

    print("\n" + "=" * 80)
    print("AUDIT FINDINGS:")
    print(f"Total Buildings Checked:              {len(buildings)}")
    print(f"Buildings Physically Intersecting Roads:     {overlapping_road_count}")
    print(f"Buildings Physically Intersecting Junctions: {overlapping_junction_count}")
    print(f"Buildings Encroaching On Sidewalks:          {overlapping_sidewalk_count}")
    print(f"Buildings with Clearance < 2.0m:             {clearance_violations_count}")
    print(f"Total Offending Buildings:                   {len(total_offending_buildings)}")
    print("=" * 80)

    # Breakdown by source
    infill_offenders = [b for b in total_offending_buildings if b["is_infill"]]
    osm_offenders = [b for b in total_offending_buildings if not b["is_infill"]]
    print(f"\nOffender Breakdown:")
    print(f"  Frontage Infill Offenders: {len(infill_offenders)} / {sum(1 for b in buildings if b.get('is_infill'))}")
    print(f"  Authentic OSM Offenders:   {len(osm_offenders)} / {sum(1 for b in buildings if not b.get('is_infill'))}")

    # Top 10 worst offenders
    total_offending_buildings.sort(key=lambda x: x["overlap_area_m2"], reverse=True)
    print("\nTop 10 Worst Encroachments:")
    for b in total_offending_buildings[:10]:
        print(f"  ID: {b['id']:<30} | Infill: {str(b['is_infill']):<5} | Area: {b['overlap_area_m2']:>6.1f} m² | RoadHit: {b['hits_road']} | JuncHit: {b['hits_junction']} | Pos: {b['centroid']}")

    # Save diagnostic results
    out_file = PROJECT_ROOT / "scratch" / "spatial_overlap_diagnostic.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_buildings": len(buildings),
            "intersecting_roads": overlapping_road_count,
            "intersecting_junctions": overlapping_junction_count,
            "encroaching_sidewalks": overlapping_sidewalk_count,
            "total_offending": len(total_offending_buildings),
            "offenders": total_offending_buildings
        }, f, indent=2)
    print(f"\nDetailed diagnostic written to: {out_file}")

if __name__ == "__main__":
    run_diagnostic()
