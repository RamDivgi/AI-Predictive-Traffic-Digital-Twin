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
PREEMPTION_MIN_HOLD_SECONDS = 8.0     # Minimum time green must be held (traffic safety standard)
PREEMPTION_HOLD_SECONDS = 8.0         # Backward compatibility alias for PREEMPTION_MIN_HOLD_SECONDS
PREEMPTION_MAX_TIMEOUT_S = 45.0       # Maximum fail-safe timeout before forced restoration
PREEMPTION_APPROACH_WIDE = False      # False = movement-specific link indices only; True = approach-wide
PREEMPTION_QUEUE_THRESHOLD = 5        # Halted vehicle threshold for reroute vs preemption
PREEMPTION_QUEUE_CLEAR_SEC_PER_VEH = 2.5 # Estimated clearance time per queued vehicle
MAX_PREDICTIVE_ETA_S = 30.0
ETA_MIN_CLAMP_S = 0.0
ETA_MAX_CLAMP_S = 300.0

# Rerouting Parameters
REROUTE_MIN_IMPROVEMENT_S = 10.0
REROUTE_MIN_IMPROVEMENT_PERCENT = 5.0
REROUTE_COOLDOWN_S = 30.0
REROUTE_MIN_DISTANCE_TO_DEST_M = 150.0
REROUTE_EVALUATION_INTERVAL_S = 5.0
REROUTE_OSCILLATION_WINDOW_S = 90.0
REROUTE_OSCILLATION_PENALTY_FACTOR = 2.0

