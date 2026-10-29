"""
Authentication and Role-Based Access Control (RBAC) Module
Mangaluru Emergency Response Digital Twin

Roles:
- dispatcher: Dispatch ambulances, select origins/hospitals, abort trips.
- admin: Traffic Administrator with simulation controls, incident injection, signal management, and dispatch.
- viewer: Read-only access to live status, telemetry, routes, trip history, and analytics.
"""

import hashlib
import hmac
import os
import secrets
import time
from typing import Dict, Any, List, Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)

# Password hashing utilities using standard library PBKDF2-HMAC-SHA256
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}:{pwd_hash.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, hash_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False

# Demonstration accounts (Stored with PBKDF2-HMAC-SHA256 hashed passwords)
# Note: These are academic demonstration credentials for project presentation.
DEMO_USERS: Dict[str, Dict[str, Any]] = {
    "dispatcher": {
        "username": "dispatcher",
        "name": "Emergency Dispatcher",
        "role": "dispatcher",
        # Default password: "dispatch123"
        "password_hash": hash_password("dispatch123", salt=b"mangaluru_salt_1"),
        "permissions": ["dispatch", "trip_control", "view"],
        "description": "Authorized to select ambulances, origins, hospitals and control active trips."
    },
    "traffic_admin": {
        "username": "traffic_admin",
        "name": "Traffic Systems Administrator",
        "role": "admin",
        # Default password: "admin123"
        "password_hash": hash_password("admin123", salt=b"mangaluru_salt_2"),
        "permissions": ["dispatch", "trip_control", "sim_control", "incidents", "view"],
        "description": "Full access to simulation pause/resume/reset, signal preemption and incidents."
    },
    "evaluator": {
        "username": "evaluator",
        "name": "Academic Evaluator / Viewer",
        "role": "viewer",
        # Default password: "viewer123"
        "password_hash": hash_password("viewer123", salt=b"mangaluru_salt_3"),
        "permissions": ["view"],
        "description": "Read-only access to overview, telemetry, routes, trip history, and analytics."
    }
}

# In-memory active session store
# token -> { "username": ..., "role": ..., "created_at": ..., "expires_at": ... }
ACTIVE_SESSIONS: Dict[str, Dict[str, Any]] = {}
SESSION_EXPIRY_SECONDS = 86_400  # 24 hours for stable presentations

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    user = DEMO_USERS.get(username.strip().lower())
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user

VALID_AMBULANCES = {
    "AMB-01": "AMB-01 (ALS - Father Muller Base)",
    "AMB-02": "AMB-02 (BLS - Pumpwell Standby)",
    "AMB-03": "AMB-03 (MICU - Kankanady Depot)"
}

def create_session(
    username: str,
    operator_name: Optional[str] = None,
    assigned_ambulance: Optional[str] = None
) -> str:
    user = DEMO_USERS[username]
    token = secrets.token_hex(24)
    now = time.time()
    
    op_name = operator_name.strip() if (operator_name and operator_name.strip()) else user["name"]
    amb_id = (assigned_ambulance.strip() if assigned_ambulance else "AMB-01").upper()
    if amb_id not in VALID_AMBULANCES:
        amb_id = "AMB-01"

    ACTIVE_SESSIONS[token] = {
        "token": token,
        "username": user["username"],
        "name": op_name,
        "operator_name": op_name,
        "assigned_ambulance": amb_id,
        "role": user["role"],
        "permissions": user["permissions"],
        "created_at": now,
        "expires_at": now + SESSION_EXPIRY_SECONDS
    }
    return token

def get_session(token: str) -> Optional[Dict[str, Any]]:
    if not token or token not in ACTIVE_SESSIONS:
        return None
    session = ACTIVE_SESSIONS[token]
    if time.time() > session["expires_at"]:
        del ACTIVE_SESSIONS[token]
        return None
    return session

def revoke_session(token: str) -> bool:
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]
        return True
    return False

def get_current_user_from_request(
    request: Request,
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    # 1. Check Bearer token in Authorization header
    token = None
    if bearer and bearer.credentials:
        token = bearer.credentials
    
    # 2. Check Cookie
    if not token:
        token = request.cookies.get("session_token")
        
    # 3. Check query param (e.g. ?token=...)
    if not token:
        token = request.query_params.get("token")
        
    # 4. Check Internal system bypass header (for TraCI / Unity background loopback)
    if not token and request.headers.get("X-System-Internal") == "sumo-bridge":
        return {
            "username": "system_bridge",
            "name": "SUMO / Unity Engine Bridge",
            "operator_name": "System Engine Bridge",
            "assigned_ambulance": "AMB-01",
            "role": "admin",
            "permissions": ["dispatch", "trip_control", "sim_control", "incidents", "view"]
        }

    if not token:
        return None
        
    session = get_session(token)
    if not session:
        return None
        
    return {
        "username": session["username"],
        "name": session.get("operator_name", session["name"]),
        "operator_name": session.get("operator_name", session["name"]),
        "assigned_ambulance": session.get("assigned_ambulance", "AMB-01"),
        "role": session["role"],
        "permissions": session["permissions"]
    }


def require_auth(allowed_roles: Optional[List[str]] = None):
    """
    FastAPI dependency factory enforcing authentication and role check.
    """
    def dependency(
        request: Request,
        user: Optional[Dict[str, Any]] = Depends(get_current_user_from_request)
    ) -> Dict[str, Any]:
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please log in with a valid demonstration account.",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        if allowed_roles and user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user['role']}' is not authorized for this operation. Required: {', '.join(allowed_roles)}"
            )
            
        return user
        
    return dependency
