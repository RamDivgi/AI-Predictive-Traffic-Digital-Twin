import json

with open("AI-Predictive-Traffic/scratch/spatial_overlap_diagnostic.json") as f:
    d = json.load(f)

osm = [b for b in d["offenders"] if not b["is_infill"]]
print(f"Total authentic OSM conflicts: {len(osm)}")

# Group by conflict type
physical_overlap = [b for b in osm if b["hits_road"] or b["hits_junction"]]
sub_2m_clearance = [b for b in osm if not (b["hits_road"] or b["hits_junction"])]

print(f"  Physical road/junction overlaps: {len(physical_overlap)}")
print(f"  Clearance < 2.0m: {len(sub_2m_clearance)}")

print("\nAll Physical Overlap Authentic OSM Buildings:")
for b in physical_overlap:
    print(f"  ID: {b['id']:<25} | Area: {b['overlap_area_m2']:>6.1f}m² | Road: {b['hits_road']} | Junc: {b['hits_junction']} | Pos: {b['centroid']}")
