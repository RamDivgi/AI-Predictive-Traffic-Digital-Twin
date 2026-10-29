import json
import urllib.request
import sumolib

net = sumolib.net.readNet("AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml")
(min_x, min_y), (max_x, max_y) = net.getBBoxXY()
sw_lon, sw_lat = net.convertXY2LonLat(min_x, min_y)
ne_lon, ne_lat = net.convertXY2LonLat(max_x, max_y)

print(f"Querying all POIs, amenities, shops, offices, landuse in bbox...")

query = f"""[out:json][timeout:45];
(
  way["amenity"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["shop"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["office"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["tourism"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["healthcare"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["historic"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["leisure"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
  way["landuse"]({sw_lat},{sw_lon},{ne_lat},{ne_lon});
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
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        ways = [e for e in data.get("elements", []) if e.get("type") == "way"]
        print(f"Total non-building tagged ways returned: {len(ways)}")
        from collections import Counter
        tags = Counter()
        for w in ways:
            t = w.get("tags", {})
            for k in ["amenity", "shop", "office", "tourism", "healthcare", "historic", "leisure", "landuse"]:
                if k in t:
                    tags[f"{k}={t[k]}"] += 1
        for k, v in tags.most_common(30):
            print(f"  {k}: {v}")
            
        with open("AI-Predictive-Traffic/simulation/mangaluru/osm_pois_and_zones.json", "w") as f_out:
            json.dump(data, f_out)
        print("Saved to osm_pois_and_zones.json")
except Exception as e:
    print(f"Error querying: {e}")
