import xml.etree.ElementTree as ET
import sumolib

class Hospital:
    def __init__(self, id, name, x, y, nearest_edge, destination_type="hospital"):
        self.id = str(id)
        self.name = str(name)
        self.x = float(x)
        self.y = float(y)
        self.nearest_edge = str(nearest_edge) if nearest_edge else None
        self.destination_type = str(destination_type)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "nearest_edge": self.nearest_edge,
            "destination_type": self.destination_type
        }

# Authoritative registry of supported, verified hospital destinations in Mangaluru
AUTHORITATIVE_REGISTRY = {
    "160262590": {
        "name": "City Hospital",
        "type": "hospital",
        "edge_override": "-239271492#3"
    },
    "highland_hospital": {
        "name": "Highland Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "kmc_hospital": {
        "name": "KMC Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "father_muller_hospital": {
        "name": "Father Muller Hospital",
        "type": "hospital",
        "edge_override": "26209723#3"
    },
    "calaco_hospital": {
        "name": "Calaco Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "scs_hospital": {
        "name": "SCS Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "unity_hospital": {
        "name": "Unity Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "indira_hospital": {
        "name": "Indira Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "athena_hospital": {
        "name": "Athena Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "vijaya_clinic_general_hospital": {
        "name": "Vijaya Clinic General Hospital",
        "type": "hospital",
        "edge_override": None
    },
    "mangalore_nursing_home": {
        "name": "Mangalore Nursing Home",
        "type": "hospital",
        "edge_override": None
    }
}

# Legacy and semantic aliases mapped to authoritative hospital IDs
HOSPITAL_ALIASES = {
    "city_hospital": "160262590"
}

# Unwanted generic POIs, clinics without hospital status, and unroutable duplicates
EXCLUDED_POIS = {
    "1203949837",
    "5867851072",
    "6938916238",
    "6938916239",
    "city_hospital"
}

class HospitalManager:
    def __init__(self, net_file, hospitals_file):
        net_file = str(net_file).replace('\\', '/')
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
                    hid = poi.get('id')
                    if not hid or hid in EXCLUDED_POIS:
                        continue
                    
                    if hid not in AUTHORITATIVE_REGISTRY:
                        continue

                    spec = AUTHORITATIVE_REGISTRY[hid]
                    name = spec["name"]
                    dest_type = spec["type"]
                    x = float(poi.get('x'))
                    y = float(poi.get('y'))

                    # Resolve nearest passenger edge
                    nearest_edge_id = spec.get("edge_override")
                    if not nearest_edge_id:
                        nearest_edges = self.net.getNeighboringEdges(x, y, r=200.0)
                        suitable = [(edge, dist) for edge, dist in nearest_edges if edge.allows("passenger")]
                        if suitable:
                            suitable.sort(key=lambda item: item[1])
                            nearest_edge_id = suitable[0][0].getID()

                    self.hospitals[hid] = Hospital(
                        id=hid,
                        name=name,
                        x=x,
                        y=y,
                        nearest_edge=nearest_edge_id,
                        destination_type=dest_type
                    )
            except Exception as e:
                print(f"Error loading hospitals from {hospitals_file}: {e}")

    def get_hospital(self, hospital_id):
        if not hospital_id:
            return None
        canonical_id = HOSPITAL_ALIASES.get(hospital_id, hospital_id)
        return self.hospitals.get(canonical_id)
        
    def get_all_hospitals(self):
        return list(self.hospitals.values())
        
    def get_default_hospital(self):
        return self.get_hospital("highland_hospital")
