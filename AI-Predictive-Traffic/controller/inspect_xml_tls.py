import gzip
import xml.etree.ElementTree as ET

net_file = "D:/AIML/Projects/Major/AI-Predictive-Traffic/simulation/mangaluru/mangaluru_ai.net.xml.gz"

with gzip.open(net_file, 'rt', encoding='utf-8') as f:
    for event, elem in ET.iterparse(f):
        if elem.tag == 'tlLogic' and elem.attrib.get('id') == "joinedS_11152279217_cluster_11151324665_3610155471":
            print(f"Program: {elem.attrib}")
            for child in elem:
                if child.tag == 'phase':
                    print(f"Phase: {child.attrib}")
            elem.clear()
