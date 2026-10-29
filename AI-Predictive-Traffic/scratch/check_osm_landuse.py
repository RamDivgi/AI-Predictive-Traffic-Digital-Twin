import json
import urllib.request
import sumolib

net = sumolib.net.readNet("AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml")
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()
sw_lon, sw_lat = net.convertXY2LonLat(min_x, min_y)
ne_lon, ne_lat = net.convertXY2LonLat(max_x, max_y)

query = f"""[out:json][timeout:30];
(
  way["landuse"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  relation["landuse"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["leisure"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["amenity"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
);
out body;
>;
out skel qt;"""

req = urllib.request.Request(
    "https://overpass.kumi.systems/api/interpreter",
    data=query.encode("utf-8"),
    headers={"User-Agent": "MangaluruDigitalTwin/1.0"}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        elements = data.get("elements", [])
        ways = [e for e in elements if e.get("type") == "way"]
        print(f"Total non-building urban zone ways found: {len(ways)}")
        from collections import Counter
        tags = Counter()
        for w in ways:
            t = w.get("tags", {})
            for k in ["landuse", "leisure", "amenity"]:
                if k in t:
                    tags[f"{k}={t[k]}"] += 1
        for k, v in tags.most_common(25):
            print(f"  {k}: {v}")
            
        with open("AI-Predictive-Traffic/simulation/mangaluru/osm_urban_zones.json", "w") as f_out:
            json.dump(data, f_out)
        print("Cached urban zones to osm_urban_zones.json")
except Exception as e:
    print(f"Error: {e}")
