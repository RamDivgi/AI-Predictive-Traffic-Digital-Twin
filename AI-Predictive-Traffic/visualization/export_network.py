import os
import sys
import json
import math
import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
import sumolib

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_NET_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"
OSM_LIVE_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "osm_buildings_live.json"
POLY_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "osm.poly.xml.gz"
LABELS_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"

OUTPUT_FILES = [
    PROJECT_ROOT / "visualization" / "RoadNetwork.json",
    PROJECT_ROOT / "dashboard" / "RoadNetwork.json",
    PROJECT_ROOT / "api" / "static" / "RoadNetwork.json",
    PROJECT_ROOT.parent / "MangaluruDigitalTwin3D" / "Assets" / "Generated" / "RoadNetwork.json"
]

SIDEWALK_WIDTH = 1.50   # Standard raised concrete sidewalk
SAFETY_MARGIN = 2.00    # Minimum horizontal safety buffer to any road/sidewalk/junction

def export_network():
    print("=" * 80)
    print("PHASE 2C: FOOTPRINT-BASED SPATIAL VALIDATION & ROAD CLEARANCE EXPORT")
    print("=" * 80)
    print(f"Loading SUMO network from: {SUMO_NET_FILE}")
    if not SUMO_NET_FILE.exists():
        print("Network file not found!")
        return

    net = sumolib.net.readNet(str(SUMO_NET_FILE))
    (min_x, min_y), (max_x, max_y) = net.getBBoxXY()

    # 1. Export Roads (Edges) and Construct 2D Polygons
    roads = []
    road_polys = []
    sidewalk_polys = []
    road_clearance_polys = []
    arterial_edge_ids = set()

    for edge in net.getEdges():
        if edge.getFunction() == "internal":
            continue

        eid = edge.getID()
        name = edge.getName() or ""
        speed = edge.getSpeed()
        lanes = edge.getLanes()

        if any(k in name.lower() for k in ['balmatta', 'teresa', 'muller', 'falnir', 'jyothi', 'bendoor', 'collector']) or speed > 11.0:
            arterial_edge_ids.add(eid)

        edge_data = {
            "id": eid,
            "name": name,
            "speed": speed,
            "lanes": []
        }

        for l_idx, lane in enumerate(lanes):
            shape = lane.getShape()
            w = lane.getWidth()
            lane_data = {
                "id": lane.getID(),
                "width": w,
                "shape": [{"x": round(p[0], 2), "y": round(p[1], 2)} for p in shape]
            }
            edge_data["lanes"].append(lane_data)

            if len(shape) >= 2:
                ls = LineString(shape)
                # Exact lane surface
                lp = ls.buffer(w * 0.5, cap_style="flat", join_style="mitre")
                if lp.is_valid and not lp.is_empty:
                    road_polys.append(lp)

                # Outer lane sidewalk ribbon & clearance buffer
                clear_p = ls.buffer((w * 0.5) + SIDEWALK_WIDTH + SAFETY_MARGIN, cap_style="flat", join_style="mitre")
                if clear_p.is_valid and not clear_p.is_empty:
                    road_clearance_polys.append(clear_p)

        roads.append(edge_data)

    print(f"Exported {len(roads)} road edges ({len(road_polys)} lane polygons).")

    # 2. Export Junctions and Construct 2D Polygons
    junctions = []
    junction_polys = []
    junction_clearance_polys = []

    for node in net.getNodes():
        shape = node.getShape()
        if shape and len(shape) >= 3:
            junctions.append({
                "id": node.getID(),
                "shape": [{"x": round(p[0], 2), "y": round(p[1], 2)} for p in shape],
                "x": round(node.getCoord()[0], 2),
                "y": round(node.getCoord()[1], 2)
            })

            jp = Polygon(shape)
            if not jp.is_valid:
                jp = jp.buffer(0)
            if jp.is_valid and not jp.is_empty:
                junction_polys.append(jp)
                jc = jp.buffer(SAFETY_MARGIN)
                if jc.is_valid and not jc.is_empty:
                    junction_clearance_polys.append(jc)

    print(f"Exported {len(junctions)} junctions ({len(junction_polys)} 2D polygons).")

    # Unified geometric representations for spatial queries
    road_union = unary_union(road_polys)
    junction_union = unary_union(junction_polys)
    road_and_junction_surface = unary_union([road_union, junction_union])
    total_exclusion_zone = unary_union(road_clearance_polys + junction_clearance_polys)

    # 3. Export Traffic Lights
    traffic_lights = []
    for tl in net.getTrafficLights():
        tl_id = tl.getID()
        controlled_nodes = set()
        controlled_links = []

        for link_idx, conn_list in tl.getLinks().items():
            for conn in conn_list:
                from_lane = conn[0]
                to_lane = conn[1]
                node = from_lane.getEdge().getToNode()
                controlled_nodes.add(node)
                controlled_links.append({
                    "link_index": link_idx,
                    "from_lane": from_lane.getID(),
                    "to_lane": to_lane.getID(),
                    "junction": node.getID()
                })

        if controlled_nodes:
            cx = sum(n.getCoord()[0] for n in controlled_nodes) / len(controlled_nodes)
            cy = sum(n.getCoord()[1] for n in controlled_nodes) / len(controlled_nodes)
        else:
            cx, cy = 0.0, 0.0

        traffic_lights.append({
            "id": tl_id,
            "x": round(cx, 2),
            "y": round(cy, 2),
            "controlled_junctions": [n.getID() for n in controlled_nodes],
            "controlled_links": controlled_links
        })

    print(f"Exported {len(traffic_lights)} traffic light controllers.")

    # 4. Export Hospitals
    AUTHORITATIVE_NAMES = {
        "highland_hospital": "Highland Hospital",
        "kmc_hospital": "KMC Hospital",
        "father_muller_hospital": "Father Muller Hospital",
        "160262590": "City Hospital",
        "calaco_hospital": "Calaco Hospital",
        "scs_hospital": "SCS Hospital",
        "unity_hospital": "Unity Hospital",
        "indira_hospital": "Indira Hospital",
        "athena_hospital": "Athena Hospital",
        "vijaya_clinic_general_hospital": "Vijaya Clinic General Hospital",
        "mangalore_nursing_home": "Mangalore Nursing Home",
        "1203949837": "Omega Hospital",
        "5867851072": "Mourishka Clinic",
        "6938916238": "Bunder Health Center",
        "6938916239": "Kodialbail Clinic"
    }

    hospitals = []
    hospital_coords = []
    if LABELS_FILE.exists():
        tree = ET.parse(str(LABELS_FILE))
        root = tree.getroot()
        for poi in root.findall('poi'):
            if poi.get("type") == "hospital":
                hx = float(poi.get("x", 0))
                hy = float(poi.get("y", 0))
                pid = poi.get("id")
                if min_x <= hx <= max_x and min_y <= hy <= max_y:
                    hospitals.append({
                        "id": pid,
                        "name": AUTHORITATIVE_NAMES.get(pid, poi.get("name", "Hospital")),
                        "x": round(hx, 2),
                        "y": round(hy, 2)
                    })
                    hospital_coords.append((hx, hy))

    print(f"Exported {len(hospitals)} hospital landmarks.")

    # 5. Ingest Authentic OpenStreetMap Footprints & Rigorous Spatial Validation
    buildings = []
    placed_polygons = []
    source_conflicts = []

    # 5a. Ingest Live OSM Buildings
    if OSM_LIVE_FILE.exists():
        with open(str(OSM_LIVE_FILE), "r", encoding="utf-8") as f:
            osm_data = json.load(f)
        nodes = {e["id"]: (e["lon"], e["lat"]) for e in osm_data.get("elements", []) if e.get("type") == "node"}
        ways = [e for e in osm_data.get("elements", []) if e.get("type") == "way" and "building" in e.get("tags", {})]

        for w in ways:
            pts = [nodes[nid] for nid in w.get("nodes", []) if nid in nodes]
            if len(pts) >= 3:
                sumo_pts = [{'x': round(p[0], 2), 'y': round(p[1], 2)} for p in [net.convertLonLat2XY(lon, lat) for lon, lat in pts]]
                cx = sum(p["x"] for p in sumo_pts) / len(sumo_pts)
                cy = sum(p["y"] for p in sumo_pts) / len(sumo_pts)

                if min_x <= cx <= max_x and min_y <= cy <= max_y:
                    b_poly = Polygon([(p["x"], p["y"]) for p in sumo_pts])
                    if not b_poly.is_valid:
                        b_poly = b_poly.buffer(0)
                    if b_poly.is_empty:
                        continue

                    tags = w.get("tags", {})
                    bid = f"osm_way_{w['id']}"

                    # Strict footprint collision check against roads and junctions
                    hits_road = b_poly.intersects(road_union)
                    hits_junc = b_poly.intersects(junction_union)
                    dist_road = b_poly.distance(road_and_junction_surface)
                    is_conflict = hits_road or hits_junc or (dist_road < 1.50)

                    bldg_entry = {
                        "id": bid,
                        "name": tags.get("name", ""),
                        "building_type": tags.get("building", "yes"),
                        "levels": int(tags["building:levels"]) if tags.get("building:levels", "").isdigit() else None,
                        "shape": sumo_pts,
                        "is_infill": False,
                        "source": "osm"
                    }

                    if is_conflict:
                        overlap_area = (b_poly.intersection(road_union).area if hits_road else 0.0) + \
                                       (b_poly.intersection(junction_union).area if hits_junc else 0.0)
                        bldg_entry["conflict"] = {
                            "type": "source_data_road_encroachment",
                            "hits_road": hits_road,
                            "hits_junction": hits_junc,
                            "overlap_area_m2": round(overlap_area, 2),
                            "clearance_m": round(dist_road, 2)
                        }
                        source_conflicts.append(bldg_entry)

                    placed_polygons.append(b_poly)
                    buildings.append(bldg_entry)

    # 5b. Ingest Polygons & Parks from osm.poly.xml.gz
    parks = []
    if POLY_FILE.exists():
        with gzip.open(str(POLY_FILE), 'rt') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            for poly in root.findall('poly'):
                ptype = poly.get("type", "")
                shape_str = poly.get("shape", "")
                if not shape_str:
                    continue
                pts = []
                for pt in shape_str.split():
                    c = pt.split(",")
                    if len(c) >= 2:
                        pts.append({"x": round(float(c[0]), 2), "y": round(float(c[1]), 2)})
                if len(pts) < 3:
                    continue
                cx = sum(p["x"] for p in pts) / len(pts)
                cy = sum(p["y"] for p in pts) / len(pts)
                if not (min_x <= cx <= max_x and min_y <= cy <= max_y):
                    continue

                if "building" in ptype:
                    pid = poly.get("id")
                    is_dup = any(abs(b["shape"][0]["x"] - pts[0]["x"]) < 5.0 and abs(b["shape"][0]["y"] - pts[0]["y"]) < 5.0 for b in buildings)
                    if not is_dup:
                        b_poly = Polygon([(p["x"], p["y"]) for p in pts])
                        if not b_poly.is_valid:
                            b_poly = b_poly.buffer(0)
                        if b_poly.is_empty:
                            continue

                        hits_road = b_poly.intersects(road_union)
                        hits_junc = b_poly.intersects(junction_union)
                        dist_road = b_poly.distance(road_and_junction_surface)
                        is_conflict = hits_road or hits_junc or (dist_road < 1.50)

                        bldg_entry = {
                            "id": pid,
                            "name": "",
                            "building_type": ptype.replace("building.", ""),
                            "levels": None,
                            "shape": pts,
                            "is_infill": False,
                            "source": "osm_poly"
                        }

                        if is_conflict:
                            overlap_area = (b_poly.intersection(road_union).area if hits_road else 0.0) + \
                                           (b_poly.intersection(junction_union).area if hits_junc else 0.0)
                            bldg_entry["conflict"] = {
                                "type": "source_data_road_encroachment",
                                "hits_road": hits_road,
                                "hits_junction": hits_junc,
                                "overlap_area_m2": round(overlap_area, 2),
                                "clearance_m": round(dist_road, 2)
                            }
                            source_conflicts.append(bldg_entry)

                        placed_polygons.append(b_poly)
                        buildings.append(bldg_entry)

                elif any(k in ptype for k in ['park', 'garden', 'pitch', 'meadow', 'wood', 'grass', 'nature']):
                    parks.append({
                        "id": poly.get("id"),
                        "type": ptype,
                        "shape": pts
                    })

    print(f"Loaded {len(buildings)} authentic building footprints ({len(source_conflicts)} documented source data conflicts).")
    print(f"Exported {len(parks)} parks and green spaces.")

    # 5c. Match Hospitals to Authentic OSM Footprints and Tag Hospital Sites
    matched_osm_count = 0
    for hosp in hospitals:
        hx, hy = hosp["x"], hosp["y"]
        best_bldg = None
        best_dist = float("inf")
        for bldg in buildings:
            pts = bldg["shape"]
            cx = sum(p["x"] for p in pts) / len(pts)
            cy = sum(p["y"] for p in pts) / len(pts)
            d = math.hypot(hx - cx, hy - cy)
            if d < best_dist:
                best_dist = d
                best_bldg = bldg
        if best_bldg and best_dist < 35.0:
            hosp["matched_building_id"] = best_bldg["id"]
            xs = [p["x"] for p in best_bldg["shape"]]
            ys = [p["y"] for p in best_bldg["shape"]]
            hosp["footprint_width"] = round(max(xs) - min(xs), 2)
            hosp["footprint_depth"] = round(max(ys) - min(ys), 2)
            best_bldg["is_hospital_site"] = True
            matched_osm_count += 1

    print(f"Matched {matched_osm_count}/{len(hospitals)} hospitals to authentic OSM building footprints.")

    # 6. Generate Street-Frontage Urban Infill Parcels with Footprint-Based Validation & Parcel Relocation
    parcel_step = 22.0
    accepted_direct = 0
    corrected_relocated = 0
    rejected_count = 0

    all_placed_polys = list(placed_polygons)
    spatial_index = STRtree(all_placed_polys)

    for edge in net.getEdges():
        if edge.getFunction() == "internal":
            continue
        eid = edge.getID()
        lanes = edge.getLanes()
        if not lanes:
            continue
        shape = lanes[0].getShape()
        total_w = sum(l.getWidth() for l in lanes)
        is_arterial = eid in arterial_edge_ids

        # Building footprint dimensions
        b_width = 14.0 if not is_arterial else 18.0
        b_depth = 12.0 if not is_arterial else 15.0
        hw = b_width * 0.5
        hd = b_depth * 0.5

        for i in range(len(shape) - 1):
            p1 = shape[i]
            p2 = shape[i+1]
            seg_dx = p2[0] - p1[0]
            seg_dy = p2[1] - p1[1]
            seg_len = math.hypot(seg_dx, seg_dy)
            if seg_len < 16.0:
                continue

            ux = seg_dx / seg_len
            uy = seg_dy / seg_len
            nlx, nly = -uy, ux
            nrx, nry = uy, -ux

            num_slots = int(seg_len / parcel_step)
            for s in range(num_slots):
                dist_along = (s + 0.5) * parcel_step
                base_x = p1[0] + ux * dist_along
                base_y = p1[1] + uy * dist_along

                for side, (nx, ny) in [('L', (nlx, nly)), ('R', (nrx, nry))]:
                    facing_deg = math.degrees(math.atan2(-nx, -ny))
                    rad = math.radians(facing_deg)
                    cos_a = math.cos(rad)
                    sin_a = math.sin(rad)

                    # Initial setback from road centerline:
                    # Half road width + sidewalk (1.5m) + safety margin (2.0m) + building half depth + buffer
                    base_setback = (total_w * 0.5) + SIDEWALK_WIDTH + SAFETY_MARGIN + hd + 1.0

                    candidate_accepted = False
                    accepted_poly = None
                    accepted_pts = None
                    was_relocated = False

                    # Test candidate at base setback, or relocate deeper into parcel (+2.5m, +5.0m, +7.5m, +10.0m)
                    for shift in [0.0, 2.5, 5.0, 7.5, 10.0]:
                        cur_setback = base_setback + shift
                        bx = base_x + nx * cur_setback
                        by = base_y + ny * cur_setback

                        # Boundary bounds check
                        if not (min_x + 15 <= bx <= max_x - 15 and min_y + 15 <= by <= max_y - 15):
                            continue

                        # Compute 4 footprint corners
                        corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
                        fp_pts = []
                        for cx_loc, cy_loc in corners:
                            gx = bx + (cx_loc * cos_a - cy_loc * sin_a)
                            gy = by + (cx_loc * sin_a + cy_loc * cos_a)
                            fp_pts.append((gx, gy))

                        cand_poly = Polygon(fp_pts)

                        # Hospital entrance & ambulance apron preservation (footprint distance >= 35m)
                        if any(cand_poly.distance(Point(hx, hy)) < 35.0 for hx, hy in hospital_coords):
                            continue

                        # Test A: Zero intersection with road or junction surfaces
                        if cand_poly.intersects(road_and_junction_surface):
                            continue

                        # Test B: Zero intersection with total exclusion zone (sidewalks, curbs, 2m buffer)
                        if cand_poly.intersects(total_exclusion_zone):
                            continue
                        if cand_poly.distance(road_and_junction_surface) < 2.0:
                            continue

                        # Test C: Inter-building clearance buffer (>= 2.5m) with all existing buildings
                        cand_buffered = cand_poly.buffer(2.5)
                        nearby_indices = spatial_index.query(cand_buffered)
                        has_bldg_conflict = False
                        for n_idx in nearby_indices:
                            if cand_buffered.intersects(all_placed_polys[n_idx]):
                                has_bldg_conflict = True
                                break
                        if has_bldg_conflict:
                            continue

                        # PASSED ALL VALIDATION!
                        candidate_accepted = True
                        accepted_poly = cand_poly
                        accepted_pts = [{'x': round(p[0], 2), 'y': round(p[1], 2)} for p in fp_pts]
                        if shift > 0.0:
                            was_relocated = True
                        break

                    if candidate_accepted:
                        typology = "commercial" if is_arterial else ("house" if (len(buildings) % 3 != 0) else "apartments")
                        bid = f"infill_{eid}_{s}_{side}"

                        buildings.append({
                            "id": bid,
                            "name": "",
                            "building_type": typology,
                            "levels": 2 if typology == "house" else (4 if typology == "commercial" else 6),
                            "shape": accepted_pts,
                            "facing": round(facing_deg, 1),
                            "is_infill": True,
                            "source": "frontage_infill"
                        })
                        all_placed_polys.append(accepted_poly)
                        spatial_index = STRtree(all_placed_polys)

                        if was_relocated:
                            corrected_relocated += 1
                        else:
                            accepted_direct += 1
                    else:
                        rejected_count += 1

    infill_total = accepted_direct + corrected_relocated
    print(f"\nInfill Parcel Validation Summary:")
    print(f"  Accepted Directly:       {accepted_direct}")
    print(f"  Corrected & Relocated:   {corrected_relocated}")
    print(f"  Rejected (Unresolvable): {rejected_count}")
    print(f"  Total Infill Placed:     {infill_total}")
    print(f"TOTAL CITY BUILDINGS:       {len(buildings)} ({len(buildings) - infill_total} Authentic + {infill_total} Infill)")

    # 7. Road Labels
    road_labels = [
        {"name": "Balmatta Road", "x": 1391.89, "y": 1494.62},
        {"name": "Mother Teresa Road", "x": 1488.75, "y": 1289.47},
        {"name": "Falnir-Jyothi Road", "x": 1699.23, "y": 1491.43},
        {"name": "Father Muller Road", "x": 2049.23, "y": 1466.82}
    ]

    export_payload = {
        "edges": roads,
        "junctions": junctions,
        "buildings": buildings,
        "parks": parks,
        "hospitals": hospitals,
        "road_labels": road_labels,
        "traffic_lights": traffic_lights
    }

    # Save to all destination paths
    for p in OUTPUT_FILES:
        os.makedirs(p.parent, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(export_payload, f)
        print(f"Successfully written to: {p}")

    print("=" * 80)
    print("PHASE 2C EXPORT COMPLETE!")
    print("=" * 80)

if __name__ == "__main__":
    export_network()
