"""Instance-level packet providers for Amphoreus runtime context."""

from __future__ import annotations

from agents.context import (
    ContextBuildRequest,
    ContextBuilder,
    ContextPacket,
    ContextProfile,
)
from memory import ActorMemoryStore

from instantiation.amphoreus.context.resolvers import (
    ActivityCardResolver,
    CharacterCardResolver,
    PlaceResolver,
    VisibleNpcResolver,
)
from instantiation.amphoreus.prompts import build_cyrene_system_prompt


class PlaceCardPacketProvider:
    """Attach the current place card when the actor has a known location."""

    def __init__(self, place_resolver: PlaceResolver | None = None) -> None:
        self.place_resolver = place_resolver or PlaceResolver()

    def build_packets(self, request: ContextBuildRequest) -> list[ContextPacket]:
        actor_state = request.actor_state
        if actor_state is None or not actor_state.current_place_id:
            return []

        place_card = self.place_resolver.resolve(actor_state.current_place_id)
        if not place_card:
            return []

        return [
            ContextPacket(
                kind="place_card",
                section="evidence",
                content="current_place_card:\n" + place_card,
                relevance_score=0.92,
                metadata={"place_id": actor_state.current_place_id},
            )
        ]


class VisibleNpcPacketProvider:
    """Attach resident NPC cards relevant to the actor's current place."""

    def __init__(
        self,
        visible_npc_resolver: VisibleNpcResolver | None = None,
        character_card_resolver: CharacterCardResolver | None = None,
    ) -> None:
        self.visible_npc_resolver = visible_npc_resolver or VisibleNpcResolver()
        self.character_card_resolver = character_card_resolver or CharacterCardResolver()

    def build_packets(self, request: ContextBuildRequest) -> list[ContextPacket]:
        actor_state = request.actor_state
        if actor_state is None or not actor_state.current_place_id:
            return []

        packets: list[ContextPacket] = []
        visible_npcs = self.visible_npc_resolver.resolve(actor_state.current_place_id)
        for character_id in visible_npcs:
            if character_id == request.actor_id:
                continue
            card = self.character_card_resolver.resolve(character_id)
            if not card:
                continue
            packets.append(
                ContextPacket(
                    kind="npc_card",
                    section="evidence",
                    content=f"visible_npc_card[{character_id}]:\n" + card,
                    relevance_score=0.8,
                    metadata={
                        "character_id": character_id,
                        "place_id": actor_state.current_place_id,
                    },
                )
            )
        return packets


class PlaceActivityPacketProvider:
    """Attach a place-scoped activity affordance card for the current location."""

    def __init__(
        self,
        activity_card_resolver: ActivityCardResolver | None = None,
    ) -> None:
        self.activity_card_resolver = activity_card_resolver or ActivityCardResolver()

    def build_packets(self, request: ContextBuildRequest) -> list[ContextPacket]:
        actor_state = request.actor_state
        if actor_state is None or not actor_state.current_place_id:
            return []

        activity_card = self.activity_card_resolver.resolve(actor_state.current_place_id)
        if not activity_card:
            return []

        return [
            ContextPacket(
                kind="activity_card",
                section="evidence",
                content="current_place_activities:\n" + activity_card,
                relevance_score=0.84,
                metadata={"place_id": actor_state.current_place_id},
            )
        ]


class RecentMemoryPacketProvider:
    """Attach a small set of actor memories relevant to the current turn."""

    def __init__(
        self,
        memory_store: ActorMemoryStore | None = None,
        visible_npc_resolver: VisibleNpcResolver | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.visible_npc_resolver = visible_npc_resolver or VisibleNpcResolver()

    def build_packets(self, request: ContextBuildRequest) -> list[ContextPacket]:
        if self.memory_store is None:
            return []

        actor_state = request.actor_state
        current_place_id = actor_state.current_place_id if actor_state is not None else None
        counterpart_ids: set[str] = set()
        if current_place_id:
            counterpart_ids.update(
                npc_id
                for npc_id in self.visible_npc_resolver.resolve(current_place_id)
                if npc_id != request.actor_id
            )
        counterpart_ids.update(
            counterpart_id
            for counterpart_id in request.metadata.get("memory_counterpart_ids", [])
            if str(counterpart_id).strip()
        )

        memories = self.memory_store.list_recent(
            actor_id=request.actor_id,
            limit=request.profile.max_memory_items,
            counterpart_ids=counterpart_ids,
            place_id=current_place_id,
        )
        packets: list[ContextPacket] = []
        for memory in memories:
            lines = [
                f"memory_type: {memory.memory_type}",
                f"created_at: {memory.created_at.isoformat()}",
            ]
            if memory.counterpart_id:
                lines.append(f"counterpart_id: {memory.counterpart_id}")
            if memory.place_id:
                lines.append(f"place_id: {memory.place_id}")
            lines.append(f"importance: {memory.importance:.2f}")
            lines.append("content: " + memory.preview_text)
            packets.append(
                ContextPacket(
                    kind="memory",
                    section="memory",
                    content="\n".join(lines),
                    timestamp=memory.created_at,
                    relevance_score=max(0.55, min(1.0, memory.importance + 0.1)),
                    metadata={
                        "memory_id": memory.id,
                        "memory_type": memory.memory_type,
                        "counterpart_id": memory.counterpart_id,
                        "place_id": memory.place_id,
                    },
                )
            )
        return packets


def build_heartbeat_profile() -> ContextProfile:
    """Context-selection profile used when Cyrene wakes on a heartbeat tick."""

    return ContextProfile(
        name="heartbeat",
        include_place_card=True,
        include_visible_npcs=True,
        max_tokens=2200,
        recency_weight=0.5,
        relevance_weight=0.5,
    )


def build_scene_turn_profile() -> ContextProfile:
    """Context-selection profile used for one NPC scene-activation turn."""

    return ContextProfile(
        name="scene_turn",
        include_place_card=True,
        include_visible_npcs=True,
        max_tokens=2000,
        recency_weight=0.45,
        relevance_weight=0.55,
    )


def build_cyrene_runtime_context_builder(
    *,
    system_prompt: str | None = None,
    memory_store: ActorMemoryStore | None = None,
) -> ContextBuilder:
    """Build the default runtime context without any passive phone-state exposure."""

    return ContextBuilder(
        system_prompt=system_prompt or build_cyrene_system_prompt(),
        packet_providers=(
            PlaceCardPacketProvider(),
            PlaceActivityPacketProvider(),
            VisibleNpcPacketProvider(),
            RecentMemoryPacketProvider(memory_store=memory_store),
        ),
    )


def build_scene_context_builder(
    *,
    system_prompt: str,
    memory_store: ActorMemoryStore | None = None,
) -> ContextBuilder:
    """Build a passive-phone-free context builder for scene-activated NPC turns."""

    return ContextBuilder(
        system_prompt=system_prompt,
        packet_providers=(
            PlaceCardPacketProvider(),
            PlaceActivityPacketProvider(),
            VisibleNpcPacketProvider(),
            RecentMemoryPacketProvider(memory_store=memory_store),
        ),
    )
