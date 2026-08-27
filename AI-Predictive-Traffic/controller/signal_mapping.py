from dataclasses import dataclass

import traci


@dataclass
class SignalLink:
    signal_id: str
    signal_index: int
    incoming_lane: str
    outgoing_lane: str
    via_lane: str


def get_signal_links(signal_id: str) -> list[SignalLink]:
    """
    Retrieve the controlled lane connections for a traffic signal.

    Each signal index corresponds to one position in the traffic
    light state string.
    """

    if signal_id not in traci.trafficlight.getIDList():
        return []

    controlled_links = traci.trafficlight.getControlledLinks(signal_id)

    links: list[SignalLink] = []

    for signal_index, signal_connections in enumerate(controlled_links):
        if not signal_connections:
            continue

        for connection in signal_connections:
            if len(connection) < 3:
                continue

            incoming_lane, outgoing_lane, via_lane = connection

            links.append(
                SignalLink(
                    signal_id=signal_id,
                    signal_index=signal_index,
                    incoming_lane=incoming_lane,
                    outgoing_lane=outgoing_lane,
                    via_lane=via_lane,
                )
            )

    return links


_MOVEMENT_TO_TLS_CACHE: dict[tuple[str, str], tuple[str, list[int]]] | None = None


def _build_tls_cache() -> None:
    global _MOVEMENT_TO_TLS_CACHE
    if _MOVEMENT_TO_TLS_CACHE is not None:
        return

    _MOVEMENT_TO_TLS_CACHE = {}

    for tls_id in traci.trafficlight.getIDList():
        links = traci.trafficlight.getControlledLinks(tls_id)
        for signal_index, connections in enumerate(links):
            if not connections:
                continue

            for connection in connections:
                if len(connection) < 3:
                    continue

                incoming_lane, outgoing_lane, via_lane = connection
                incoming_edge = incoming_lane.rsplit("_", 1)[0]
                outgoing_edge = outgoing_lane.rsplit("_", 1)[0]

                key = (incoming_edge, outgoing_edge)
                if key not in _MOVEMENT_TO_TLS_CACHE:
                    _MOVEMENT_TO_TLS_CACHE[key] = (tls_id, [])

                if signal_index not in _MOVEMENT_TO_TLS_CACHE[key][1]:
                    _MOVEMENT_TO_TLS_CACHE[key][1].append(signal_index)


def get_tls_and_indices_for_movement(
    incoming_edge: str,
    outgoing_edge: str,
) -> tuple[str | None, list[int]]:
    """
    Find the actual Traffic Light System (TLS) ID and signal indices controlling 
    a specific edge-to-edge movement.

    This ignores SUMO internal Node IDs (junctions) which often do not 
    match the TLS IDs.

    Returns:
        (tls_id, list_of_indices) or (None, [])
    """
    _build_tls_cache()

    key = (incoming_edge, outgoing_edge)
    if key in _MOVEMENT_TO_TLS_CACHE:
        return _MOVEMENT_TO_TLS_CACHE[key]

    return None, []


def get_signal_indices_for_movement(
    signal_id: str,
    incoming_edge: str,
    outgoing_edge: str,
) -> list[int]:
    """
    Legacy method for backward compatibility.
    """
    tls_id, indices = get_tls_and_indices_for_movement(incoming_edge, outgoing_edge)
    if tls_id and tls_id == signal_id:
        return indices
    
    # If the provided signal_id didn't match the cache exactly, it might be a node ID.
    # We still return the indices found via the cache if any exist.
    return indices


def format_signal_links(links: list[SignalLink]) -> str:
    """
    Format signal-link information for readable console output.
    """

    if not links:
        return "No controlled links found."

    lines = []

    for link in links:
        lines.append(
            f"Signal index {link.signal_index:2d} | "
            f"{link.incoming_lane} -> {link.outgoing_lane} | "
            f"via: {link.via_lane}"
        )

    return "\n".join(lines)