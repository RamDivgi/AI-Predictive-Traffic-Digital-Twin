import xml.etree.ElementTree as ET
import sumolib

class Hospital:
    def __init__(self, id, name, x, y, nearest_edge):
        self.id = id
        self.name = name
        self.x = x
        self.y = y
        self.nearest_edge = nearest_edge

class HospitalManager:
    def __init__(self, net_file, hospitals_file):
        net_file = net_file.replace('\\', '/')
        self.net = sumolib.net.readNet(net_file)
        self.hospitals = {}
        self._load_hospitals(hospitals_file)

    def _load_hospitals(self, hospitals_files):
        if isinstance(hospitals_files, str):
            hospitals_files = [hospitals_files]
            
        for hospitals_file in hospitals_files:
            try:
                tree = ET.parse(hospitals_file)
                root = tree.getroot()
                for poi in root.findall('poi'):
                    poi_type = poi.get('type')
                    if poi_type == 'hospital' or poi_type == 'clinic':
                        hid = poi.get('id')
                        name = poi.get('name')
                        if name in ("Hospital", "Clinic") or not name:
                            name = f"{name or 'Unknown'} ({hid})"
                        x = float(poi.get('x'))
                        y = float(poi.get('y'))
                        
                        # Find nearest edge
                        nearest_edges = self.net.getNeighboringEdges(x, y, r=200.0)
                        suitable = [(edge, dist) for edge, dist in nearest_edges if edge.allows("passenger")]
                        
                        nearest_edge_id = None
                        if suitable:
                            suitable.sort(key=lambda item: item[1])
                            nearest_edge_id = suitable[0][0].getID()
                        
                        self.hospitals[hid] = Hospital(hid, name, x, y, nearest_edge_id)
            except Exception as e:
                print(f"Error loading hospitals: {e}")

    def get_hospital(self, hospital_id):
        return self.hospitals.get(hospital_id)
        
    def get_all_hospitals(self):
        return list(self.hospitals.values())
        
    def get_default_hospital(self):
        return self.get_hospital("highland_hospital")
