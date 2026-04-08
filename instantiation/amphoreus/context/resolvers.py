"""Resolvers for static Amphoreus prompt assets used at runtime."""

from __future__ import annotations

from instantiation.amphoreus.prompts import (
    load_character_prompt,
    load_world_activity_prompt,
    load_world_place_prompt,
)

VISIBLE_NPCS_BY_PLACE: dict[str, tuple[str, ...]] = {
    "okhema": ("aglaea",),
    "dawncloud": ("aglaea",),
    "temple_and_observatory": ("tribbie",),
    "grove_of_epiphany": ("anaxa",),
    "styxia_harbor": ("phainon",),
    "outer_ring_road": ("phainon",),
    "aedes_elysiae": ("phainon",),
}


class PlaceResolver:
    """Resolve a place card by its world-state place id."""

    def resolve(self, place_id: str) -> str | None:
        try:
            return load_world_place_prompt(place_id)
        except FileNotFoundError:
            return None


class CharacterCardResolver:
    """Resolve a character card by character id."""

    def resolve(self, character_id: str) -> str | None:
        try:
            return load_character_prompt(character_id, "card")
        except FileNotFoundError:
            return None


class ActivityCardResolver:
    """Resolve a place-scoped activity affordance card."""

    def resolve(self, place_id: str) -> str | None:
        try:
            return load_world_activity_prompt(place_id)
        except FileNotFoundError:
            return None


class VisibleNpcResolver:
    """Map the current place to the NPCs likely visible in that location."""

    def resolve(self, place_id: str) -> tuple[str, ...]:
        return VISIBLE_NPCS_BY_PLACE.get(place_id, ())
