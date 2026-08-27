import sumolib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NETWORK_FILE = PROJECT_ROOT / "simulation" / "mangaluru" / "mangaluru_ai.net.xml.gz"

def main():
    net = sumolib.net.readNet(str(NETWORK_FILE))
    
    # An edge that we know is not a TLS. For example a random edge.
    edges = net.getEdges()
    for edge in edges:
        for to_edge, conns in edge.getOutgoing().items():
            for conn in conns:
                tls = conn.getTLSID()
                if not tls:
                    print(f"No TLS for connection {edge.getID()} -> {to_edge.getID()}, type is {type(tls)}, value is '{tls}'")
                    return

if __name__ == "__main__":
    main()
