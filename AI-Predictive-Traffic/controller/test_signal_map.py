import os
import sys
from pathlib import Path
import traci

PROJECT_ROOT = Path("D:/AIML/Projects/Major/AI-Predictive-Traffic")
sys.path.append(str(PROJECT_ROOT / "controller"))
import signal_mapping

SUMO_CONFIG = PROJECT_ROOT / "simulation" / "mangaluru" / "kankanady_demo.sumocfg"

traci.start([
    "sumo",
    "-c", str(SUMO_CONFIG),
    "--step-length", "1.0",
    "--quit-on-end"
])

tls_id, indices = signal_mapping.get_tls_and_indices_for_movement("-1203027037", "355391676#0")
print(f"Movement -1203027037 -> 355391676#0: TLS = {tls_id}, Indices = {indices}")

tls_id2, indices2 = signal_mapping.get_tls_and_indices_for_movement("1080446743#0", "355391676#0")
print(f"Movement 1080446743#0 -> 355391676#0: TLS = {tls_id2}, Indices = {indices2}")

traci.close()
