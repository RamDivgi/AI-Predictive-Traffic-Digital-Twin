import sumolib
import xml.etree.ElementTree as ET

net_file = "simulation/mangaluru/presentation_selection2.net.xml"
net = sumolib.net.readNet(net_file)
tree = ET.parse(net_file)
root = tree.getroot()

for tid in ['298371899', '8387081772', '11288614860']:
    print(f"\n==========================================")
    print(f"=== CHECKING {tid} ===")
    print(f"==========================================")
    
    # 1. Junction tag
    junc = root.find(f".//junction[@id='{tid}']")
    if junc is not None:
        print(f"Junction found in XML:")
        print(f"  id: {junc.get('id')}")
        print(f"  type: {junc.get('type')}")
        print(f"  x: {junc.get('x')}, y: {junc.get('y')}")
        print(f"  incLanes: {junc.get('incLanes')}")
    else:
        print("Junction element with this ID NOT found in XML.")
        
    # 2. Node in sumolib
    try:
        node = net.getNode(tid)
        print(f"Node in sumolib:")
        print(f"  type: {node.getType()}")
        print(f"  coord: {node.getCoord()}")
        print(f"  tl: {node.getTL()}")
        print(f"  incoming edges: {[e.getID() for e in node.getIncoming()]}")
        print(f"  outgoing edges: {[e.getID() for e in node.getOutgoing()]}")
    except Exception as e:
        print(f"Node in sumolib error: {e}")
        
    # 3. tlLogic tag
    tl = root.find(f".//tlLogic[@id='{tid}']")
    if tl is not None:
        print(f"tlLogic element with this ID found:")
        print(f"  attrib: {tl.attrib}")
        for phase in tl.findall('phase'):
            print(f"    phase: duration={phase.get('duration')} state={phase.get('state')}")
    else:
        print("tlLogic element with this exact ID NOT found.")
        
    # 4. Check if any connection references tl=tid
    conns = [c for c in root.findall('.//connection') if c.get('tl') == tid]
    print(f"Connections with tl='{tid}': {len(conns)}")
    if conns:
        for c in conns[:6]:
            print(f"  from={c.get('from')}:{c.get('fromLane')} to={c.get('to')}:{c.get('toLane')} linkIndex={c.get('linkIndex')} dir={c.get('dir')}")
            
    # 5. Check if this node is controlled by another TLS ID (e.g. cluster)
    for tll in root.findall('.//tlLogic'):
        # Check if node belongs to this TLS
        t_id = tll.get('id')
        if tid in t_id:
            print(f"Found related tlLogic: {t_id}")
            
    # Check if junction's incoming connections belong to any TLS
    if junc is not None:
        inc_edges = set()
        for lane_id in (junc.get('incLanes') or '').split():
            inc_edges.add(lane_id.rsplit('_', 1)[0])
        print(f"Junction incoming road edges: {inc_edges}")
        for inc_e in inc_edges:
            for c in root.findall(f".//connection[@from='{inc_e}']"):
                if c.get('tl'):
                    print(f"  Edge {inc_e} has connection controlled by tl='{c.get('tl')}' to {c.get('to')}")
