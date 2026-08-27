import json
import os
from typing import Dict, Any
import time

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "twin_state.json")

class StateProvider:
    @staticmethod
    def write_state(state_dict: Dict[str, Any]):
        # Write to a temporary file and rename to ensure atomic reads
        temp_file = STATE_FILE + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(state_dict, f)
            os.replace(temp_file, STATE_FILE)
        except Exception:
            pass
            
    @staticmethod
    def read_state() -> Dict[str, Any]:
        if not os.path.exists(STATE_FILE):
            return None
        
        # Check if the file is stale (e.g. runner crashed)
        if time.time() - os.path.getmtime(STATE_FILE) > 5.0:
            return None
            
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def clear_state():
        if os.path.exists(STATE_FILE):
            try:
                os.remove(STATE_FILE)
            except:
                pass
