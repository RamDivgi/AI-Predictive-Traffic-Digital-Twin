from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd
import traci

from junction_detector import (
    get_upcoming_junctions,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL_FILE = (
    PROJECT_ROOT
    / "models"
    / "eta_prediction_model.joblib"
)

AMBULANCE_ID = "ambulance"

MAX_JUNCTIONS = 3

MINIMUM_PREDICTION_SPEED = 5.0


@dataclass
class JunctionETA:
    junction_id: str
    incoming_edge: str
    outgoing_edge: str
    distance_m: float
    estimated_travel_seconds: float
    estimated_arrival_time: float
    ml_predicted: bool = False


_model = None


def load_eta_model():
    """
    Load the trained ETA prediction pipeline once.
    """

    global _model

    if _model is not None:
        return _model

    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"ETA prediction model not found:\n"
            f"{MODEL_FILE}"
        )

    _model = joblib.load(
        MODEL_FILE
    )

    return _model


def get_traffic_features(
    junction,
    ambulance_speed_mps: float,
) -> dict:
    """
    Collect the same feature types used during ML training.
    """

    incoming_edge = (
        junction.incoming_edge
    )

    vehicle_ids = (
        traci.edge.getLastStepVehicleIDs(
            incoming_edge
        )
    )

    vehicle_count = len(
        vehicle_ids
    )

    halted_vehicle_count = sum(
        1
        for vehicle_id in vehicle_ids
        if traci.vehicle.getSpeed(
            vehicle_id
        ) < 0.1
    )

    mean_speed = (
        traci.edge.getLastStepMeanSpeed(
            incoming_edge
        )
    )

    occupancy = (
        traci.edge.getLastStepOccupancy(
            incoming_edge
        )
    )

    if mean_speed < 0:
        mean_speed = 0.0

    if occupancy < 0:
        occupancy = 0.0

    junction_id = (
        junction.junction_id
    )

    signal_phase = -1
    signal_time_to_switch = 0.0

    try:
        signal_phase = (
            traci.trafficlight.getPhase(
                junction_id
            )
        )

        current_time = (
            traci.simulation.getTime()
        )

        next_switch = (
            traci.trafficlight.getNextSwitch(
                junction_id
            )
        )

        signal_time_to_switch = max(
            0.0,
            next_switch - current_time,
        )

    except traci.TraCIException:
        pass

    traffic_scenario = (
        "live"
    )

    return {
        "ambulance_speed_mps": (
            ambulance_speed_mps
        ),
        "ambulance_speed_kmh": (
            ambulance_speed_mps * 3.6
        ),
        "distance_to_junction_m": (
            junction.distance_from_ambulance_m
        ),
        "vehicle_count": (
            vehicle_count
        ),
        "halted_vehicle_count": (
            halted_vehicle_count
        ),
        "mean_speed_kmh": (
            mean_speed * 3.6
        ),
        "occupancy_percent": (
            occupancy
        ),
        "signal_phase": (
            signal_phase
        ),
        "signal_time_to_switch_s": (
            signal_time_to_switch
        ),
        "junction_id": (
            junction_id
        ),
        "incoming_edge": (
            incoming_edge
        ),
        "outgoing_edge": (
            junction.outgoing_edge
        ),
        "traffic_scenario": (
            traffic_scenario
        ),
    }


def predict_eta(
    junction,
    ambulance_speed_mps: float,
) -> float:
    """
    Predict ambulance arrival time using the trained ML model.

    If prediction fails, fall back to the physics-based ETA.
    """

    try:
        model = load_eta_model()

        features = get_traffic_features(
            junction,
            ambulance_speed_mps,
        )

        dataframe = pd.DataFrame(
            [features]
        )

        prediction = float(
            model.predict(
                dataframe
            )[0]
        )

        if prediction >= 0.0:
            return prediction

    except Exception:
        pass

    effective_speed = max(
        ambulance_speed_mps,
        MINIMUM_PREDICTION_SPEED,
    )

    return (
        junction.distance_from_ambulance_m
        / effective_speed
    )


def calculate_junction_etas(
    max_junctions: int = MAX_JUNCTIONS,
) -> list[JunctionETA]:
    """
    Calculate ETA for upcoming junctions.

    Primary method:
        Trained Random Forest model.

    Fallback:
        Physics-based distance / bounded-speed ETA.
    """

    if (
        AMBULANCE_ID
        not in traci.vehicle.getIDList()
    ):
        return []

    junctions = get_upcoming_junctions(
        max_junctions
    )

    if not junctions:
        return []

    current_speed = (
        traci.vehicle.getSpeed(
            AMBULANCE_ID
        )
    )

    current_time = (
        traci.simulation.getTime()
    )

    results = []

    for junction in junctions:

        predicted_eta = predict_eta(
            junction,
            current_speed,
        )

        results.append(
            JunctionETA(
                junction_id=(
                    junction.junction_id
                ),
                incoming_edge=(
                    junction.incoming_edge
                ),
                outgoing_edge=(
                    junction.outgoing_edge
                ),
                distance_m=(
                    junction.distance_from_ambulance_m
                ),
                estimated_travel_seconds=(
                    predicted_eta
                ),
                estimated_arrival_time=(
                    current_time
                    + predicted_eta
                ),
                ml_predicted=True,
            )
        )

    return results


def format_junction_etas(
    etas: list[JunctionETA],
) -> str:
    """
    Format junction ETA information
    for console output.
    """

    if not etas:
        return (
            "No junction ETA available."
        )

    lines = []

    for index, eta in enumerate(
        etas,
        start=1,
    ):

        method = (
            "ML"
            if eta.ml_predicted
            else "Physics"
        )

        lines.append(
            f"{index}. Junction "
            f"{eta.junction_id} | "
            f"{eta.incoming_edge} -> "
            f"{eta.outgoing_edge} | "
            f"Distance: "
            f"{eta.distance_m:.2f} m | "
            f"ETA: "
            f"{eta.estimated_travel_seconds:.2f} s | "
            f"Arrival: "
            f"{eta.estimated_arrival_time:.2f} s | "
            f"Method: {method}"
        )

    return "\n".join(lines)