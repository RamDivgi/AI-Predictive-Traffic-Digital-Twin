import gzip
import xml.etree.ElementTree as ET

tree = ET.parse(gzip.open('d:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/osm.poly.xml.gz', 'rb'))
root = tree.getroot()
hospitals = [poi for poi in root.findall('poi') if poi.get('type') in ('hospital', 'amenity.hospital')]
print("Hospitals found:")
for h in hospitals:
    name = h.get('name')
    if not name:
        for param in h.findall('param'):
            if param.get('key') == 'name':
                name = param.get('value')
                break
    if not name:
        name = "Unknown"
    print(f"{h.get('id')}: {name} ({h.get('x')}, {h.get('y')})")
