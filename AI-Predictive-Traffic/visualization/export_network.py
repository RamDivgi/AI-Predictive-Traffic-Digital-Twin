import os
import sys
import json
import sumolib
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMO_NET_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_selection2.net.xml"
OUTPUT_FILE = PROJECT_ROOT / "visualization" / "RoadNetwork.json"
UNITY_OUTPUT_FILE = PROJECT_ROOT.parent / "MangaluruDigitalTwin3D" / "Assets" / "Generated" / "RoadNetwork.json"

def export_network():
    print(f"Loading SUMO network from: {SUMO_NET_FILE}")
    if not SUMO_NET_FILE.exists():
        print("Network file not found!")
        return

    net = sumolib.net.readNet(str(SUMO_NET_FILE))
    
    roads = []
    
    for edge in net.getEdges():
        # Only export normal edges for now to keep it lightweight.
        # Internal edges are junctions which can be messy for basic lines.
        if edge.getFunction() == "internal":
            continue
            
        edge_data = {
            "id": edge.getID(),
            "lanes": []
        }
        
        for lane in edge.getLanes():
            shape = lane.getShape()
            lane_data = {
                "id": lane.getID(),
                "width": lane.getWidth(),
                "shape": [{"x": p[0], "y": p[1]} for p in shape]
            }
            edge_data["lanes"].append(lane_data)
            
        roads.append(edge_data)
            
    junctions = []
    for node in net.getNodes():
        shape = node.getShape()
        is_tls = node.getType() == "traffic_light"
        
        # Only export junctions that have a defined polygon shape
        if shape and len(shape) >= 3:
            junctions.append({
                "id": node.getID(),
                "is_tls": is_tls,
                "shape": [{"x": p[0], "y": p[1]} for p in shape],
                "x": node.getCoord()[0],
                "y": node.getCoord()[1]
            })

    (min_x, min_y), (max_x, max_y) = net.getBBoxXY()
    
    # Read buildings and hospitals from osm.poly.xml.gz
    poly_file = PROJECT_ROOT / "simulation" / "mangaluru" / "osm.poly.xml.gz"
    buildings = []
    hospitals = []
    
    if poly_file.exists():
        import xml.etree.ElementTree as ET
        import gzip
        print(f"Loading polygons from: {poly_file}")
        with gzip.open(poly_file, 'rt') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            for poly in root.findall('poly'):
                ptype = poly.get("type", "")
                if "building" in ptype:
                    shape_str = poly.get("shape")
                    if shape_str:
                        points = []
                        for pt in shape_str.split():
                            coords = pt.split(",")
                            if len(coords) >= 2:
                                points.append({"x": float(coords[0]), "y": float(coords[1])})
                        
                        if len(points) >= 3:
                            # Filter by bounding box of presentation selection
                            cx = sum(p["x"] for p in points) / len(points)
                            cy = sum(p["y"] for p in points) / len(points)
                            if min_x <= cx <= max_x and min_y <= cy <= max_y:
                                buildings.append({
                                    "id": poly.get("id"),
                                    "shape": points
                                })

    # Only load the relevant hospitals from presentation_labels.add.xml or hospitals.add.xml
    # Actually, we know exactly which hospitals are in the presentation network
    hospitals_add_file = PROJECT_ROOT / "simulation" / "mangaluru" / "presentation_labels.add.xml"
    if hospitals_add_file.exists():
        import xml.etree.ElementTree as ET
        print(f"Loading hospitals from: {hospitals_add_file}")
        tree = ET.parse(hospitals_add_file)
        root = tree.getroot()
        for poi in root.findall('poi'):
            if poi.get("type") == "hospital":
                hx = float(poi.get("x", 0))
                hy = float(poi.get("y", 0))
                if min_x <= hx <= max_x and min_y <= hy <= max_y:
                    hospitals.append({
                        "id": poi.get("id"),
                        "name": poi.get("name", "Hospital"),
                        "x": hx,
                        "y": hy
                    })
                    
    road_labels = [
        {"name": "Balmatta Road", "x": 1391.89, "y": 1494.62},
        {"name": "Mother Teresa Road", "x": 1488.75, "y": 1289.47},
        {"name": "Falnir-Jyothi Road", "x": 1699.23, "y": 1491.43},
        {"name": "Father Muller Road", "x": 2049.23, "y": 1466.82}
    ]

    data = {
        "edges": roads,
        "junctions": junctions,
        "buildings": buildings,
        "hospitals": hospitals,
        "road_labels": road_labels
    }
    
    # Save locally
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f)
    print(f"Exported {len(roads)} edges, {len(junctions)} junctions, {len(buildings)} buildings, and {len(hospitals)} hospitals to {OUTPUT_FILE}")
    
    # Try saving to Unity
    os.makedirs(UNITY_OUTPUT_FILE.parent, exist_ok=True)
    with open(UNITY_OUTPUT_FILE, 'w') as f:
        json.dump(data, f)
    print(f"Also exported to Unity at {UNITY_OUTPUT_FILE}")

if __name__ == "__main__":
    export_network()
