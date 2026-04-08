"""Data models for actor-centric context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agents.core.messaging.event import AgentEvent
from agents.core.messaging.message import Message, MessageRole
from world.core.state import ActorState, WorldState


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped) // 4)


@dataclass(slots=True)
class ContextPacket:
    """A candidate runtime-context unit produced before each model call."""

    kind: str
    section: str
    content: str
    timestamp: datetime = field(default_factory=_utc_now)
    relevance_score: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0
    packet_id: str = field(default_factory=lambda: f"ctx_{uuid4().hex}")

    def __post_init__(self) -> None:
        self.relevance_score = max(0.0, min(1.0, self.relevance_score))
        if self.token_count <= 0:
            self.token_count = _estimate_token_count(self.content)


@dataclass(slots=True)
class ContextProfile:
    """Selection and rendering preferences for a specific event shape."""

    name: str
    required_kinds: tuple[str, ...] = ("policy", "event", "state")
    preferred_kinds: tuple[str, ...] = (
        "place_card",
        "activity_card",
        "npc_card",
        "memory",
        "history",
        "handoff",
        "tool_observation",
    )
    max_history_turns: int = 6
    max_memory_items: int = 4
    max_evidence_items: int = 6
    include_place_card: bool = True
    include_visible_npcs: bool = True
    recency_weight: float = 0.4
    relevance_weight: float = 0.6
    max_tokens: int = 2200

    def __post_init__(self) -> None:
        total_weight = self.recency_weight + self.relevance_weight
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError("recency_weight and relevance_weight must sum to 1.0")


@dataclass(slots=True)
class ContextBuildRequest:
    """Input bundle required to assemble actor-centric runtime context."""

    actor_id: str
    profile: ContextProfile
    event: AgentEvent | None = None
    world_state: WorldState | None = None
    actor_state: ActorState | None = None
    recent_messages: list[Message] = field(default_factory=list)
    scene_messages: list[Message] = field(default_factory=list)
    custom_packets: list[ContextPacket] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextBundle:
    """The assembled runtime context passed alongside the base system prompt."""

    system_prompt: str
    runtime_context_text: str
    selected_packets: list[ContextPacket] = field(default_factory=list)
    truncated_packets: list[ContextPacket] = field(default_factory=list)
    token_estimate: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_system_message(self) -> Message:
        """Convert the rendered runtime context into a system message."""

        return Message(
            role=MessageRole.SYSTEM,
            content=self.runtime_context_text,
            metadata=self.metadata.copy(),
        )
