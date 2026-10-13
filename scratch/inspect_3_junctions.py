import xml.etree.ElementTree as ET

tree = ET.parse('AI-Predictive-Traffic/simulation/mangaluru/presentation_selection2.net.xml')
root = tree.getroot()

target_ids = ['298371899', '8387081772', '11288614860']

for tid in target_ids:
    print(f'=== TARGET ID: {tid} ===')
    juncs = [j for j in root.findall('junction') if j.get('id') == tid]
    print(f'Junctions count: {len(juncs)}')
    for j in juncs:
        print(f'  junction id={j.get("id")} type={j.get("type")} x={j.get("x")} y={j.get("y")}')
        print(f'  incLanes: {j.get("incLanes")}')
    
    tls = [t for t in root.findall('tlLogic') if t.get('id') == tid]
    print(f'tlLogics count: {len(tls)}')
    for t in tls:
        print(f'  tlLogic id={t.get("id")} type={t.get("type")} programID={t.get("programID")}')
        for p in t.findall('phase'):
            print(f'    phase state={p.get("state")} duration={p.get("duration")}')
            
    conns = [c for c in root.findall('connection') if c.get('tl') == tid]
    print(f'Connections count: {len(conns)}')
    for c in conns:
        print(f'  conn: from={c.get("from")} to={c.get("to")} fromLane={c.get("fromLane")} toLane={c.get("toLane")} linkIndex={c.get("linkIndex")}')
