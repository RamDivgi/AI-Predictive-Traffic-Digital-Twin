import gzip
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
import sumolib

PROJECT_ROOT = Path("d:/AIML/Projects/Major")
net_file = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml"
poly_file = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/osm.poly.xml.gz"
road_json = PROJECT_ROOT / "MangaluruDigitalTwin3D/Assets/Generated/RoadNetwork.json"

print("=" * 80)
print("PHASE 2B: BUILDING SOURCE DIAGNOSIS")
print("=" * 80)

# 1. Load SUMO network and bounds
net = sumolib.net.readNet(str(net_file))
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()
sw_lon, sw_lat = net.convertXY2LonLat(min_x, min_y)
ne_lon, ne_lat = net.convertXY2LonLat(max_x, max_y)

print(f"1. SUMO Network Cartesian BBox: [{min_x:.2f}, {min_y:.2f}] to [{max_x:.2f}, {max_y:.2f}]")
print(f"   SUMO Network WGS84 BBox:     [{sw_lat:.6f}, {sw_lon:.6f}] to [{ne_lat:.6f}, {ne_lon:.6f}]")
print(f"   Total Edges: {len(net.getEdges())} | Total Junction Nodes: {len(net.getNodes())}")

# 2. Inspect existing osm.poly.xml.gz
print(f"\n2. Existing osm.poly.xml.gz Analysis:")
poly_buildings_in_bbox = []
poly_buildings_out_bbox = []
other_polys = []

if poly_file.exists():
    with gzip.open(str(poly_file), 'rt') as f:
        tree = ET.parse(f)
        root = tree.getroot()
        for poly in root.findall('poly'):
            ptype = poly.get("type", "")
            shape_str = poly.get("shape", "")
            if not shape_str:
                continue
            pts = [[float(c) for c in pt.split(',')] for pt in shape_str.split() if ',' in pt]
            if len(pts) < 3:
                continue
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            
            p_data = {
                "id": poly.get("id"),
                "type": ptype,
                "cx": cx,
                "cy": cy,
                "shape": pts
            }
            if "building" in ptype:
                if min_x <= cx <= max_x and min_y <= cy <= max_y:
                    poly_buildings_in_bbox.append(p_data)
                else:
                    poly_buildings_out_bbox.append(p_data)
            else:
                other_polys.append(p_data)

print(f"   Building polygons in osm.poly.xml.gz total: {len(poly_buildings_in_bbox) + len(poly_buildings_out_bbox)}")
print(f"   - Within presentation_selection2 bbox:     {len(poly_buildings_in_bbox)}")
print(f"   - Outside presentation_selection2 bbox:    {len(poly_buildings_out_bbox)}")
print(f"   Non-building polygons (parks, amenities): {len(other_polys)}")

# 3. Inspect RoadNetwork.json
print(f"\n3. Existing RoadNetwork.json Analysis:")
with open(str(road_json), 'r') as f:
    rn_data = json.load(f)

rn_buildings = rn_data.get("buildings", [])
print(f"   Exported buildings in RoadNetwork.json:     {len(rn_buildings)}")

# Check spatial distribution of existing buildings
xs = [sum(p['x'] for p in b['shape'])/len(b['shape']) for b in rn_buildings]
ys = [sum(p['y'] for p in b['shape'])/len(b['shape']) for b in rn_buildings]
print(f"   Existing buildings X range: [{min(xs):.1f}, {max(xs):.1f}] (Net: [{min_x:.1f}, {max_x:.1f}])")
print(f"   Existing buildings Y range: [{min(ys):.1f}, {max(ys):.1f}] (Net: [{min_y:.1f}, {max_y:.1f}])")

# 4. Check OpenStreetMap Overpass Live Data for Mangaluru bbox
print(f"\n4. Checking OpenStreetMap Live Coverage via Overpass API:")
query = f"""[out:json][timeout:30];
(
  way["building"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  relation["building"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
);
out body;
>;
out skel qt;"""

req = urllib.request.Request(
    "https://overpass-api.de/api/interpreter",
    data=query.encode("utf-8"),
    headers={"User-Agent": "MangaluruDigitalTwin/1.0"}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        osm_json = json.loads(resp.read().decode("utf-8"))
        elements = osm_json.get("elements", [])
        ways = [e for e in elements if e.get("type") == "way" and "building" in e.get("tags", {})]
        rels = [e for e in elements if e.get("type") == "relation" and "building" in e.get("tags", {})]
        nodes = {e["id"]: (e["lon"], e["lat"]) for e in elements if e.get("type") == "node"}
        print(f"   Overpass API query SUCCESSFUL!")
        print(f"   Available OSM building ways in bbox:      {len(ways)}")
        print(f"   Available OSM building relations in bbox: {len(rels)}")
        print(f"   Available OSM nodes cached:              {len(nodes)}")
        
        # Save raw OSM response for offline reproducibility
        osm_cache_path = PROJECT_ROOT / "AI-Predictive-Traffic/simulation/mangaluru/osm_buildings_live.json"
        with open(str(osm_cache_path), "w") as f_out:
            json.dump(osm_json, f_out)
        print(f"   Cached live OSM data to {osm_cache_path.name}")
except Exception as e:
    print(f"   Overpass API query failed: {e}")

print("=" * 80)
