import re

mapping = {
    "160151297": "Father Muller Hospital",
    "741188001": "Unity hospital",
    "2280989014": "Indira Hospital",
    "2282371286": "Athena Hospital",
    "239270568": "SCS Hospital",
    "6938918894": "Mangalore Nursing Home",
    "6938880545": "Vijaya Clinic General Hospital",
    "219223242": "Calaco Hospital"
}

file_path = r"d:\AIML\Projects\Major\AI-Predictive-Traffic\simulation\mangaluru\presentation_labels.add.xml"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

for old_id, new_name in mapping.items():
    new_id = new_name.lower().replace(" ", "_")
    
    # Replace the cross ID
    content = content.replace(f'id="{old_id}_cross"', f'id="{new_id}_cross"')
    
    # Replace the poi ID
    content = content.replace(f'id="{old_id}"', f'id="{new_id}"')
    
    # Replace the name of the POI
    # <poi id="new_id" type="hospital" color="0,0,0,0" layer="100" x="..." y="..." name="Hospital" />
    pattern = rf'(<poi id="{new_id}".*?name=")[^"]*(".*?/>)'
    content = re.sub(pattern, rf'\g<1>{new_name}\g<2>', content)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replacement successful")
