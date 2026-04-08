"""Heartbeat-driven runtime loop for the Amphoreus MVP."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from agents.context import ContextPacket, ContextProfile
from agents.core.messaging.message import MessageRole
from agents.core.messaging.mode_result import ModeResult
from agents.runtime import CompanionRuntime
from world.core.manager import WorldManager
from world.core.state import ActorState

from instantiation.amphoreus.context import build_heartbeat_profile
from instantiation.amphoreus.scene_activation import (
    SceneActivationOrchestrator,
    SceneActivationTurn,
)
from instantiation.amphoreus.world_graph import TRANSIT_PLACE_ID, place_display_name


@dataclass(slots=True)
class HeartbeatTurnRecord:
    """One heartbeat cycle covering Cyrene and any scene-activated NPCs."""

    tick_index: int
    cyrene_result: ModeResult
    scene_turns: list[SceneActivationTurn] = field(default_factory=list)
    actor_place_id: str | None = None


class CyreneHeartbeatRunner:
    """Drive the MVP heartbeat loop on top of the companion runtime."""

    def __init__(
        self,
        *,
        runtime: CompanionRuntime,
        world_manager: WorldManager,
        scene_orchestrator: SceneActivationOrchestrator | None = None,
        profile: ContextProfile | None = None,
        actor_id: str = "cyrene",
    ) -> None:
        self.runtime = runtime
        self.world_manager = world_manager
        self.scene_orchestrator = scene_orchestrator
        self.profile = profile or build_heartbeat_profile()
        self.actor_id = actor_id
        self._tick_count = 0
        self._active_scene_id: str | None = None

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def run_tick(self, *, metadata: dict | None = None) -> HeartbeatTurnRecord:
        """Run one heartbeat cycle and optionally activate resident NPCs."""

        transition_packets = self._apply_due_world_transitions()
        self._tick_count += 1
        merged_metadata = {
            "heartbeat_tick_index": self._tick_count,
            **(metadata or {}),
        }
        cyrene_result = self.runtime.run_heartbeat_tick(
            profile=self.profile,
            custom_packets=transition_packets,
            metadata=merged_metadata,
        )
        actor_state = self.world_manager.get_actor_state(self.actor_id)
        actor_place_id = actor_state.current_place_id if actor_state is not None else None
        scene_intent = self._resolve_scene_intent(actor_place_id)
        scene_turns = self._activate_scene_if_needed(
            tick_index=self._tick_count,
            cyrene_result=cyrene_result,
            actor_place_id=actor_place_id,
            scene_intent=scene_intent,
        )
        return HeartbeatTurnRecord(
            tick_index=self._tick_count,
            cyrene_result=cyrene_result,
            scene_turns=scene_turns,
            actor_place_id=actor_place_id,
        )

    def run_loop(
        self,
        *,
        max_ticks: int,
        interval_seconds: float = 0.0,
        metadata_factory: Callable[[int], dict | None] | None = None,
    ) -> list[HeartbeatTurnRecord]:
        """Run a bounded heartbeat loop for tests or MVP harnesses."""

        if max_ticks <= 0:
            raise ValueError("max_ticks must be greater than 0")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be >= 0")

        records: list[HeartbeatTurnRecord] = []
        for index in range(max_ticks):
            tick_index = self._tick_count + 1
            metadata = metadata_factory(tick_index) if metadata_factory is not None else None
            records.append(self.run_tick(metadata=metadata))
            if interval_seconds > 0 and index < max_ticks - 1:
                time.sleep(interval_seconds)
        return records

    def _activate_scene_if_needed(
        self,
        *,
        tick_index: int,
        cyrene_result: ModeResult,
        actor_place_id: str | None,
        scene_intent: str | None,
    ) -> list[SceneActivationTurn]:
        if self.scene_orchestrator is None or not actor_place_id or not scene_intent:
            return []

        initiating_content = self._build_scene_trigger_content(cyrene_result, actor_place_id)
        if not initiating_content:
            return []

        return self.scene_orchestrator.activate_for_actor(
            actor_id=self.actor_id,
            scene_id=actor_place_id,
            initiating_content=initiating_content,
            intent=scene_intent,
            causal_ref=f"{self.actor_id}_heartbeat_{tick_index}",
            protagonist_runtime=self.runtime,
        )

    def _resolve_scene_intent(self, actor_place_id: str | None) -> str | None:
        if self.scene_orchestrator is None or not actor_place_id:
            self._active_scene_id = None
            return None

        visible_npcs = self.scene_orchestrator.visible_npc_resolver.resolve(actor_place_id)
        if not visible_npcs:
            self._active_scene_id = None
            return None

        if self._active_scene_id != actor_place_id:
            self._active_scene_id = actor_place_id
            return "scene_enter"

        return "scene_continue"

    def _apply_due_world_transitions(self) -> list[ContextPacket]:
        actor_state = self.world_manager.get_actor_state(self.actor_id)
        if actor_state is None:
            return []

        activity_block = actor_state.current_activity_block
        if activity_block is None or activity_block.activity_type != "travel":
            return []
        if activity_block.planned_until is None:
            return []

        now = self.world_manager.now()
        if now < activity_block.planned_until:
            return []

        destination_place_id = str(
            activity_block.payload.get("destination_place_id", "")
        ).strip()
        origin_place_id = str(activity_block.payload.get("from_place_id", "")).strip()
        if not destination_place_id:
            return []

        self.world_manager.set_actor_state(
            ActorState(
                actor_id=actor_state.actor_id,
                current_place_id=destination_place_id,
                current_activity_block=None,
            )
        )
        self._active_scene_id = None
        return [
            self._build_arrival_packet(
                arrived_at=activity_block.planned_until,
                origin_place_id=origin_place_id or TRANSIT_PLACE_ID,
                destination_place_id=destination_place_id,
            )
        ]

    def _build_arrival_packet(
        self,
        *,
        arrived_at: datetime,
        origin_place_id: str,
        destination_place_id: str,
    ) -> ContextPacket:
        return ContextPacket(
            kind="context",
            section="context",
            content=(
                "world_transition:\n"
                f"- kind: arrival\n"
                f"- from_place_id: {origin_place_id}\n"
                f"- to_place_id: {destination_place_id}\n"
                f"- arrived_at: {arrived_at.isoformat()}\n"
                f"- note: 你刚刚结束赶路，已抵达{place_display_name(destination_place_id)}。"
            ),
            timestamp=arrived_at,
            relevance_score=0.97,
            metadata={
                "transition_kind": "arrival",
                "from_place_id": origin_place_id,
                "to_place_id": destination_place_id,
            },
        )

    def _build_scene_trigger_content(
        self,
        result: ModeResult,
        actor_place_id: str,
    ) -> str:
        for message in reversed(result.messages):
            if message.role is MessageRole.ASSISTANT and message.content.strip():
                return message.content.strip()

        handoff_summary = (
            result.metadata.get("runtime", {}).get("handoff_summary", {})
            if isinstance(result.metadata, dict)
            else {}
        )
        if isinstance(handoff_summary, dict):
            summary_text = str(handoff_summary.get("summary_text", "")).strip()
            if summary_text:
                return summary_text

        return f"昔涟此刻位于 {actor_place_id}，但暂时没有新的明确表态。"


__all__ = [
    "HeartbeatTurnRecord",
    "CyreneHeartbeatRunner",
]
