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

    @staticmethod
    def write_trip_command(command: Dict[str, Any]):
        cmd_file = os.path.join(os.path.dirname(__file__), "..", "trip_command.json")
        temp_file = cmd_file + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(command, f)
            os.replace(temp_file, cmd_file)
        except Exception:
            pass

    @staticmethod
    def read_trip_command() -> Dict[str, Any]:
        cmd_file = os.path.join(os.path.dirname(__file__), "..", "trip_command.json")
        if not os.path.exists(cmd_file):
            return None
        try:
            with open(cmd_file, "r") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def clear_trip_command():
        cmd_file = os.path.join(os.path.dirname(__file__), "..", "trip_command.json")
        if os.path.exists(cmd_file):
            try:
                os.remove(cmd_file)
            except:
                pass

    @staticmethod
    def write_trip_status(status_dict: Dict[str, Any]):
        status_file = os.path.join(os.path.dirname(__file__), "..", "trip_status.json")
        temp_file = status_file + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(status_dict, f)
            os.replace(temp_file, status_file)
        except Exception:
            pass

    @staticmethod
    def read_trip_status() -> Dict[str, Any]:
        status_file = os.path.join(os.path.dirname(__file__), "..", "trip_status.json")
        if not os.path.exists(status_file):
            return None
        try:
            with open(status_file, "r") as f:
                return json.load(f)
        except Exception:
            return None
