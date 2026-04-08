"""Static navigation facts for the Amphoreus MVP."""

from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush

TRANSIT_PLACE_ID = "in_transit"

PLACE_DISPLAY_NAMES: dict[str, str] = {
    "aedes_elysiae": "哀丽秘榭",
    "dawncloud": "云晓栈道",
    "grove_of_epiphany": "神悟树庭",
    "in_transit": "路上",
    "janusopolis_ruins": "雅努萨波利斯遗址",
    "okhema": "奥赫玛",
    "outer_ring_road": "外环路",
    "styxia_harbor": "斯堤克西亚港",
    "temple_and_observatory": "神殿与观星台",
}

TRAVEL_ROUTES: dict[tuple[str, str], int] = {
    ("aedes_elysiae", "outer_ring_road"): 18,
    ("dawncloud", "grove_of_epiphany"): 16,
    ("dawncloud", "okhema"): 12,
    ("grove_of_epiphany", "okhema"): 20,
    ("grove_of_epiphany", "temple_and_observatory"): 14,
    ("janusopolis_ruins", "outer_ring_road"): 26,
    ("okhema", "outer_ring_road"): 16,
    ("okhema", "styxia_harbor"): 24,
    ("okhema", "temple_and_observatory"): 18,
    ("outer_ring_road", "styxia_harbor"): 12,
}


def list_supported_place_ids() -> tuple[str, ...]:
    """Return the navigable place ids supported by the MVP world graph."""

    return tuple(
        sorted(
            place_id
            for place_id in PLACE_DISPLAY_NAMES
            if place_id != TRANSIT_PLACE_ID
        )
    )


def place_display_name(place_id: str) -> str:
    """Resolve a stable human-readable name for a place id."""

    return PLACE_DISPLAY_NAMES.get(place_id, place_id)


def estimate_travel_minutes(origin_place_id: str, destination_place_id: str) -> int:
    """Estimate the shortest travel time between two world places."""

    if origin_place_id == destination_place_id:
        return 0

    if origin_place_id not in PLACE_DISPLAY_NAMES:
        raise ValueError(f"unknown origin_place_id: {origin_place_id}")
    if destination_place_id not in PLACE_DISPLAY_NAMES:
        raise ValueError(f"unknown destination_place_id: {destination_place_id}")
    if origin_place_id == TRANSIT_PLACE_ID or destination_place_id == TRANSIT_PLACE_ID:
        raise ValueError("travel routes must start and end at stable world places")

    graph: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (left, right), minutes in TRAVEL_ROUTES.items():
        graph[left].append((right, minutes))
        graph[right].append((left, minutes))

    queue: list[tuple[int, str]] = [(0, origin_place_id)]
    visited: set[str] = set()

    while queue:
        total_minutes, place_id = heappop(queue)
        if place_id == destination_place_id:
            return total_minutes
        if place_id in visited:
            continue
        visited.add(place_id)
        for neighbor, leg_minutes in graph.get(place_id, ()):
            if neighbor not in visited:
                heappush(queue, (total_minutes + leg_minutes, neighbor))

    raise ValueError(
        "no travel route from "
        + origin_place_id
        + " to "
        + destination_place_id
    )


__all__ = [
    "PLACE_DISPLAY_NAMES",
    "TRANSIT_PLACE_ID",
    "TRAVEL_ROUTES",
    "estimate_travel_minutes",
    "list_supported_place_ids",
    "place_display_name",
]
