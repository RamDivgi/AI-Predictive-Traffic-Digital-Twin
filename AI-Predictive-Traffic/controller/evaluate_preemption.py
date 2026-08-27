from __future__ import annotations

from pathlib import Path

import traci


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SUMO_CONFIG = (
    PROJECT_ROOT
    / "simulation"
    / "config"
    / "test.sumocfg"
)

AMBULANCE_ID = "ambulance"

# ---------------------------------------------------------------------------
# SAFETY / TEST CONFIGURATION
# ---------------------------------------------------------------------------

# Absolute maximum simulation duration.
# This prevents a broken traffic scenario from running forever.
MAX_SIMULATION_TIME_S = 180.0

# If the ambulance has not appeared by this time, the experiment is invalid.
AMBULANCE_APPEAR_TIMEOUT_S = 60.0

# Temporary test scenario.
#
# IMPORTANT:
# The ambulance departs at t=20 in test.rou.xml.
# Therefore the forced-red period must extend beyond t=20.
TEST_JUNCTION_ID = "B"
TEST_AMBULANCE_SIGNAL_INDEX = 7
TEST_RED_START_S = 20.0
TEST_RED_END_S = 35.0


def force_test_red_signal(is_preempted: bool = False) -> None:
    """
    Temporary validation scenario.

    The normal test network currently gives the AB -> BC ambulance
    movement a favorable signal. That does not provide a useful
    preemption test.

    Therefore, during the ambulance's initial approach to junction B,
    force the ambulance movement to red while keeping the other
    signal positions green.

    This is ONLY for validating the controller.

    It will be removed once the real digital-twin signal network
    provides realistic signal timing.
    """

    if (
        TEST_JUNCTION_ID
        not in traci.trafficlight.getIDList()
    ):
        return

    current_time = traci.simulation.getTime()

    if not (
        TEST_RED_START_S
        <= current_time
        <= TEST_RED_END_S
    ):
        return

    # Do not overwrite the signal if the AI has successfully preempted it
    if is_preempted:
        return

    current_state = (
        traci.trafficlight.getRedYellowGreenState(
            TEST_JUNCTION_ID
        )
    )

    if not current_state:
        return

    new_state = [
        "G"
        for _ in current_state
    ]

    if (
        0
        <= TEST_AMBULANCE_SIGNAL_INDEX
        < len(new_state)
    ):
        new_state[
            TEST_AMBULANCE_SIGNAL_INDEX
        ] = "r"

    traci.trafficlight.setRedYellowGreenState(
        TEST_JUNCTION_ID,
        "".join(new_state),
    )


def run_simulation(
    use_ai: bool,
) -> dict[str, float]:
    """
    Run one controlled SUMO experiment.

    use_ai=False:
        Normal traffic signal operation.

    use_ai=True:
        AI predictive traffic controller enabled.

    A hard simulation-time limit is applied so that a broken
    scenario cannot run indefinitely.
    """

    if not SUMO_CONFIG.exists():
        raise FileNotFoundError(
            f"SUMO configuration not found:\n"
            f"{SUMO_CONFIG}"
        )

    from traffic_aware_controller import (
        TrafficAwareController,
    )

    controller = (
        TrafficAwareController()
        if use_ai
        else None
    )

    sumo_command = [
        "sumo",
        "-c",
        str(SUMO_CONFIG),
        "--start",
        "--quit-on-end",
    ]

    print()
    print("=" * 80)

    if use_ai:
        print(
            "EXPERIMENT: AI PREDICTIVE PREEMPTION"
        )
    else:
        print(
            "EXPERIMENT: BASELINE NORMAL SIGNALS"
        )

    print("=" * 80)

    try:
        traci.start(
            sumo_command
        )

        ambulance_start_time: float | None = None
        ambulance_arrival_time: float | None = None

        total_waiting_time = 0.0
        total_time_loss = 0.0

        preemption_count = 0

        previously_preempted: set[str] = set()

        # --------------------------------------------------------------
        # Simulation loop
        # --------------------------------------------------------------

        while (
            traci.simulation.getMinExpectedNumber()
            > 0
        ):

            current_simulation_time = (
                traci.simulation.getTime()
            )

            # ----------------------------------------------------------
            # HARD SAFETY TIMEOUT
            # ----------------------------------------------------------

            if (
                current_simulation_time
                >= MAX_SIMULATION_TIME_S
            ):
                print()
                print(
                    "WARNING: Maximum simulation "
                    "time reached."
                )
                print(
                    f"Simulation stopped at "
                    f"{current_simulation_time:.1f}s."
                )
                break

            traci.simulationStep()

            current_time = (
                traci.simulation.getTime()
            )

            vehicle_ids = (
                traci.vehicle.getIDList()
            )

            # ----------------------------------------------------------
            # Temporary test signal scenario
            # ----------------------------------------------------------

            if use_ai:
                is_preempted = (
                    controller is not None
                    and controller.signal_controller.is_preempted(
                        TEST_JUNCTION_ID
                    )
                )
                # force_test_red_signal(is_preempted=is_preempted)

            # ----------------------------------------------------------
            # Ambulance tracking
            # ----------------------------------------------------------

            ambulance_present = (
                AMBULANCE_ID
                in vehicle_ids
            )

            if ambulance_present:

                if ambulance_start_time is None:
                    ambulance_start_time = (
                        current_time
                    )

                    print(
                        f"[TEST] Ambulance entered "
                        f"simulation at "
                        f"{ambulance_start_time:.1f}s"
                    )

                if use_ai:

                    decisions = (
                        controller.process_step()
                    )

                    for features, decision in decisions:

                        junction_id = (
                            features.junction_id
                        )

                        if (
                            decision.should_preempt
                            and junction_id
                            not in previously_preempted
                        ):
                            preemption_count += 1

                            previously_preempted.add(
                                junction_id
                            )

                            print(
                                f"[EVALUATION] "
                                f"Preemption counted: "
                                f"{junction_id}"
                            )

            else:

                # Ambulance has disappeared from the
                # active vehicle list after completing
                # its route.
                if (
                    ambulance_start_time
                    is not None
                    and ambulance_arrival_time
                    is None
                ):
                    ambulance_arrival_time = (
                        current_time
                    )

                    print(
                        f"[TEST] Ambulance completed "
                        f"route at "
                        f"{ambulance_arrival_time:.1f}s"
                    )

            # ----------------------------------------------------------
            # Global traffic statistics
            # ----------------------------------------------------------

            for vehicle_id in vehicle_ids:

                try:

                    total_waiting_time += (
                        traci.vehicle.getAccumulatedWaitingTime(
                            vehicle_id
                        )
                    )

                    total_time_loss += (
                        traci.vehicle.getTimeLoss(
                            vehicle_id
                        )
                    )

                except traci.TraCIException:
                    pass

            # ----------------------------------------------------------
            # Ambulance appearance timeout
            # ----------------------------------------------------------

            if (
                ambulance_start_time is None
                and current_time
                >= AMBULANCE_APPEAR_TIMEOUT_S
            ):
                print()
                print(
                    "WARNING: Ambulance did not "
                    "appear within the expected "
                    "time window."
                )
                break

        # --------------------------------------------------------------
        # Final ambulance handling
        # --------------------------------------------------------------

        if (
            ambulance_arrival_time is None
            and ambulance_start_time is not None
        ):
            ambulance_arrival_time = (
                traci.simulation.getTime()
            )

            print(
                "[TEST] Using final simulation time "
                "as ambulance completion time."
            )

        if (
            ambulance_start_time is None
            or ambulance_arrival_time is None
        ):
            raise RuntimeError(
                "Ambulance was not observed during "
                "the experiment."
            )

        ambulance_travel_time = (
            ambulance_arrival_time
            - ambulance_start_time
        )

        return {
            "ambulance_travel_time": (
                ambulance_travel_time
            ),
            "total_waiting_time": (
                total_waiting_time
            ),
            "total_time_loss": (
                total_time_loss
            ),
            "preemption_count": (
                float(preemption_count)
            ),
        }

    finally:

        if controller is not None:

            try:
                controller.shutdown()

            except Exception:
                pass

        try:
            traci.close()

        except Exception:
            pass


def print_results(
    baseline: dict[str, float],
    ai: dict[str, float],
) -> None:

    travel_improvement = (
        baseline["ambulance_travel_time"]
        - ai["ambulance_travel_time"]
    )

    if (
        baseline["ambulance_travel_time"]
        > 0
    ):

        travel_improvement_percent = (
            travel_improvement
            / baseline["ambulance_travel_time"]
            * 100.0
        )

    else:

        travel_improvement_percent = 0.0

    print()
    print("=" * 80)
    print("PERFORMANCE COMPARISON")
    print("=" * 80)

    print(
        f"{'Metric':30}"
        f"{'Baseline':>15}"
        f"{'AI System':>15}"
    )

    print("-" * 60)

    print(
        f"{'Ambulance travel time (s)':30}"
        f"{baseline['ambulance_travel_time']:15.2f}"
        f"{ai['ambulance_travel_time']:15.2f}"
    )

    print(
        f"{'Total waiting time (s)':30}"
        f"{baseline['total_waiting_time']:15.2f}"
        f"{ai['total_waiting_time']:15.2f}"
    )

    print(
        f"{'Total time loss (s)':30}"
        f"{baseline['total_time_loss']:15.2f}"
        f"{ai['total_time_loss']:15.2f}"
    )

    print(
        f"{'Preemption activations':30}"
        f"{baseline['preemption_count']:15.0f}"
        f"{ai['preemption_count']:15.0f}"
    )

    print()
    print(
        f"Ambulance travel-time improvement: "
        f"{travel_improvement:.2f} s"
    )

    print(
        f"Improvement percentage: "
        f"{travel_improvement_percent:.2f}%"
    )

    print()
    print("=" * 80)
    print(
        "PERFORMANCE EVALUATION COMPLETED"
    )
    print("=" * 80)


def main() -> None:

    print()
    print("=" * 80)
    print(
        "AI PREDICTIVE TRAFFIC - "
        "PERFORMANCE EVALUATION"
    )
    print("=" * 80)

    print()
    print(
        f"Maximum simulation time: "
        f"{MAX_SIMULATION_TIME_S:.0f}s"
    )

    print(
        f"Test red window at Junction B: "
        f"{TEST_RED_START_S:.0f}s - "
        f"{TEST_RED_END_S:.0f}s"
    )

    # --------------------------------------------------------------
    # Baseline
    # --------------------------------------------------------------

    baseline = run_simulation(
        use_ai=False
    )

    # --------------------------------------------------------------
    # AI
    # --------------------------------------------------------------

    ai = run_simulation(
        use_ai=True
    )

    # --------------------------------------------------------------
    # Comparison
    # --------------------------------------------------------------

    print_results(
        baseline,
        ai,
    )


if __name__ == "__main__":
    main()
