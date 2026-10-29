import json
import math
import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from shapely.strtree import STRtree
import sumolib

PROJECT_ROOT = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic")
SUMO_NET_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"
OSM_LIVE_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "osm_buildings_live.json"
POLY_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "osm.poly.xml.gz"
LABELS_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
PREFAB_BOUNDS_FILE = PROJECT_ROOT / "scratch" / "prefab_bounds.json"

net = sumolib.net.readNet(str(SUMO_NET_FILE))
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()

# 1. Road and Junction Polygons
road_polys = []
sidewalk_polys = []
road_clearance_polys = [] # Road + Sidewalk + 2.0m Safety buffer

SAFETY_MARGIN = 2.0
SIDEWALK_WIDTH = 1.5

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

    for l_idx, lane in enumerate(lanes):
        shape = lane.getShape()
        w = lane.getWidth()
        if len(shape) < 2:
            continue
        ls = LineString(shape)
        # Exact road surface
        r_poly = ls.buffer(w * 0.5, cap_style="flat", join_style="mitre")
        if r_poly.is_valid and not r_poly.is_empty:
            road_polys.append(r_poly)

        # Clearance envelope: lane + sidewalk + safety margin
        clear_poly = ls.buffer((w * 0.5) + SIDEWALK_WIDTH + SAFETY_MARGIN, cap_style="flat", join_style="mitre")
        if clear_poly.is_valid and not clear_poly.is_empty:
            road_clearance_polys.append(clear_poly)

junction_polys = []
junction_clearance_polys = []

for node in net.getNodes():
    shape = node.getShape()
    if shape and len(shape) >= 3:
        j_poly = Polygon(shape)
        if not j_poly.is_valid:
            j_poly = j_poly.buffer(0)
        if j_poly.is_valid and not j_poly.is_empty:
            junction_polys.append(j_poly)
            # Junction clearance envelope with 2.0m safety margin
            jc = j_poly.buffer(SAFETY_MARGIN)
            if jc.is_valid:
                junction_clearance_polys.append(jc)

road_union = unary_union(road_polys)
junction_union = unary_union(junction_polys)
road_and_junction_surface = unary_union([road_union, junction_union])
total_exclusion_zone = unary_union(road_clearance_polys + junction_clearance_polys)

# Load hospital coordinates
hospitals = []
if LABELS_FILE.exists():
    tree = ET.parse(str(LABELS_FILE))
    root = tree.getroot()
    for poi in root.findall('poi'):
        if poi.get("type") == "hospital":
            hx = float(poi.get("x", 0))
            hy = float(poi.get("y", 0))
            if min_x <= hx <= max_x and min_y <= hy <= max_y:
                hospitals.append((hx, hy))

# 2. Ingest Authentic OSM Buildings & Flag Conflicts
authentic_buildings = []
placed_polygons = []
osm_conflicts = []

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

                # Test conflict with road surface & junctions
                hits_road = b_poly.intersects(road_union)
                hits_junc = b_poly.intersects(junction_union)
                dist_road = b_poly.distance(road_and_junction_surface)
                is_conflict = hits_road or hits_junc or (dist_road < 1.5)

                b_entry = {
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
                    b_entry["conflict"] = {
                        "type": "source_data_road_encroachment",
                        "hits_road": hits_road,
                        "hits_junction": hits_junc,
                        "overlap_area_m2": round(overlap_area, 2),
                        "clearance_m": round(dist_road, 2)
                    }
                    osm_conflicts.append(b_entry)
                else:
                    placed_polygons.append(b_poly)

                authentic_buildings.append(b_entry)

# Ingest Polygons from osm.poly.xml.gz
if POLY_FILE.exists():
    with gzip.open(str(POLY_FILE), 'rt') as f:
        tree = ET.parse(f)
        root = tree.getroot()
        for poly in root.findall('poly'):
            ptype = poly.get("type", "")
            if "building" not in ptype:
                continue
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

            pid = poly.get("id")
            is_dup = any(abs(b["shape"][0]["x"] - pts[0]["x"]) < 5.0 and abs(b["shape"][0]["y"] - pts[0]["y"]) < 5.0 for b in authentic_buildings)
            if not is_dup:
                b_poly = Polygon([(p["x"], p["y"]) for p in pts])
                if not b_poly.is_valid:
                    b_poly = b_poly.buffer(0)
                if b_poly.is_empty:
                    continue

                hits_road = b_poly.intersects(road_union)
                hits_junc = b_poly.intersects(junction_union)
                dist_road = b_poly.distance(road_and_junction_surface)
                is_conflict = hits_road or hits_junc or (dist_road < 1.5)

                b_entry = {
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
                    b_entry["conflict"] = {
                        "type": "source_data_road_encroachment",
                        "hits_road": hits_road,
                        "hits_junction": hits_junc,
                        "overlap_area_m2": round(overlap_area, 2),
                        "clearance_m": round(dist_road, 2)
                    }
                    osm_conflicts.append(b_entry)
                else:
                    placed_polygons.append(b_poly)

                authentic_buildings.append(b_entry)

print(f"Loaded {len(authentic_buildings)} authentic buildings.")
print(f"  Non-conflicting: {len(placed_polygons)}")
print(f"  Flagged source data conflicts: {len(osm_conflicts)}")

# Build spatial index of placed buildings for fast collision checks
placed_bldgs_tree = STRtree(placed_polygons)

# 3. Generate Infill Parcels with Strict Footprint Spatial Validation
parcel_step = 22.0
infill_buildings = []
corrected_count = 0
rejected_count = 0
accepted_direct_count = 0

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

                # Base setback: road half width + sidewalk (1.5m) + safety margin (2.0m) + building half depth (hd)
                base_setback = (total_w * 0.5) + SIDEWALK_WIDTH + SAFETY_MARGIN + hd + 1.0

                # Try base setback, then try deeper parcel relocations (+2.5m, +5.0m, +7.5m, +10.0m)
                candidate_accepted = False
                accepted_poly = None
                accepted_pts = None
                was_relocated = False

                for shift in [0.0, 2.5, 5.0, 7.5, 10.0]:
                    cur_setback = base_setback + shift
                    bx = base_x + nx * cur_setback
                    by = base_y + ny * cur_setback

                    # Map bounds check
                    if not (min_x + 15 <= bx <= max_x - 15 and min_y + 15 <= by <= max_y - 15):
                        continue

                    # Hospital apron exclusion (>= 35m)
                    if any(math.hypot(bx - hx, by - hy) < 35.0 for hx, hy in hospitals):
                        continue

                    # Compute 4 footprint corners
                    corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
                    fp_pts = []
                    for cx_loc, cy_loc in corners:
                        gx = bx + (cx_loc * cos_a - cy_loc * sin_a)
                        gy = by + (cx_loc * sin_a + cy_loc * cos_a)
                        fp_pts.append((gx, gy))

                    cand_poly = Polygon(fp_pts)

                    # Test 1: Must NOT intersect road or junction surface
                    if cand_poly.intersects(road_and_junction_surface):
                        continue

                    # Test 2: Must NOT intersect total exclusion zone (road + sidewalk + junction + 2.0m safety margin)
                    if cand_poly.intersects(total_exclusion_zone):
                        continue

                    # Test 3: Must maintain building-to-building buffer (>= 3.0m) with all existing buildings
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
                    typology = "commercial" if is_arterial else ("house" if (len(infill_buildings) % 3 != 0) else "apartments")
                    bid = f"infill_{eid}_{s}_{side}"
                    infill_buildings.append({
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
                        corrected_count += 1
                    else:
                        accepted_direct_count += 1
                else:
                    rejected_count += 1

print("\n" + "=" * 80)
print("INFILL GENERATION & VALIDATION RESULTS:")
print(f"Total Infill Candidates Evaluated: {accepted_direct_count + corrected_count + rejected_count}")
print(f"Accepted Directly (0 setback adjustment): {accepted_direct_count}")
print(f"Corrected & Relocated within parcel:      {corrected_count}")
print(f"Rejected (Unresolvable conflict):         {rejected_count}")
print(f"Total Validated Infill Buildings:        {len(infill_buildings)}")
print(f"TOTAL CITY BUILDINGS (Authentic + Infill):{len(authentic_buildings) + len(infill_buildings)}")
print("=" * 80)

# Verify 100% of accepted infill buildings have ZERO overlap with road/junction
all_infill_polys = [Polygon([(p["x"], p["y"]) for p in b["shape"]]) for b in infill_buildings]
infill_road_hits = sum(1 for p in all_infill_polys if p.intersects(road_and_junction_surface))
infill_exclusion_hits = sum(1 for p in all_infill_polys if p.intersects(total_exclusion_zone))
print(f"Sanity Check on Infill Buildings:")
print(f"  Infill intersecting roads/junctions:       {infill_road_hits} (MUST BE 0)")
print(f"  Infill violating safety/sidewalk buffers: {infill_exclusion_hits} (MUST BE 0)")
