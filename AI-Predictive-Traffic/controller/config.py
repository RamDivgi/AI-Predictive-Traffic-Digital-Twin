from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SIMULATION_DIR = PROJECT_ROOT / "simulation" / "mangaluru"

# Model Paths
MODEL_FILE = PROJECT_ROOT / "models" / "eta_prediction_model.joblib"

# Simulation Network Files
NET_FILE = SIMULATION_DIR / "presentation_selection2.net.xml"
HOSPITALS_FILE = SIMULATION_DIR / "presentation_labels.add.xml"

# Ambulance Configuration
AMBULANCE_ID = "ambulance"
DEFAULT_HOSPITAL_ID = "wenlock_hospital"  # Used as fallback if no specific hospital is targeted

# AI Controller / Preemption Parameters
MAX_JUNCTIONS = 10
PREEMPTION_THRESHOLD = 40.0
PREEMPTION_HOLD_SECONDS = 8.0
MAX_PREDICTIVE_ETA_S = 30.0

# Rerouting Parameters
REROUTE_MIN_IMPROVEMENT_S = 10.0
REROUTE_MIN_IMPROVEMENT_PERCENT = 5.0
REROUTE_COOLDOWN_S = 30.0
REROUTE_MIN_DISTANCE_TO_DEST_M = 150.0
REROUTE_EVALUATION_INTERVAL_S = 5.0

