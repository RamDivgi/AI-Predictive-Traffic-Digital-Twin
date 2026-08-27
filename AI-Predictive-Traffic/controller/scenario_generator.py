from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class TrafficScenario:
    """
    Configuration for one SUMO traffic-generation scenario.
    """

    name: str
    vehicle_count: int
    departure_spacing: float
    speed_factor: float
    description: str


# Base traffic-condition definitions.
#
# The generator will randomize values around these ranges
# for every dataset-generation run.
SCENARIO_RANGES = {
    "low": {
        "vehicle_count": (5, 9),
        "departure_spacing": (3.5, 5.0),
        "speed_factor": (0.95, 1.05),
        "description": "Low traffic demand",
    },
    "normal": {
        "vehicle_count": (10, 15),
        "departure_spacing": (2.0, 3.0),
        "speed_factor": (0.95, 1.05),
        "description": "Normal traffic demand",
    },
    "moderate": {
        "vehicle_count": (16, 22),
        "departure_spacing": (1.4, 2.0),
        "speed_factor": (0.90, 1.00),
        "description": "Moderate traffic demand",
    },
    "heavy": {
        "vehicle_count": (23, 30),
        "departure_spacing": (1.0, 1.4),
        "speed_factor": (0.82, 0.95),
        "description": "Heavy traffic demand",
    },
    "congested": {
        "vehicle_count": (31, 40),
        "departure_spacing": (0.6, 1.0),
        "speed_factor": (0.70, 0.85),
        "description": "Highly congested traffic demand",
    },
}


def _create_scenario(
    name: str,
    rng: random.Random,
) -> TrafficScenario:
    """
    Create one randomized traffic scenario.
    """

    configuration = SCENARIO_RANGES[name]

    vehicle_count = rng.randint(
        configuration["vehicle_count"][0],
        configuration["vehicle_count"][1],
    )

    departure_spacing = round(
        rng.uniform(
            configuration["departure_spacing"][0],
            configuration["departure_spacing"][1],
        ),
        2,
    )

    speed_factor = round(
        rng.uniform(
            configuration["speed_factor"][0],
            configuration["speed_factor"][1],
        ),
        3,
    )

    return TrafficScenario(
        name=name,
        vehicle_count=vehicle_count,
        departure_spacing=departure_spacing,
        speed_factor=speed_factor,
        description=configuration["description"],
    )


def get_scenarios(
    seed: Optional[int] = None,
) -> List[TrafficScenario]:
    """
    Generate one randomized instance of every traffic condition.

    Passing a seed makes the generated scenarios reproducible.
    """

    rng = random.Random(seed)

    scenario_names = [
        "low",
        "normal",
        "moderate",
        "heavy",
        "congested",
    ]

    return [
        _create_scenario(
            name,
            rng,
        )
        for name in scenario_names
    ]


def get_scenario(
    name: str,
    seed: Optional[int] = None,
) -> TrafficScenario:
    """
    Generate one randomized scenario by name.
    """

    normalized_name = name.strip().lower()

    if normalized_name not in SCENARIO_RANGES:
        available = ", ".join(
            SCENARIO_RANGES.keys()
        )

        raise ValueError(
            f"Unknown scenario '{name}'. "
            f"Available scenarios: {available}"
        )

    rng = random.Random(seed)

    return _create_scenario(
        normalized_name,
        rng,
    )


def print_scenarios(
    seed: Optional[int] = None,
) -> None:
    """
    Print the generated traffic scenarios.
    """

    scenarios = get_scenarios(seed)

    print()
    print("=" * 80)
    print("TRAFFIC SCENARIOS")
    print("=" * 80)

    for scenario in scenarios:
        print(
            f"{scenario.name:12} | "
            f"Vehicles: {scenario.vehicle_count:2} | "
            f"Spacing: {scenario.departure_spacing:4.2f}s | "
            f"Speed factor: {scenario.speed_factor:5.3f} | "
            f"{scenario.description}"
        )


if __name__ == "__main__":
    print_scenarios()